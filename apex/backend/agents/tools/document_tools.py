"""Document processing tools for Agent 1."""

import logging
import os
import re

logger = logging.getLogger("apex.tools.document")


def pdf_reader_tool(file_path: str) -> dict:
    """Read a PDF file and extract text per page.

    Returns dict with pages list, each containing page_number and text.
    """
    result = {"pages": [], "total_pages": 0, "error": None}

    if not os.path.exists(file_path):
        result["error"] = f"File not found: {file_path}"
        return result

    try:
        import fitz  # PyMuPDF

        doc = fitz.open(file_path)
        result["total_pages"] = len(doc)
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            result["pages"].append(
                {
                    "page_number": page_num + 1,
                    "text": text.strip(),
                }
            )
        doc.close()
    except ImportError:
        # Fallback: try pdfplumber
        try:
            import pdfplumber

            with pdfplumber.open(file_path) as pdf:
                result["total_pages"] = len(pdf.pages)
                for i, page in enumerate(pdf.pages):
                    text = page.extract_text() or ""
                    result["pages"].append(
                        {
                            "page_number": i + 1,
                            "text": text.strip(),
                        }
                    )
        except ImportError:
            result["error"] = "No PDF library available (install PyMuPDF or pdfplumber)"
    except Exception as e:
        result["error"] = str(e)

    return result


def docx_reader_tool(file_path: str) -> dict:
    """Read a DOCX file and extract text by paragraph."""
    result = {"paragraphs": [], "total_paragraphs": 0, "error": None}

    if not os.path.exists(file_path):
        result["error"] = f"File not found: {file_path}"
        return result

    try:
        from docx import Document

        doc = Document(file_path)
        for para in doc.paragraphs:
            if para.text.strip():
                result["paragraphs"].append(para.text.strip())
        result["total_paragraphs"] = len(result["paragraphs"])
    except ImportError:
        result["error"] = "python-docx not installed"
    except Exception as e:
        result["error"] = str(e)

    return result


# ---------------------------------------------------------------------------
# Work Scope detection (Sprint 18.3.3.2)
#
# Christman-style Work Scope PDFs (KCCU Volume 2 shape) previously fell
# through to the content-based "spec" branch because their body text
# mentions "section"/"division"/"part 1". That pollutes Agent 2's spec
# parsing, which filters on Document.classification == "spec"
# (agent_2_spec_parser.py:316) and additionally pulls in "general"/None
# (agent_2_spec_parser.py:328). Tagging these docs "work_scope" keeps
# them out of both selectors. Agent 2B runs its own per-document
# classifier and is NOT gated on Document.classification, so this tag
# is purely defensive for Agent 2's output quality.
# ---------------------------------------------------------------------------

_WORK_SCOPE_FILENAME_HINTS: tuple[str, ...] = (
    "work scope",
    "work scopes",
    "workscopes",
    "work_scopes",
    "work-scopes",
)

# "WC 00", "WC 28A", etc. — 1-2 digits with optional letter suffix, followed
# by a space or hyphen (the KCCU table-of-contents / section-header shape).
_WC_NUMBER_RE = re.compile(r"\bWC\s+\d{1,2}[A-Z]?[\s\-]", re.IGNORECASE)

# "Work Included:" as a line-start marker (the bold subsection heading inside
# each WC block). MULTILINE so it matches on any line, tolerating leading
# whitespace that PDF text extraction often introduces.
_WORK_INCLUDED_LINE_RE = re.compile(r"(?m)^\s*Work Included:")


def _is_work_scope_document(filename: str, text_sample: str) -> bool:
    """Detect a Christman-style Work Scopes document.

    Filename signal (any one match → True):
        * substring match against _WORK_SCOPE_FILENAME_HINTS
        * filenames containing BOTH "volume" and "scope" (e.g.
          "KCCU Volume 2 - Work Scopes")

    Content signals (≥ 2 required when filename doesn't match):
        1. literal "Work Category No." (with period) in the body
        2. _WC_NUMBER_RE match ("WC 00", "WC 28A", ...)
        3. both "Proposal Section" AND "Work Category Description"
           (the Christman table header)
        4. a line starting with "Work Included:"

    Single-signal matches are deliberately insufficient — specs that
    mention "Work Category" once in a coordination note must not trigger.

    Fails closed: any unexpected exception returns False so downstream
    classification of non-work-scope docs is never broken.
    """
    try:
        fname_lower = (filename or "").lower()

        if any(hint in fname_lower for hint in _WORK_SCOPE_FILENAME_HINTS):
            return True
        if "volume" in fname_lower and "scope" in fname_lower:
            return True

        text = text_sample or ""
        text_lower = text.lower()

        signals = 0
        if "work category no." in text_lower:
            signals += 1
        if _WC_NUMBER_RE.search(text):
            signals += 1
        if "proposal section" in text_lower and "work category description" in text_lower:
            signals += 1
        if _WORK_INCLUDED_LINE_RE.search(text):
            signals += 1

        return signals >= 2
    except Exception:  # pragma: no cover - defensive
        return False


def file_classifier_tool(filename: str, text_sample: str = "") -> str:
    """Classify a document based on filename and content sample.

    Returns one of: winest, work_scope, takeoff, spec, drawing, addendum,
    rfi, schedule, general.

    Ordering: winest → work_scope → spec → drawing → fallback.
    WinEst always wins; work_scope fires before the "spec" branch so
    Christman-style Work Scope PDFs don't pollute Agent 2's spec-parsing
    filter (see _is_work_scope_document docstring for the full rationale).
    """
    fname_lower = filename.lower()
    text_lower = text_sample.lower()[:2000]

    # WinEst (Sprint 18.3.3.2) — Agent 1 normally short-circuits .est files
    # before calling this tool, but when the tool is invoked directly (tests
    # or ad-hoc tooling) .est must not fall through to content-based branches.
    if fname_lower.endswith(".est"):
        return "winest"

    # Work Scope (Sprint 18.3.3.2) — fires before "spec" so KCCU-style Work
    # Scope PDFs don't get spec-parsed. See module-level comment above.
    if _is_work_scope_document(filename, text_sample):
        return "work_scope"

    # Filename-based classification
    if any(kw in fname_lower for kw in ["takeoff", "estimate"]) and any(
        fname_lower.endswith(ext) for ext in (".xlsx", ".csv", ".xls")
    ):
        return "takeoff"
    if any(kw in fname_lower for kw in ["spec", "specification", "section"]):
        return "spec"
    if any(kw in fname_lower for kw in ["drawing", "dwg", "plan", "sheet", "detail"]):
        return "drawing"
    if any(kw in fname_lower for kw in ["addend", "amendment", "revision"]):
        return "addendum"
    if any(kw in fname_lower for kw in ["rfi", "request for information"]):
        return "rfi"
    if any(kw in fname_lower for kw in ["schedule", "timeline"]):
        return "schedule"

    # Content-based classification
    if any(kw in text_lower for kw in ["section", "division", "part 1", "part 2", "part 3", "masterformat"]):
        return "spec"
    if any(kw in text_lower for kw in ["detail", "elevation", "plan view", "scale:"]):
        return "drawing"
    if re.search(r"addend(um|a)\s*(no|#|\d)", text_lower):
        return "addendum"

    return "general"
