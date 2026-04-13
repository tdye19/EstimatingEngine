"""PDF table extraction and CSI code mapping service.

Deterministic extraction — no LLM involved. Uses pdfplumber for table
detection and regex-based CSI code mapping.
"""

import logging
import re

import pdfplumber
from sqlalchemy.orm import Session

from apex.backend.models.document import Document
from apex.backend.models.spec_section import SpecSection

logger = logging.getLogger("apex.pdf_parser")

# ---------------------------------------------------------------------------
# CSI MasterFormat division lookup
# ---------------------------------------------------------------------------

CSI_DIVISIONS: dict[str, str] = {
    "01": "General Requirements",
    "02": "Existing Conditions",
    "03": "Concrete",
    "04": "Masonry",
    "05": "Metals",
    "06": "Wood, Plastics, and Composites",
    "07": "Thermal and Moisture Protection",
    "08": "Openings",
    "09": "Finishes",
    "10": "Specialties",
    "11": "Equipment",
    "12": "Furnishings",
    "13": "Special Construction",
    "14": "Conveying Equipment",
    "21": "Fire Suppression",
    "22": "Plumbing",
    "23": "HVAC",
    "25": "Integrated Automation",
    "26": "Electrical",
    "27": "Communications",
    "28": "Electronic Safety and Security",
    "31": "Earthwork",
    "32": "Exterior Improvements",
    "33": "Utilities",
    "34": "Transportation",
    "35": "Waterway and Marine Construction",
    "40": "Process Integration",
    "41": "Material Processing and Handling Equipment",
    "42": "Process Heating, Cooling, and Drying Equipment",
    "43": "Process Gas and Liquid Handling",
    "44": "Pollution and Waste Control Equipment",
    "46": "Water and Wastewater Equipment",
    "48": "Electrical Power Generation",
}

# Keyword → CSI division mapping for inference
CSI_KEYWORD_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(concrete|footing|slab|foundation|rebar|formwork)\b", re.I), "03"),
    (re.compile(r"\b(masonry|brick|block|mortar|grout)\b", re.I), "04"),
    (re.compile(r"\b(steel|metal\s+deck|structural\s+steel|joist|iron)\b", re.I), "05"),
    (re.compile(r"\b(wood|lumber|plywood|timber|carpentry|millwork)\b", re.I), "06"),
    (re.compile(r"\b(roofing|waterproof|insulation|sealant|flashing|membrane)\b", re.I), "07"),
    (re.compile(r"\b(door|window|glass|glazing|curtain\s+wall|hardware)\b", re.I), "08"),
    (re.compile(r"\b(drywall|paint|tile|flooring|ceiling|carpet|stucco|plaster)\b", re.I), "09"),
    (re.compile(r"\b(toilet\s+accessory|locker|signage|fire\s+extinguisher)\b", re.I), "10"),
    (re.compile(r"\b(elevator|escalator|lift|conveyor)\b", re.I), "14"),
    (re.compile(r"\b(fire\s+suppression|sprinkler|fire\s+alarm)\b", re.I), "21"),
    (re.compile(r"\b(plumbing|pipe|valve|fixture|sanitary|drain|water\s+heater)\b", re.I), "22"),
    (re.compile(r"\b(hvac|duct|air\s+handler|boiler|chiller|cooling|heating|ahu)\b", re.I), "23"),
    (re.compile(r"\b(electrical|conduit|panel|switchgear|transformer|wiring|circuit)\b", re.I), "26"),
    (re.compile(r"\b(earthwork|excavat|grading|backfill|compaction)\b", re.I), "31"),
    (re.compile(r"\b(paving|asphalt|curb|landscap|fence|sidewalk)\b", re.I), "32"),
    (re.compile(r"\b(utilit|sewer|storm\s+drain|water\s+main|gas\s+line)\b", re.I), "33"),
]

# Table header keywords that indicate a bid-tab / line-item table
_BID_TAB_HEADERS = {
    "item",
    "description",
    "quantity",
    "qty",
    "unit",
    "unit cost",
    "unit price",
    "total",
    "amount",
    "extended",
    "cost",
    "price",
    "csi",
    "division",
    "trade",
    "spec",
    "section",
}

# Column role detection keywords
_COL_ROLES = {
    "description": {"description", "desc", "item description", "work item", "scope"},
    "quantity": {"quantity", "qty", "amount"},
    "unit": {"unit", "uom", "u/m"},
    "unit_cost": {"unit cost", "unit price", "rate", "unit rate", "$/unit"},
    "total_cost": {"total", "extended", "ext cost", "total cost", "total price", "amount"},
    "csi_code": {"csi", "csi code", "division", "spec", "section", "spec section"},
}


class CSICodeMapper:
    """Parse explicit CSI codes and infer from description keywords."""

    # Matches patterns like "03 30 00", "03-30-00", "033000", "03 3000"
    _CSI_REGEX = re.compile(r"\b(\d{2})\s*[-.]?\s*(\d{2})\s*[-.]?\s*(\d{2})\b")

    @staticmethod
    def extract_csi_code(text: str) -> str | None:
        """Extract explicit CSI code from text. Returns formatted 'XX XX XX' or None."""
        m = CSICodeMapper._CSI_REGEX.search(text)
        if m:
            return f"{m.group(1)} {m.group(2)} {m.group(3)}"
        return None

    @staticmethod
    def extract_division(text: str) -> str | None:
        """Extract 2-digit division code from text."""
        code = CSICodeMapper.extract_csi_code(text)
        if code:
            return code[:2]
        return None

    @staticmethod
    def infer_division(description: str) -> str | None:
        """Infer CSI division from description keywords."""
        for pattern, division in CSI_KEYWORD_MAP:
            if pattern.search(description):
                return division
        return None

    @staticmethod
    def map_code(text: str, description: str = "") -> tuple[str | None, str | None]:
        """Return (csi_code, division_number) from explicit code or keyword inference."""
        code = CSICodeMapper.extract_csi_code(text)
        if code:
            return code, code[:2]
        code = CSICodeMapper.extract_csi_code(description)
        if code:
            return code, code[:2]
        div = CSICodeMapper.infer_division(f"{text} {description}")
        if div:
            return None, div
        return None, None


class TableExtractor:
    """Detect bid-tab tables in PDF pages and extract structured line items."""

    @staticmethod
    def is_bid_tab_header(row: list[str]) -> bool:
        """Check if a table row looks like a bid-tab header."""
        if not row:
            return False
        cells = [str(c).strip().lower() for c in row if c]
        matches = sum(1 for c in cells if c in _BID_TAB_HEADERS)
        return matches >= 2

    @staticmethod
    def detect_column_roles(header_row: list[str]) -> dict[int, str]:
        """Map column indices to semantic roles based on header text."""
        roles: dict[int, str] = {}
        for idx, cell in enumerate(header_row):
            if not cell:
                continue
            cell_lower = str(cell).strip().lower()
            for role, keywords in _COL_ROLES.items():
                if cell_lower in keywords or any(kw in cell_lower for kw in keywords):
                    roles[idx] = role
                    break
        return roles

    @staticmethod
    def extract_line_items(
        tables: list[list[list[str]]],
    ) -> list[dict]:
        """Extract structured line items from detected tables."""
        items = []
        for table in tables:
            if not table or len(table) < 2:
                continue

            header = table[0]
            if not TableExtractor.is_bid_tab_header(header):
                continue

            roles = TableExtractor.detect_column_roles(header)
            if not roles:
                continue

            for row in table[1:]:
                if not row or all(not str(c).strip() for c in row):
                    continue

                item: dict = {}
                for idx, role in roles.items():
                    if idx < len(row):
                        val = str(row[idx]).strip() if row[idx] else ""
                        if role in ("quantity", "unit_cost", "total_cost"):
                            # Clean numeric values
                            cleaned = re.sub(r"[,$]", "", val)
                            try:
                                item[role] = float(cleaned)
                            except (ValueError, TypeError):
                                item[role] = None
                        else:
                            item[role] = val

                # Must have at least a description
                if item.get("description"):
                    # Map CSI code
                    text = item.get("csi_code", "")
                    desc = item.get("description", "")
                    csi_code, division = CSICodeMapper.map_code(text, desc)
                    item["csi_code"] = csi_code
                    item["division_number"] = division
                    items.append(item)

        return items


class PDFParserService:
    """Orchestrate PDF table extraction and persist results as SpecSection records."""

    def __init__(self, db: Session):
        self.db = db

    def parse_document(self, document: Document) -> dict:
        """Parse a single PDF document, extracting tables and CSI-mapped line items.

        Returns dict with extracted_items count and spec_sections_created count.
        """
        if not document.file_path:
            return {"status": "error", "message": "No file path for document"}

        if document.file_type not in ("pdf",):
            return {"status": "skipped", "message": f"Not a PDF: {document.file_type}"}

        logger.info("Parsing PDF: %s (doc_id=%d)", document.filename, document.id)

        try:
            all_tables = []
            with pdfplumber.open(document.file_path) as pdf:
                for page in pdf.pages:
                    tables = page.extract_tables()
                    if tables:
                        all_tables.extend(tables)

            items = TableExtractor.extract_line_items(all_tables)
            logger.info("Extracted %d line items from %s", len(items), document.filename)

            # Group items by division and persist as SpecSection records
            sections_created = 0
            by_division: dict[str, list[dict]] = {}
            for item in items:
                div = item.get("division_number") or "00"
                by_division.setdefault(div, []).append(item)

            for div, div_items in by_division.items():
                div_name = CSI_DIVISIONS.get(div, "Unknown")
                section = SpecSection(
                    project_id=document.project_id,
                    document_id=document.id,
                    division_number=div,
                    section_number=f"{div} 00 00",
                    title=f"Division {div} — {div_name} (extracted)",
                    raw_text="\n".join(it.get("description", "") for it in div_items),
                    materials_referenced=[it.get("description") for it in div_items if it.get("description")],
                    in_scope=True,
                )
                self.db.add(section)
                sections_created += 1

            # Mark document as processed
            document.processing_status = "completed"
            self.db.commit()

            return {
                "status": "completed",
                "document_id": document.id,
                "tables_found": len(all_tables),
                "items_extracted": len(items),
                "sections_created": sections_created,
                "items": items,
            }

        except Exception as exc:
            logger.error("PDF parse failed for doc %d: %s", document.id, exc)
            document.processing_status = "error"
            self.db.commit()
            return {"status": "error", "message": str(exc)}

    def parse_project_pdfs(self, project_id: int) -> dict:
        """Parse all unprocessed PDF documents for a project."""
        docs = (
            self.db.query(Document)
            .filter(
                Document.project_id == project_id,
                Document.file_type == "pdf",
                Document.processing_status.in_(["pending", "error"]),
            )
            .all()
        )

        results = []
        for doc in docs:
            result = self.parse_document(doc)
            results.append(result)

        return {
            "project_id": project_id,
            "documents_processed": len(results),
            "results": results,
        }
