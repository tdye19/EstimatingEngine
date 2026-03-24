"""Project management router."""

import os
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
from apex.backend.services.agent_orchestrator import AgentOrchestrator
from apex.backend.utils.auth import require_auth
from apex.backend.utils.schemas import (
    ProjectCreate, ProjectUpdate, ProjectOut, DocumentOut, APIResponse,
    PipelineStatusOut, AgentStepStatus,
)

router = APIRouter(prefix="/api/projects", tags=["projects"], dependencies=[Depends(require_auth)])

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")


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


def _run_pipeline(project_id: int, document_id: int = None):
    """Background task to run agent pipeline."""
    from apex.backend.db.database import SessionLocal
    db = SessionLocal()
    try:
        orchestrator = AgentOrchestrator(db, project_id)
        orchestrator.run_pipeline(document_id=document_id)
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
    db: Session = Depends(get_db),
):
    """Start the agent pipeline in the background.

    Accepts an optional *document_id* query param; defaults to the latest
    uploaded document for the project.
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

    background_tasks.add_task(_run_pipeline, project_id, document_id)

    return APIResponse(
        success=True,
        message="Pipeline started",
        data={"status": "started", "project_id": project_id, "document_id": document_id},
    )


@router.get("/{project_id}/pipeline/status", response_model=PipelineStatusOut)
def pipeline_status(project_id: int, db: Session = Depends(get_db)):
    """Return the current pipeline status for each agent (1-6)."""
    project = db.query(Project).filter(
        Project.id == project_id, Project.is_deleted == False  # noqa: E712
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    orchestrator = AgentOrchestrator(db, project_id)
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
        orchestrator = AgentOrchestrator(db, project_id)
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
            orchestrator = AgentOrchestrator(session, pid)
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
