"""Document processing tools for Agent 1."""

import os
import re
import logging

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
            result["pages"].append({
                "page_number": page_num + 1,
                "text": text.strip(),
            })
        doc.close()
    except ImportError:
        # Fallback: try pdfplumber
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                result["total_pages"] = len(pdf.pages)
                for i, page in enumerate(pdf.pages):
                    text = page.extract_text() or ""
                    result["pages"].append({
                        "page_number": i + 1,
                        "text": text.strip(),
                    })
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


def file_classifier_tool(filename: str, text_sample: str = "") -> str:
    """Classify a document based on filename and content sample.

    Returns one of: spec, drawing, addendum, rfi, schedule, general
    """
    fname_lower = filename.lower()
    text_lower = text_sample.lower()[:2000]

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
