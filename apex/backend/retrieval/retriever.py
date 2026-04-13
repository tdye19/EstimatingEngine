"""Public retrieval API.

Primary entrypoint:
    search(project_id, query, top_k=5) -> list[RetrievedChunk]

Secondary helpers used by agents:
    format_for_agent(chunks) -> str   — formats chunks as REFERENCE MATERIAL block
    search_multi(project_id, queries, top_k_each) -> list[RetrievedChunk]  — deduplicated
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger("apex.retrieval.retriever")


@dataclass
class RetrievedChunk:
    """A single spec chunk returned by semantic search."""
    text: str
    section_number: str
    title: str
    division_number: str
    document_id: int
    similarity_score: float


def search(project_id: int, query: str, top_k: int = 5) -> list[RetrievedChunk]:
    """Search for spec chunks relevant to *query* within *project_id*.

    Returns an empty list (not raises) if:
    - OPENAI_API_KEY is not configured
    - The project has not been indexed yet
    - Any other retrieval error

    Performance target: <500ms (embedding + ChromaDB query).
    """
    from apex.backend.retrieval.embedder import embed_texts, is_available
    from apex.backend.retrieval.store import query_collection

    if not is_available():
        logger.debug("Retrieval skipped: OPENAI_API_KEY not configured")
        return []

    try:
        embeddings = embed_texts([query])
        query_embedding = embeddings[0]
    except Exception as exc:
        logger.warning(f"Retrieval embedding failed for query '{query[:60]}...': {exc}")
        return []

    try:
        raw = query_collection(project_id, query_embedding, top_k)
    except Exception as exc:
        logger.warning(f"Retrieval store query failed for project {project_id}: {exc}")
        return []

    return [
        RetrievedChunk(
            text=r["text"],
            section_number=r["section_number"],
            title=r["title"],
            division_number=r["division_number"],
            document_id=r["document_id"],
            similarity_score=r["similarity_score"],
        )
        for r in raw
    ]


def search_multi(
    project_id: int,
    queries: list[str],
    top_k_each: int = 3,
    min_score: float = 0.3,
) -> list[RetrievedChunk]:
    """Run multiple queries and return deduplicated results sorted by score.

    Deduplication key: (section_number, chunk text[:100]).
    Chunks below min_score are filtered out.
    """
    seen: set[str] = set()
    merged: list[RetrievedChunk] = []

    for q in queries:
        for chunk in search(project_id, q, top_k=top_k_each):
            if chunk.similarity_score < min_score:
                continue
            dedup_key = f"{chunk.section_number}:{chunk.text[:100]}"
            if dedup_key not in seen:
                seen.add(dedup_key)
                merged.append(chunk)

    # Sort by similarity descending
    merged.sort(key=lambda c: c.similarity_score, reverse=True)
    return merged


def format_for_agent(chunks: list[RetrievedChunk], label: str = "REFERENCE MATERIAL") -> str:
    """Format retrieved chunks as a clearly-labelled REFERENCE MATERIAL block.

    The spec requires:
    - Clearly separated from instructions
    - Labeled as "REFERENCE MATERIAL"
    - Include citations (section number)
    """
    if not chunks:
        return ""

    lines = [
        f"=== {label} (from project specifications) ===",
    ]
    for i, chunk in enumerate(chunks, 1):
        lines.append(
            f"\n[REF {i}] Section {chunk.section_number} — {chunk.title}"
        )
        # Indent the spec text for visual separation
        for line in chunk.text.split("\n"):
            lines.append(f"  {line}")
        lines.append(
            f"  [Citation: Spec Section {chunk.section_number} | Score: {chunk.similarity_score:.2f}]"
        )
    lines.append(f"\n=== END {label} ===\n")

    return "\n".join(lines)
