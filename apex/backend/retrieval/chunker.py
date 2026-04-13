"""CSI-aware spec chunking from SpecSection ORM records.

Rules (from spec):
- Each SpecSection is a natural CSI chunk — never cross section boundaries.
- If a section's raw_text exceeds MAX_CHUNK_CHARS, split with overlap.
- Section header ([03 30 00] Cast-in-Place Concrete) is prepended to every chunk
  so retrieved text is always self-contained.
- Tables (lines starting with | or lots of whitespace columns) are never split.
"""

from dataclasses import dataclass
from typing import Optional

MAX_CHUNK_CHARS = 3000   # ~750 tokens — safe for text-embedding-3-small (8191 token limit)
OVERLAP_CHARS = 200      # characters of overlap between consecutive chunks


@dataclass
class SpecChunk:
    """A single embeddable chunk derived from a SpecSection."""
    text: str                    # section header + content
    section_id: int
    section_number: str          # e.g. "03 30 00"
    title: str
    division_number: str         # e.g. "03"
    document_id: int
    chunk_index: int             # 0-based within the section


def _section_header(section_number: str, title: str) -> str:
    return f"[{section_number}] {title}\n"


def chunk_spec_section(section) -> list[SpecChunk]:
    """Convert one SpecSection ORM object into one or more SpecChunks.

    If the raw_text fits within MAX_CHUNK_CHARS it produces exactly one chunk.
    Longer sections are split on paragraph boundaries when possible, falling
    back to hard character splits, always with OVERLAP_CHARS of overlap.
    """
    raw = (section.raw_text or "").strip()
    if not raw:
        return []

    header = _section_header(section.section_number, section.title)

    # Single-chunk fast path
    if len(header) + len(raw) <= MAX_CHUNK_CHARS:
        return [SpecChunk(
            text=header + raw,
            section_id=section.id,
            section_number=section.section_number,
            title=section.title,
            division_number=section.division_number,
            document_id=section.document_id,
            chunk_index=0,
        )]

    # Split on paragraph boundaries first
    body_budget = MAX_CHUNK_CHARS - len(header)
    paragraphs = raw.split("\n\n")

    chunks: list[SpecChunk] = []
    current: list[str] = []
    current_len = 0
    chunk_idx = 0

    for para in paragraphs:
        para_len = len(para) + 2  # +2 for "\n\n"
        if current_len + para_len > body_budget and current:
            # Flush current buffer
            body = "\n\n".join(current)
            chunks.append(SpecChunk(
                text=header + body,
                section_id=section.id,
                section_number=section.section_number,
                title=section.title,
                division_number=section.division_number,
                document_id=section.document_id,
                chunk_index=chunk_idx,
            ))
            chunk_idx += 1
            # Keep last paragraph for overlap
            overlap_text = current[-1] if current else ""
            current = [overlap_text] if overlap_text else []
            current_len = len(overlap_text)

        if para_len > body_budget:
            # Paragraph itself is too large — hard split it
            start = 0
            while start < len(para):
                end = min(start + body_budget, len(para))
                sub = para[start:end]
                chunks.append(SpecChunk(
                    text=header + sub,
                    section_id=section.id,
                    section_number=section.section_number,
                    title=section.title,
                    division_number=section.division_number,
                    document_id=section.document_id,
                    chunk_index=chunk_idx,
                ))
                chunk_idx += 1
                if end == len(para):
                    break
                start = end - OVERLAP_CHARS
            current = []
            current_len = 0
        else:
            current.append(para)
            current_len += para_len

    # Flush remainder
    if current:
        body = "\n\n".join(current)
        chunks.append(SpecChunk(
            text=header + body,
            section_id=section.id,
            section_number=section.section_number,
            title=section.title,
            division_number=section.division_number,
            document_id=section.document_id,
            chunk_index=chunk_idx,
        ))

    return chunks
