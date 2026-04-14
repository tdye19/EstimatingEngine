"""Spec Retrieval API — search and index endpoints.

Endpoints:
    POST /api/projects/{project_id}/specs/search  — semantic search over spec chunks
    POST /api/projects/{project_id}/specs/index   — (re-)index all spec sections
    GET  /api/projects/{project_id}/specs/status  — index status + chunk count
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apex.backend.db.database import get_db
from apex.backend.models.user import User
from apex.backend.utils.auth import get_authorized_project, require_auth

logger = logging.getLogger("apex.routers.retrieval")

router = APIRouter(
    prefix="/api/projects",
    tags=["retrieval"],
)


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class SpecSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, description="Natural language query")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of results to return")


class SpecChunkResult(BaseModel):
    text: str
    section_number: str
    title: str
    division_number: str
    similarity_score: float


class SpecSearchResponse(BaseModel):
    results: list[SpecChunkResult]
    query: str
    project_id: int
    total_results: int


class IndexResponse(BaseModel):
    success: bool
    chunks_indexed: int
    project_id: int
    message: str


class IndexStatusResponse(BaseModel):
    project_id: int
    indexed: bool
    chunk_count: int
    embedding_available: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/{project_id}/specs/search", response_model=SpecSearchResponse)
def search_specs(
    project_id: int,
    request: SpecSearchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    """Semantic search over project specification chunks.

    Returns up to top_k spec text snippets with source citations.
    Performance target: <500ms.
    """
    from apex.backend.retrieval.retriever import search

    get_authorized_project(project_id, user, db)

    logger.info(f"Spec search: project_id={project_id} query='{request.query[:60]}' top_k={request.top_k}")

    try:
        chunks = search(project_id, request.query, top_k=request.top_k)
    except Exception as exc:
        logger.error(f"Spec search failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Search failed: {exc}") from exc

    results = [
        SpecChunkResult(
            text=c.text,
            section_number=c.section_number,
            title=c.title,
            division_number=c.division_number,
            similarity_score=c.similarity_score,
        )
        for c in chunks
    ]

    return SpecSearchResponse(
        results=results,
        query=request.query,
        project_id=project_id,
        total_results=len(results),
    )


@router.post("/{project_id}/specs/index", response_model=IndexResponse)
def index_specs(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    """(Re-)index all parsed spec sections for a project into ChromaDB.

    Deletes existing vectors before re-indexing so stale chunks from
    deleted/shortened sections are never returned by search.
    """
    from apex.backend.retrieval.pipeline import index_project_specs

    get_authorized_project(project_id, user, db)

    logger.info(f"Spec index requested: project_id={project_id}")

    try:
        count = index_project_specs(db, project_id, force=True)
    except Exception as exc:
        logger.error(f"Spec indexing failed for project {project_id}: {exc}")
        raise HTTPException(status_code=500, detail=f"Indexing failed: {exc}") from exc

    if count == 0:
        from apex.backend.retrieval.embedder import is_available

        if not is_available():
            msg = "OPENAI_API_KEY not configured — indexing skipped."
        else:
            msg = "No spec sections found to index. Run the pipeline first to parse specs."
    else:
        msg = f"Successfully indexed {count} chunks from project specifications."

    return IndexResponse(
        success=True,
        chunks_indexed=count,
        project_id=project_id,
        message=msg,
    )


@router.get("/{project_id}/specs/status", response_model=IndexStatusResponse)
def spec_index_status(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth),
):
    """Check whether spec sections have been indexed for a project."""
    from apex.backend.retrieval.embedder import is_available
    from apex.backend.retrieval.store import collection_count

    get_authorized_project(project_id, user, db)

    count = collection_count(project_id)
    return IndexStatusResponse(
        project_id=project_id,
        indexed=count > 0,
        chunk_count=count,
        embedding_available=is_available(),
    )
