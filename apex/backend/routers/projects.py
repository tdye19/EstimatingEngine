"""Project management router."""

import math
import os
import shutil
import time
import uuid
import csv
import io
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, Response
from sqlalchemy.orm import Session
from apex.backend.db.database import get_db
from apex.backend.models.project import Project
from apex.backend.models.document import Document
from apex.backend.models.project_actual import ProjectActual
from apex.backend.models.user import User
from apex.backend.services.crew_orchestrator import get_orchestrator
from apex.backend.utils.auth import require_auth
from apex.backend.utils.schemas import (
    ProjectCreate, ProjectUpdate, ProjectOut, DocumentOut, APIResponse,
    PipelineStatusOut, AgentStepStatus, ChunkedUploadInitRequest,
)

router = APIRouter(prefix="/api/projects", tags=["projects"], dependencies=[Depends(require_auth)])

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
CHUNK_SIZE = 1024 * 1024        # 1 MB per chunk
SESSION_TTL = 1800              # 30 minutes in seconds

# In-memory upload session store: upload_id -> session dict
_upload_sessions: dict[str, dict] = {}


def cleanup_stale_upload_sessions() -> None:
    """Remove upload sessions and temp dirs older than SESSION_TTL. Call on startup."""
    now = time.time()
    stale = [uid for uid, s in list(_upload_sessions.items()) if now - s["created_at"] > SESSION_TTL]
    for uid in stale:
        temp_dir = _upload_sessions[uid].get("temp_dir", "")
        if temp_dir and os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        _upload_sessions.pop(uid, None)

    # Also remove any orphaned tmp dirs on disk from previous server runs
    tmp_root = os.path.join(UPLOAD_DIR, "tmp")
    if os.path.isdir(tmp_root):
        for entry in os.scandir(tmp_root):
            if entry.is_dir() and entry.name not in _upload_sessions:
                age = now - entry.stat().st_mtime
                if age > SESSION_TTL:
                    shutil.rmtree(entry.path, ignore_errors=True)


def _generate_project_number(db: Session) -> str:
    year = datetime.now().year
    prefix = f"PRJ-{year}-"
    count = db.query(Project).filter(Project.project_number.like(f"{prefix}%")).count()
    return f"{prefix}{count + 1:03d}"


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

    project = Project(
        name=data.name,
        project_number=project_number,
        project_type=data.project_type,
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
def list_projects(db: Session = Depends(get_db)):
    projects = db.query(Project).filter(Project.is_deleted == False).all()  # noqa: E712
    return APIResponse(
        success=True,
        data=[ProjectOut.model_validate(p).model_dump(mode="json") for p in projects],
    )


@router.get("/{project_id}", response_model=APIResponse)
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(
        Project.id == project_id, Project.is_deleted == False  # noqa: E712
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return APIResponse(
        success=True,
        data=ProjectOut.model_validate(project).model_dump(mode="json"),
    )


@router.put("/{project_id}", response_model=APIResponse)
def update_project(project_id: int, data: ProjectUpdate, db: Session = Depends(get_db)):
    project = db.query(Project).filter(
        Project.id == project_id, Project.is_deleted == False  # noqa: E712
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)

    return APIResponse(
        success=True,
        message="Project updated",
        data=ProjectOut.model_validate(project).model_dump(mode="json"),
    )


@router.post("/{project_id}/documents", response_model=APIResponse)
async def upload_document(
    project_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(
        Project.id == project_id, Project.is_deleted == False  # noqa: E712
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Ensure upload directory exists
    project_dir = os.path.join(UPLOAD_DIR, str(project_id))
    os.makedirs(project_dir, exist_ok=True)

    # Save file
    file_ext = os.path.splitext(file.filename)[1] if file.filename else ""
    unique_name = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(project_dir, unique_name)

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    # Determine file type
    file_type = file_ext.lstrip(".").lower() if file_ext else "unknown"

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
):
    """Initialize a chunked upload session. Returns upload_id and chunk_size."""
    project = db.query(Project).filter(
        Project.id == project_id, Project.is_deleted == False  # noqa: E712
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    upload_id = str(uuid.uuid4())
    total_chunks = math.ceil(data.file_size / CHUNK_SIZE)

    temp_dir = os.path.join(UPLOAD_DIR, "tmp", upload_id)
    os.makedirs(temp_dir, exist_ok=True)

    _upload_sessions[upload_id] = {
        "project_id": project_id,
        "filename": data.filename,
        "file_size": data.file_size,
        "content_type": data.content_type,
        "total_chunks": total_chunks,
        "chunks_received": set(),
        "temp_dir": temp_dir,
        "created_at": time.time(),
    }

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
):
    """Receive one chunk. chunk_number is 0-indexed and must be sequential."""
    session = _upload_sessions.get(upload_id)
    if not session or session["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="Upload session not found")

    expected = len(session["chunks_received"])
    if chunk_number != expected:
        raise HTTPException(
            status_code=400,
            detail=f"Expected chunk {expected}, got chunk_number={chunk_number}",
        )

    chunk_path = os.path.join(session["temp_dir"], f"chunk_{chunk_number:06d}")
    chunk_data = await chunk.read()
    with open(chunk_path, "wb") as f:
        f.write(chunk_data)

    session["chunks_received"].add(chunk_number)
    chunks_received = len(session["chunks_received"])

    return APIResponse(
        success=True,
        data={"chunks_received": chunks_received, "total_expected": session["total_chunks"]},
    )


@router.post("/{project_id}/documents/upload/{upload_id}/complete", response_model=APIResponse)
async def chunked_upload_complete(
    project_id: int,
    upload_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Reassemble chunks into the final file, create Document record, trigger pipeline."""
    session = _upload_sessions.get(upload_id)
    if not session or session["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="Upload session not found")

    total_chunks = session["total_chunks"]
    chunks_received = len(session["chunks_received"])
    if chunks_received != total_chunks:
        raise HTTPException(
            status_code=400,
            detail=f"Incomplete upload: received {chunks_received}/{total_chunks} chunks",
        )

    # Reassemble into final file
    project_dir = os.path.join(UPLOAD_DIR, str(project_id))
    os.makedirs(project_dir, exist_ok=True)

    filename = session["filename"]
    file_ext = os.path.splitext(filename)[1]
    unique_name = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(project_dir, unique_name)

    with open(file_path, "wb") as out_f:
        for i in range(total_chunks):
            chunk_path = os.path.join(session["temp_dir"], f"chunk_{i:06d}")
            with open(chunk_path, "rb") as in_f:
                out_f.write(in_f.read())

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
    shutil.rmtree(session["temp_dir"], ignore_errors=True)
    _upload_sessions.pop(upload_id, None)

    return APIResponse(
        success=True,
        message="Document uploaded",
        data=DocumentOut.model_validate(doc).model_dump(mode="json"),
    )


@router.get("/{project_id}/documents", response_model=APIResponse)
def list_documents(project_id: int, db: Session = Depends(get_db)):
    docs = db.query(Document).filter(
        Document.project_id == project_id,
        Document.is_deleted == False,  # noqa: E712
    ).all()
    return APIResponse(
        success=True,
        data=[DocumentOut.model_validate(d).model_dump(mode="json") for d in docs],
    )


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(
        Project.id == project_id, Project.is_deleted == False  # noqa: E712
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    project.is_deleted = True
    db.commit()


@router.delete("/{project_id}/documents/{doc_id}", status_code=204)
def delete_document(project_id: int, doc_id: int, db: Session = Depends(get_db)):
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
def run_agents(
    project_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(
        Project.id == project_id, Project.is_deleted == False  # noqa: E712
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    background_tasks.add_task(_run_pipeline, project_id)

    return APIResponse(
        success=True,
        message="Agent pipeline started",
        data={"project_id": project_id, "status": "running"},
    )


@router.post("/{project_id}/pipeline/run", response_model=APIResponse)
def pipeline_run(
    project_id: int,
    background_tasks: BackgroundTasks,
    document_id: int = None,
    pipeline_mode: str = None,
    db: Session = Depends(get_db),
):
    """Start the agent pipeline in the background.

    Query params:
      document_id   — specific document to process (defaults to latest upload)
      pipeline_mode — "spec" | "winest_import" (auto-detected if omitted;
                      .est files always trigger "winest_import")
    """
    project = db.query(Project).filter(
        Project.id == project_id, Project.is_deleted == False  # noqa: E712
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

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
def pipeline_status(project_id: int, db: Session = Depends(get_db)):
    """Return the current pipeline status for each agent (1-6)."""
    project = db.query(Project).filter(
        Project.id == project_id, Project.is_deleted == False  # noqa: E712
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    orchestrator = get_orchestrator(db, project_id)
    statuses = orchestrator.get_pipeline_status()

    # Derive overall status
    status_values = [s["status"] for s in statuses]
    if any(s == "running" for s in status_values):
        overall = "running"
    elif any(s == "failed" for s in status_values):
        overall = "failed"
    elif all(s == "completed" for s in status_values):
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
):
    if agent_number < 1 or agent_number > 7:
        raise HTTPException(status_code=400, detail="agent_number must be between 1 and 7")
    project = db.query(Project).filter(
        Project.id == project_id, Project.is_deleted == False  # noqa: E712
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
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


@router.post("/{project_id}/actuals", response_model=APIResponse)
async def upload_actuals(
    project_id: int,
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
):
    """Upload field actuals as CSV and trigger IMPROVE agent."""
    project = db.query(Project).filter(
        Project.id == project_id, Project.is_deleted == False  # noqa: E712
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    content = await file.read()
    text = content.decode("utf-8", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))

    imported = 0
    for row in reader:
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
        db.add(actual)
        imported += 1

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

    if background_tasks:
        background_tasks.add_task(_run_improve, project_id)

    return APIResponse(
        success=True,
        message=f"Imported {imported} actuals, IMPROVE agent started",
        data={"imported": imported},
    )
