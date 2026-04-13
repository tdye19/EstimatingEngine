"""ChromaDB vector store with project-level namespace isolation.

One ChromaDB collection per project: collection name = "project_{project_id}".
Persistent storage at CHROMA_DIR (default: ./chroma_db, configurable via env).

Cosine similarity space is used so distances map directly to similarity scores.
ChromaDB distance in cosine mode = 1 - cosine_similarity, so:
    similarity_score = 1.0 - distance
"""

import logging
import os

logger = logging.getLogger("apex.retrieval.store")

CHROMA_DIR: str = os.getenv("CHROMA_DB_DIR", "./chroma_db")
_COSINE_METADATA = {"hnsw:space": "cosine"}


def _client():
    """Return a shared ChromaDB PersistentClient."""
    import chromadb

    return chromadb.PersistentClient(path=CHROMA_DIR)


def _collection_name(project_id: int) -> str:
    return f"project_{project_id}"


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


def upsert_chunks(
    project_id: int,
    chunks: list,  # list[SpecChunk]
    embeddings: list[list[float]],
) -> int:
    """Upsert chunks + embeddings into the project's ChromaDB collection.

    IDs are deterministic: proj{pid}_sec{sid}_chunk{idx}
    Existing chunks with the same ID are overwritten (safe for re-indexing).
    """
    if not chunks:
        return 0

    client = _client()
    col = client.get_or_create_collection(
        name=_collection_name(project_id),
        metadata=_COSINE_METADATA,
    )

    ids = [f"proj{project_id}_sec{c.section_id}_chunk{c.chunk_index}" for c in chunks]
    documents = [c.text for c in chunks]
    metadatas = [
        {
            "section_id": c.section_id,
            "section_number": c.section_number,
            "title": c.title,
            "division_number": c.division_number,
            "document_id": c.document_id,
            "chunk_index": c.chunk_index,
        }
        for c in chunks
    ]

    col.upsert(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)
    logger.debug(f"Upserted {len(chunks)} chunks for project {project_id}")
    return len(chunks)


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def query_collection(
    project_id: int,
    query_embedding: list[float],
    top_k: int = 5,
) -> list[dict]:
    """Return top_k most similar chunks for a project.

    Returns a list of dicts with keys:
        text, section_number, title, division_number, document_id, similarity_score
    Returns [] if the collection doesn't exist or is empty.
    """
    client = _client()
    col_name = _collection_name(project_id)

    try:
        col = client.get_collection(col_name)
    except Exception:
        logger.debug(f"No ChromaDB collection for project {project_id} — not yet indexed")
        return []

    try:
        results = col.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, col.count()),
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:
        logger.warning(f"ChromaDB query failed for project {project_id}: {exc}")
        return []

    retrieved = []
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]

    for doc, meta, dist in zip(docs, metas, dists, strict=False):
        # cosine space: similarity = 1 - distance
        similarity = round(max(0.0, 1.0 - float(dist)), 4)
        retrieved.append(
            {
                "text": doc,
                "section_number": meta.get("section_number", ""),
                "title": meta.get("title", ""),
                "division_number": meta.get("division_number", ""),
                "document_id": meta.get("document_id", 0),
                "similarity_score": similarity,
            }
        )

    return retrieved


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def collection_exists(project_id: int) -> bool:
    """Return True if the project collection exists and has at least one chunk."""
    try:
        client = _client()
        col = client.get_collection(_collection_name(project_id))
        return col.count() > 0
    except Exception:
        return False


def collection_count(project_id: int) -> int:
    """Return number of chunks indexed for a project (0 if none)."""
    try:
        client = _client()
        col = client.get_collection(_collection_name(project_id))
        return col.count()
    except Exception:
        return 0


def delete_project_collection(project_id: int) -> bool:
    """Delete all chunks for a project. Returns True if deleted, False if not found."""
    try:
        client = _client()
        client.delete_collection(_collection_name(project_id))
        logger.info(f"Deleted ChromaDB collection for project {project_id}")
        return True
    except Exception:
        return False
