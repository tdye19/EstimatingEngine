"""Project management router."""

import math
import os
import shutil
import time
import uuid
from pathlib import Path
import csv
import io
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, BackgroundTasks, Query
from sqlalchemy.orm import Session
from apex.backend.db.database import get_db
from apex.backend.models.project import Project
from apex.backend.models.document import Document
from apex.backend.models.project_actual import ProjectActual
from apex.backend.models.upload_session import UploadSession
from apex.backend.models.upload_chunk import UploadChunk
from apex.backend.models.user import User
from apex.backend.services.crew_orchestrator import get_orchestrator
from apex.backend.utils.auth import require_auth, get_authorized_project, get_current_user, SECRET_KEY, ALGORITHM
from apex.backend.utils.schemas import (
    ProjectCreate, ProjectUpdate, ProjectOut, DocumentOut, APIResponse,
    PipelineStatusOut, AgentStepStatus, ChunkedUploadInitRequest,
    ShadowComparisonOut,
)

router = APIRouter(prefix="/api/projects", tags=["projects"], dependencies=[Depends(require_auth)])

from slowapi import Limiter
from slowapi.util import get_remote_address
from apex.backend.config import (
    UPLOAD_DIR, CHUNK_SIZE, SESSION_TTL, MAX_UPLOAD_BYTES, ALLOWED_EXTENSIONS,
    PIPELINE_RATE_LIMIT,
)
_limiter = Limiter(key_func=get_remote_address)
from apex.backend.utils.upload_utils import get_chunk_path, assemble_chunks, cleanup_chunks

def cleanup_stale_upload_sessions() -> None:
    """Remove upload sessions and temp dirs older than SESSION_TTL. Call on startup."""
    now = datetime.utcnow()
    from apex.backend.db.database import SessionLocal
    db = SessionLocal()
    try:
        expired_sessions = (
            db.query(UploadSession)
            .filter(UploadSession.expires_at < now)
            .all()
        )
        for session in expired_sessions:
            cleanup_chunks(session.upload_id)
            db.delete(session)
        db.commit()
    finally:
        db.close()

    # Also remove old tmp dirs on disk from previous server runs.
    tmp_root = os.path.join(UPLOAD_DIR, "tmp")
    if os.path.isdir(tmp_root):
        for entry in os.scandir(tmp_root):
            if entry.is_dir():
                age = time.time() - entry.stat().st_mtime
                if age > SESSION_TTL:
                    shutil.rmtree(entry.path, ignore_errors=True)


def _generate_project_number(db: Session) -> str:
    year = datetime.now().year
    prefix = f"PRJ-{year}-"
    from sqlalchemy import func
    max_num = (
        db.query(func.max(Project.project_number))
        .filter(Project.project_number.like(f"{prefix}%"))
        .scalar()
    )
    if max_num:
        last_seq = int(max_num.replace(prefix, ""))
    else:
        last_seq = 0
    return f"{prefix}{last_seq + 1:03d}"


@router.post("", response_model=APIResponse)
def create_project(
    data: ProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    project_number = data.project_number or _generate_project_number(db)

    existing = db.query(Project).filter(Project.project_number == project_number).first()
    if existing:
        raise HTTPException(status_code=400, detail="Project number already exists")

    mode = data.mode if data.mode in ("shadow", "production") else "shadow"
    project = Project(
        name=data.name,
        project_number=project_number,
        project_type=data.project_type,
        mode=mode,
        description=data.description,
        location=data.location,
        square_footage=data.square_footage,
        estimated_value=data.estimated_value,
        bid_date=data.bid_date,
        owner_id=user.id,
        organization_id=user.organization_id,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    return APIResponse(
        success=True,
        message="Project created",
        data=ProjectOut.model_validate(project).model_dump(mode="json"),
    )


@router.get("", response_model=APIResponse)
def list_projects(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    query = db.query(Project).filter(
        Project.is_deleted == False,  # noqa: E712
        Project.owner_id == user.id,
    ).order_by(Project.id.desc())
    total = query.count()
    projects = query.offset(skip).limit(min(limit, 200)).all()
    return APIResponse(
        success=True,
        data=[ProjectOut.model_validate(p).model_dump(mode="json") for p in projects],
        message=f"{total} projects total",
    )


@router.get("/{project_id}", response_model=APIResponse)
def get_project(project_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    project = get_authorized_project(project_id, user, db)
    return APIResponse(
        success=True,
        data=ProjectOut.model_validate(project).model_dump(mode="json"),
    )


@router.put("/{project_id}", response_model=APIResponse)
def update_project(project_id: int, data: ProjectUpdate, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    project = get_authorized_project(project_id, user, db)

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)

    return APIResponse(
        success=True,
        message="Project updated",
        data=ProjectOut.model_validate(project).model_dump(mode="json"),
    )


@router.get("/{project_id}/comparison", response_model=APIResponse)
def get_shadow_comparison(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    """Return shadow comparison data: APEX estimate vs manual estimate."""
    from apex.backend.models.estimate import Estimate, EstimateLineItem

    project = get_authorized_project(project_id, user, db)

    # Get latest APEX estimate
    latest_estimate = (
        db.query(Estimate)
        .filter(Estimate.project_id == project_id, Estimate.is_deleted == False)  # noqa: E712
        .order_by(Estimate.version.desc())
        .first()
    )

    apex_total = latest_estimate.total_bid_amount if latest_estimate else None
    manual_total = project.manual_estimate_total

    variance_abs = None
    variance_pct = None
    if apex_total is not None and manual_total is not None:
        variance_abs = apex_total - manual_total
        if manual_total != 0:
            variance_pct = round((variance_abs / manual_total) * 100, 2)

    # Build by-division breakdown from APEX estimate line items
    by_division = None
    if latest_estimate:
        division_totals = {}
        line_items = (
            db.query(EstimateLineItem)
            .filter(EstimateLineItem.estimate_id == latest_estimate.id)
            .all()
        )
        for item in line_items:
            div = item.division_number
            if div not in division_totals:
                division_totals[div] = {"division": div, "apex_total": 0.0}
            division_totals[div]["apex_total"] += item.total_cost
        by_division = sorted(division_totals.values(), key=lambda d: d["division"])

    comparison = ShadowComparisonOut(
        project_id=project_id,
        mode=project.mode,
        apex_estimate_total=apex_total,
        manual_estimate_total=manual_total,
        manual_estimate_notes=project.manual_estimate_notes,
        variance_absolute=variance_abs,
        variance_pct=variance_pct,
        by_division=by_division,
    )

    return APIResponse(
        success=True,
        data=comparison.model_dump(mode="json"),
    )


@router.post("/{project_id}/documents", response_model=APIResponse)
async def upload_document(
    project_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    project = get_authorized_project(project_id, user, db)

    # Validate file extension
    file_ext = os.path.splitext(file.filename)[1] if file.filename else ""
    file_type = file_ext.lstrip(".").lower() if file_ext else ""
    if file_type not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '.{file_type}' not allowed. Accepted: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Read content and validate size
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({len(content) / 1024 / 1024:.1f} MB). Maximum: {MAX_UPLOAD_BYTES // 1024 // 1024} MB",
        )

    # Ensure upload directory exists
    project_dir = os.path.join(UPLOAD_DIR, str(project_id))
    os.makedirs(project_dir, exist_ok=True)

    # Save file
    unique_name = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(project_dir, unique_name)
    with open(file_path, "wb") as f:
        f.write(content)

    doc = Document(
        project_id=project_id,
        filename=file.filename or unique_name,
        file_path=file_path,
        file_type=file_type,
        file_size_bytes=len(content),
        processing_status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    return APIResponse(
        success=True,
        message="Document uploaded",
        data=DocumentOut.model_validate(doc).model_dump(mode="json"),
    )


@router.post("/{project_id}/documents/upload/init", response_model=APIResponse)
async def chunked_upload_init(
    project_id: int,
    data: ChunkedUploadInitRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    """Initialize a chunked upload session. Returns upload_id and chunk_size."""
    get_authorized_project(project_id, user, db)

    # Validate file extension
    file_ext = os.path.splitext(data.filename)[1].lstrip(".").lower() if data.filename else ""
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '.{file_ext}' not allowed. Accepted: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Validate file size
    if data.file_size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({data.file_size / 1024 / 1024:.1f} MB). Maximum: {MAX_UPLOAD_BYTES // 1024 // 1024} MB",
        )

    upload_id = str(uuid.uuid4())
    total_chunks = math.ceil(data.file_size / CHUNK_SIZE)

    temp_dir = os.path.join(UPLOAD_DIR, "tmp", upload_id)
    os.makedirs(temp_dir, exist_ok=True)

    db.add(
        UploadSession(
            upload_id=upload_id,
            project_id=project_id,
            filename=data.filename,
            file_size=data.file_size,
            content_type=data.content_type,
            total_chunks=total_chunks,
            next_chunk=0,
            temp_dir=temp_dir,
            expires_at=datetime.utcnow() + timedelta(seconds=SESSION_TTL),
        )
    )
    db.commit()

    return APIResponse(
        success=True,
        message="Upload session initialized",
        data={"upload_id": upload_id, "chunk_size": CHUNK_SIZE, "total_chunks": total_chunks},
    )


@router.post("/{project_id}/documents/upload/{upload_id}/chunk", response_model=APIResponse)
async def chunked_upload_chunk(
    project_id: int,
    upload_id: str,
    chunk_number: int,
    chunk: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Receive one chunk. chunk_number is 0-indexed and must be sequential."""
    session = db.query(UploadSession).filter(UploadSession.upload_id == upload_id).first()
    if not session or session.project_id != project_id:
        raise HTTPException(status_code=404, detail="Upload session not found")
    if session.expires_at < datetime.utcnow():
        if session.temp_dir and os.path.isdir(session.temp_dir):
            shutil.rmtree(session.temp_dir, ignore_errors=True)
        db.delete(session)
        db.commit()
        raise HTTPException(status_code=404, detail="Upload session expired")

    expected = session.next_chunk
    if chunk_number != expected:
        raise HTTPException(
            status_code=400,
            detail=f"Expected chunk {expected}, got chunk_number={chunk_number}",
        )

    chunk_data = await chunk.read()
    get_chunk_path(upload_id, chunk_number).write_bytes(chunk_data)

    session.next_chunk = chunk_number + 1
    session.expires_at = datetime.utcnow() + timedelta(seconds=SESSION_TTL)
    db.commit()
    chunks_received = session.next_chunk

    return APIResponse(
        success=True,
        data={"chunks_received": chunks_received, "total_expected": session.total_chunks},
    )


@router.post("/{project_id}/documents/upload/{upload_id}/complete", response_model=APIResponse)
async def chunked_upload_complete(
    project_id: int,
    upload_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Reassemble chunks into the final file, create Document record, trigger pipeline."""
    session = db.query(UploadSession).filter(UploadSession.upload_id == upload_id).first()
    if not session or session.project_id != project_id:
        raise HTTPException(status_code=404, detail="Upload session not found")
    if session.expires_at < datetime.utcnow():
        if session.temp_dir and os.path.isdir(session.temp_dir):
            shutil.rmtree(session.temp_dir, ignore_errors=True)
        db.delete(session)
        db.commit()
        raise HTTPException(status_code=404, detail="Upload session expired")

    total_chunks = session.total_chunks
    chunks_received = session.next_chunk
    if chunks_received != total_chunks:
        raise HTTPException(
            status_code=400,
            detail=f"Incomplete upload: received {chunks_received}/{total_chunks} chunks",
        )

    # Reassemble into final file
    project_dir = os.path.join(UPLOAD_DIR, str(project_id))
    os.makedirs(project_dir, exist_ok=True)

    filename = session.filename
    file_ext = os.path.splitext(filename)[1]
    unique_name = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(project_dir, unique_name)

    if not assemble_chunks(upload_id, total_chunks, Path(file_path)):
        raise HTTPException(
            status_code=400,
            detail=f"Incomplete upload: one or more chunks missing on disk",
        )

    file_size = os.path.getsize(file_path)
    file_type = file_ext.lstrip(".").lower() if file_ext else "unknown"

    doc = Document(
        project_id=project_id,
        filename=filename,
        file_path=file_path,
        file_type=file_type,
        file_size_bytes=file_size,
        processing_status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # Clean up temp chunks
    cleanup_chunks(upload_id)
    db.delete(session)
    db.commit()

    # Auto-trigger pipeline after chunked upload completes
    background_tasks.add_task(
        _run_pipeline,
        project_id=project_id,
        document_id=doc.id,
        pipeline_mode=None,  # auto-detected from file type
    )

    return APIResponse(
        success=True,
        message="Document uploaded",
        data=DocumentOut.model_validate(doc).model_dump(mode="json"),
    )


@router.get("/{project_id}/documents", response_model=APIResponse)
def list_documents(project_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    get_authorized_project(project_id, user, db)
    docs = db.query(Document).filter(
        Document.project_id == project_id,
        Document.is_deleted == False,  # noqa: E712
    ).all()
    return APIResponse(
        success=True,
        data=[DocumentOut.model_validate(d).model_dump(mode="json") for d in docs],
    )


@router.post("/{project_id}/documents/bulk-delete", response_model=APIResponse)
def bulk_delete_documents(
    project_id: int,
    data: dict,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    """Soft-delete multiple documents at once."""
    get_authorized_project(project_id, user, db)
    doc_ids = data.get("document_ids", [])
    if not doc_ids:
        raise HTTPException(status_code=400, detail="No document IDs provided")

    count = 0
    for doc_id in doc_ids:
        doc = db.query(Document).filter(
            Document.id == doc_id,
            Document.project_id == project_id,
            Document.is_deleted == False,  # noqa: E712
        ).first()
        if doc:
            doc.is_deleted = True
            count += 1
    db.commit()
    return APIResponse(success=True, message=f"Deleted {count} documents", data={"deleted": count})


@router.post("/{project_id}/clone", response_model=APIResponse)
def clone_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    """Clone a project with its estimate, line items, takeoff items, and spec sections."""
    source = get_authorized_project(project_id, user, db)

    new_number = _generate_project_number(db)
    clone = Project(
        name=f"{source.name} (Copy)",
        project_number=new_number,
        project_type=source.project_type,
        description=source.description,
        location=source.location,
        square_footage=source.square_footage,
        estimated_value=source.estimated_value,
        bid_date=source.bid_date,
        status="draft",
        owner_id=user.id,
        organization_id=user.organization_id,
    )
    db.add(clone)
    db.flush()  # get clone.id

    # Clone spec sections
    from apex.backend.models.spec_section import SpecSection
    sections = db.query(SpecSection).filter(
        SpecSection.project_id == project_id, SpecSection.is_deleted == False  # noqa: E712
    ).all()
    for s in sections:
        db.add(SpecSection(
            project_id=clone.id, document_id=None,
            division_number=s.division_number, section_number=s.section_number,
            title=s.title, work_description=s.work_description,
            materials_referenced=s.materials_referenced,
            execution_requirements=s.execution_requirements,
            submittal_requirements=s.submittal_requirements,
            keywords=s.keywords, raw_text=s.raw_text,
        ))

    # Clone takeoff items
    from apex.backend.models.takeoff_item import TakeoffItem
    items = db.query(TakeoffItem).filter(
        TakeoffItem.project_id == project_id, TakeoffItem.is_deleted == False  # noqa: E712
    ).all()
    for t in items:
        db.add(TakeoffItem(
            project_id=clone.id, csi_code=t.csi_code,
            description=t.description, quantity=t.quantity,
            unit_of_measure=t.unit_of_measure, drawing_reference=t.drawing_reference,
            confidence=t.confidence, notes=t.notes,
        ))

    # Clone latest estimate + line items
    from apex.backend.models.estimate import Estimate, EstimateLineItem
    est = db.query(Estimate).filter(
        Estimate.project_id == project_id, Estimate.is_deleted == False  # noqa: E712
    ).order_by(Estimate.version.desc()).first()
    if est:
        new_est = Estimate(
            project_id=clone.id, version=1, status="draft",
            total_direct_cost=est.total_direct_cost,
            total_labor_cost=est.total_labor_cost,
            total_material_cost=est.total_material_cost,
            total_subcontractor_cost=est.total_subcontractor_cost,
            gc_markup_pct=est.gc_markup_pct, gc_markup_amount=est.gc_markup_amount,
            overhead_pct=est.overhead_pct, overhead_amount=est.overhead_amount,
            profit_pct=est.profit_pct, profit_amount=est.profit_amount,
            contingency_pct=est.contingency_pct, contingency_amount=est.contingency_amount,
            total_bid_amount=est.total_bid_amount,
            exclusions=est.exclusions, assumptions=est.assumptions,
            alternates=est.alternates, executive_summary=est.executive_summary,
        )
        db.add(new_est)
        db.flush()
        for li in est.line_items:
            db.add(EstimateLineItem(
                estimate_id=new_est.id, division_number=li.division_number,
                csi_code=li.csi_code, description=li.description,
                quantity=li.quantity, unit_of_measure=li.unit_of_measure,
                labor_cost=li.labor_cost, material_cost=li.material_cost,
                equipment_cost=li.equipment_cost, subcontractor_cost=li.subcontractor_cost,
                total_cost=li.total_cost, unit_cost=li.unit_cost,
            ))

    db.commit()
    db.refresh(clone)

    return APIResponse(
        success=True,
        message=f"Project cloned as {clone.project_number}",
        data=ProjectOut.model_validate(clone).model_dump(mode="json"),
    )


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    project = get_authorized_project(project_id, user, db)
    project.is_deleted = True
    db.commit()


@router.delete("/{project_id}/documents/{doc_id}", status_code=204)
def delete_document(project_id: int, doc_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    get_authorized_project(project_id, user, db)
    doc = db.query(Document).filter(
        Document.id == doc_id,
        Document.project_id == project_id,
        Document.is_deleted == False,  # noqa: E712
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    doc.is_deleted = True
    db.commit()


def _detect_pipeline_mode(db: Session, project_id: int, document_id: int = None) -> str:
    """Auto-detect pipeline mode from pending document file types.

    Returns "winest_import" if any pending document is a native .est file.
    For .xlsx WinEst exports the mode is determined by Agent 1 during
    processing (it signals back via output["pipeline_mode"]).
    """
    query = db.query(Document).filter(
        Document.project_id == project_id,
        Document.is_deleted == False,  # noqa: E712
        Document.processing_status == "pending",
    )
    if document_id is not None:
        query = query.filter(Document.id == document_id)

    for doc in query.all():
        if doc.file_type == "est":
            return "winest_import"
    return "spec"


def _run_pipeline(project_id: int, document_id: int = None, pipeline_mode: str = None):
    """Background task to run the agent pipeline.

    If *pipeline_mode* is not supplied it is auto-detected from the pending
    document's file type (.est → "winest_import", everything else → "spec").
    """
    from apex.backend.db.database import SessionLocal
    db = SessionLocal()
    try:
        if pipeline_mode is None:
            pipeline_mode = _detect_pipeline_mode(db, project_id, document_id)
        orchestrator = get_orchestrator(db, project_id)
        orchestrator.run_pipeline(document_id=document_id, pipeline_mode=pipeline_mode)
    finally:
        db.close()


@router.post("/{project_id}/run-agents", response_model=APIResponse)
@_limiter.limit(PIPELINE_RATE_LIMIT)
def run_agents(
    request: Request,
    project_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    get_authorized_project(project_id, user, db)

    background_tasks.add_task(_run_pipeline, project_id)

    return APIResponse(
        success=True,
        message="Agent pipeline started",
        data={"project_id": project_id, "status": "running"},
    )


@router.post("/{project_id}/pipeline/run", response_model=APIResponse)
@_limiter.limit(PIPELINE_RATE_LIMIT)
def pipeline_run(
    request: Request,
    project_id: int,
    background_tasks: BackgroundTasks,
    document_id: int = None,
    pipeline_mode: str = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    """Start the agent pipeline in the background.

    Query params:
      document_id   — specific document to process (defaults to latest upload)
      pipeline_mode — "spec" | "winest_import" (auto-detected if omitted;
                      .est files always trigger "winest_import")
    """
    get_authorized_project(project_id, user, db)

    # Resolve document_id if not provided
    if document_id is None:
        latest_doc = (
            db.query(Document)
            .filter(Document.project_id == project_id, Document.is_deleted == False)  # noqa: E712
            .order_by(Document.id.desc())
            .first()
        )
        if latest_doc:
            document_id = latest_doc.id

    # Auto-detect mode if caller didn't specify
    if pipeline_mode is None:
        pipeline_mode = _detect_pipeline_mode(db, project_id, document_id)

    background_tasks.add_task(_run_pipeline, project_id, document_id, pipeline_mode)

    return APIResponse(
        success=True,
        message="Pipeline started",
        data={
            "status":        "started",
            "project_id":    project_id,
            "document_id":   document_id,
            "pipeline_mode": pipeline_mode,
        },
    )


@router.get("/{project_id}/pipeline/status", response_model=PipelineStatusOut)
def pipeline_status(project_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    """Return the current pipeline status for each agent (1-6)."""
    get_authorized_project(project_id, user, db)

    orchestrator = get_orchestrator(db, project_id)
    statuses = orchestrator.get_pipeline_status()

    # Derive overall status
    status_values = [s["status"] for s in statuses]
    if any(s == "running" for s in status_values):
        overall = "running"
    elif any(s == "failed" for s in status_values):
        overall = "failed"
    elif all(s in ("completed", "skipped") for s in status_values):
        overall = "completed"
    elif all(s == "pending" for s in status_values):
        overall = "pending"
    else:
        overall = "running"

    return PipelineStatusOut(
        project_id=project_id,
        agents=[AgentStepStatus(**s) for s in statuses],
        overall=overall,
    )


@router.post("/{project_id}/agents/{agent_number}/run", response_model=APIResponse)
def run_single_agent(
    project_id: int,
    agent_number: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    if agent_number < 1 or agent_number > 7:
        raise HTTPException(status_code=400, detail="agent_number must be between 1 and 7")
    get_authorized_project(project_id, user, db)
    try:
        orchestrator = get_orchestrator(db, project_id)
        result = orchestrator.run_single_agent(agent_number)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent {agent_number} failed: {str(e)}")
    return APIResponse(
        success=True,
        message=f"Agent {agent_number} completed",
        data=result,
    )


@router.get("/{project_id}/documents/{doc_id}/file")
def get_document_file(
    project_id: int,
    doc_id: int,
    token: str = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Serve the actual document file for viewing."""
    from jose import JWTError, jwt as jose_jwt

    # If no user from Authorization header, try the query-string token
    if user is None and token:
        try:
            payload = jose_jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            sub = payload.get("sub")
            if sub is not None:
                user = db.query(User).filter(
                    User.id == int(sub), User.is_deleted == False  # noqa: E712
                ).first()
        except (JWTError, ValueError):
            pass

    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    get_authorized_project(project_id, user, db)
    doc = db.query(Document).filter(
        Document.id == doc_id,
        Document.project_id == project_id,
        Document.is_deleted == False,  # noqa: E712
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = doc.file_path
    if not os.path.isabs(file_path):
        file_path = os.path.join(os.getcwd(), file_path)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    from fastapi.responses import FileResponse
    media_type = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "csv": "text/csv",
        "txt": "text/plain",
    }.get(doc.file_type, "application/octet-stream")

    return FileResponse(file_path, media_type=media_type, filename=doc.filename)


@router.post("/{project_id}/actuals", response_model=APIResponse)
async def upload_actuals(
    project_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    """Upload field actuals as CSV and trigger IMPROVE agent."""
    get_authorized_project(project_id, user, db)

    content = await file.read()
    text = content.decode("utf-8", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))

    required_columns = {"csi_code"}
    if reader.fieldnames is None:
        raise HTTPException(status_code=400, detail="CSV file is empty or has no header row")
    missing = required_columns - set(reader.fieldnames)
    if missing:
        raise HTTPException(status_code=400, detail=f"CSV missing required columns: {', '.join(sorted(missing))}")

    imported = 0
    skipped = 0
    for row_num, row in enumerate(reader, start=2):
        try:
            actual = ProjectActual(
                project_id=project_id,
                csi_code=row.get("csi_code", "").strip(),
                description=row.get("description", ""),
                actual_quantity=float(row.get("actual_quantity", 0) or 0),
                actual_labor_hours=float(row.get("actual_labor_hours", 0) or 0),
                actual_cost=float(row.get("actual_cost", 0) or 0),
                crew_type=row.get("crew_type", ""),
                work_type=row.get("work_type", ""),
            )
        except (ValueError, TypeError):
            skipped += 1
            continue
        db.add(actual)
        imported += 1

    if imported == 0:
        raise HTTPException(status_code=400, detail=f"No valid rows in CSV ({skipped} rows skipped due to invalid data)")

    db.commit()

    # Run IMPROVE agent in background
    def _run_improve(pid: int):
        from apex.backend.db.database import SessionLocal
        session = SessionLocal()
        try:
            orchestrator = get_orchestrator(session, pid)
            orchestrator.run_improve_agent()
        finally:
            session.close()

    background_tasks.add_task(_run_improve, project_id)

    return APIResponse(
        success=True,
        message=f"Imported {imported} actuals ({skipped} skipped), IMPROVE agent started",
        data={"imported": imported, "skipped": skipped},
    )


@router.post("/{project_id}/actuals/entry", response_model=APIResponse)
def submit_actual_entry(
    project_id: int,
    data: dict,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    """Submit a single field actual record (mobile-friendly)."""
    get_authorized_project(project_id, user, db)

    actual = ProjectActual(
        project_id=project_id,
        csi_code=data.get("csi_code", "").strip(),
        description=data.get("description", ""),
        actual_quantity=float(data.get("actual_quantity", 0) or 0),
        actual_labor_hours=float(data.get("actual_labor_hours", 0) or 0),
        actual_cost=float(data.get("actual_cost", 0) or 0),
        crew_type=data.get("crew_type", ""),
        work_type=data.get("work_type", ""),
    )
    db.add(actual)
    db.commit()
    db.refresh(actual)

    return APIResponse(
        success=True,
        message="Actual entry recorded",
        data={"id": actual.id, "csi_code": actual.csi_code},
    )
