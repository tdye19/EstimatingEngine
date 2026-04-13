"""Spec indexing pipeline: embed all SpecSections into ChromaDB.

Called:
  - Lazily at the start of Agent 3 / Agent 6 (first run auto-indexes)
  - Explicitly via POST /api/projects/{id}/specs/index (re-index on demand)

Design:
  - Already-indexed projects are skipped unless force=True
  - Chunks in batches of BATCH_SIZE to bound memory usage
  - Graceful degradation: returns 0 chunks if embedding unavailable
"""

import logging

from sqlalchemy.orm import Session

logger = logging.getLogger("apex.retrieval.pipeline")

BATCH_SIZE = 50    # OpenAI embedding batch size per request


def index_project_specs(db: Session, project_id: int, force: bool = False) -> int:
    """Embed all SpecSections for *project_id* and store in ChromaDB.

    Args:
        db: Active SQLAlchemy session.
        project_id: Project to index.
        force: When True, re-index even if collection already exists.

    Returns:
        Number of chunks indexed (0 if already indexed and force=False,
        or 0 on any non-fatal error).
    """
    from apex.backend.models.spec_section import SpecSection
    from apex.backend.retrieval.chunker import chunk_spec_section
    from apex.backend.retrieval.embedder import embed_texts, is_available
    from apex.backend.retrieval.store import (
        collection_exists,
        delete_project_collection,
        upsert_chunks,
    )

    if not is_available():
        logger.info(
            "Spec indexing skipped: OPENAI_API_KEY not configured. "
            "Set it to enable spec retrieval in Agent 3 and Agent 6."
        )
        return 0

    if not force and collection_exists(project_id):
        logger.debug(f"Project {project_id} already indexed — skipping (use force=True to re-index)")
        return 0

    if force:
        # Delete existing vectors so stale chunks from deleted/shortened
        # sections can never surface in search results after re-indexing.
        delete_project_collection(project_id)
        logger.info(f"Project {project_id}: cleared existing vectors for clean re-index")

    sections = (
        db.query(SpecSection)
        .filter(
            SpecSection.project_id == project_id,
            SpecSection.is_deleted == False,  # noqa: E712
        )
        .all()
    )

    if not sections:
        logger.info(f"Project {project_id}: no SpecSections found — nothing to index")
        return 0

    # Chunk all sections
    all_chunks = []
    for section in sections:
        all_chunks.extend(chunk_spec_section(section))

    if not all_chunks:
        logger.info(f"Project {project_id}: all SpecSections have no raw_text — nothing to index")
        return 0

    logger.info(
        f"Project {project_id}: indexing {len(all_chunks)} chunks "
        f"from {len(sections)} spec sections"
    )

    total_indexed = 0
    try:
        for i in range(0, len(all_chunks), BATCH_SIZE):
            batch = all_chunks[i : i + BATCH_SIZE]
            texts = [c.text for c in batch]
            embeddings = embed_texts(texts)
            upsert_chunks(project_id, batch, embeddings)
            total_indexed += len(batch)
            logger.debug(f"Project {project_id}: indexed batch {i//BATCH_SIZE + 1} ({len(batch)} chunks)")
    except Exception as exc:
        logger.error(f"Project {project_id}: indexing failed after {total_indexed} chunks — {exc}")
        # Return whatever we managed to index rather than raising
        return total_indexed

    logger.info(f"Project {project_id}: indexing complete — {total_indexed} chunks in ChromaDB")
    return total_indexed
