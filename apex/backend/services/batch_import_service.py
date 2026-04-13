"""Batch import service for processing zip archives of historical estimate files.

Handles the full lifecycle:
  1. Extracting a zip archive to a temp directory
  2. Auto-detecting file types and grouping by subfolder (one folder = one project)
  3. Creating DocumentGroup / Document / DocumentAssociation / EstimateLibraryEntry records
  4. Parsing WinEst files into HistoricalLineItem records
  5. Optionally running Agent 1 ingestion on spec PDFs
"""

import logging
import os
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy.orm import Session

from apex.backend.config import UPLOAD_DIR
from apex.backend.models.document import Document
from apex.backend.models.document_association import DocumentAssociation, DocumentGroup
from apex.backend.models.estimate_library import EstimateLibraryEntry
from apex.backend.models.historical_line_item import HistoricalLineItem
from apex.backend.models.project import Project
from apex.backend.services.line_item_normalizer import LineItemNormalizer
from apex.backend.utils.csi_utils import CSI_DIVISION_NAMES
from apex.backend.utils.winest_parser import is_winest_xlsx, parse_winest_file

logger = logging.getLogger("apex.batch_import")


# ---------------------------------------------------------------------------
# Pydantic result model
# ---------------------------------------------------------------------------


class BatchImportResult(BaseModel):
    total_files: int
    groups_created: int
    files_by_type: dict[str, int]  # e.g. {"winest": 3, "spec": 5}
    library_entries_created: int
    errors: list[str]


# ---------------------------------------------------------------------------
# CSI auto-mapping helpers
# ---------------------------------------------------------------------------

# Keyword → two-digit CSI division string (keys match CSI_DIVISION_NAMES)
_CSI_KEYWORD_MAP: dict[str, str] = {
    # Division 03 — Concrete
    "concrete": "03",
    "rebar": "03",
    "formwork": "03",
    "reinforc": "03",
    # Division 04 — Masonry
    "masonry": "04",
    "brick": "04",
    "block": "04",
    "mortar": "04",
    # Division 05 — Metals
    "steel": "05",
    "metal": "05",
    "structural": "05",
    "joist": "05",
    # Division 06 — Wood
    "lumber": "06",
    "framing": "06",
    "plywood": "06",
    "carpent": "06",
    # Division 07 — Thermal & Moisture
    "roofing": "07",
    "waterproof": "07",
    "insulation": "07",
    "flashing": "07",
    "sealant": "07",
    "firestop": "07",
    # Division 08 — Openings
    "door": "08",
    "window": "08",
    "glazing": "08",
    "storefront": "08",
    "hardware": "08",
    # Division 09 — Finishes
    "drywall": "09",
    "gypsum": "09",
    "paint": "09",
    "floor": "09",
    "carpet": "09",
    "tile": "09",
    "ceiling": "09",
    # Division 10 — Specialties
    "signage": "10",
    "toilet": "10",
    "partition": "10",
    # Division 21 — Fire Suppression
    "sprinkler": "21",
    "fire suppression": "21",
    # Division 22 — Plumbing
    "plumbing": "22",
    "pipe": "22",
    "drain": "22",
    "fixture": "22",
    # Division 23 — HVAC
    "hvac": "23",
    "mechanical": "23",
    "duct": "23",
    "ventilat": "23",
    # Division 26 — Electrical
    "electrical": "26",
    "wiring": "26",
    "conduit": "26",
    "panel": "26",
    "lighting": "26",
    # Division 27 — Communications
    "data": "27",
    "telecom": "27",
    "communicat": "27",
    # Division 31 — Earthwork
    "earthwork": "31",
    "grading": "31",
    "excavat": "31",
    "backfill": "31",
    # Division 32 — Exterior Improvements
    "paving": "32",
    "landscap": "32",
    "sidewalk": "32",
    # Division 33 — Utilities
    "utilities": "33",
    "sewer": "33",
    "water main": "33",
}


def _auto_map_csi(
    description: str,
) -> tuple[str | None, int | None, str | None]:
    """Best-effort CSI mapping based on description keywords.

    Returns (csi_code, division_int, division_name) or (None, None, None).
    """
    lower = description.lower()
    for keyword, div in _CSI_KEYWORD_MAP.items():
        if keyword in lower:
            div_name = CSI_DIVISION_NAMES.get(div)
            return (f"{div} 00 00", int(div), div_name)
    return (None, None, None)


# ---------------------------------------------------------------------------
# File-type detection
# ---------------------------------------------------------------------------

# Maps extension → (metric_type, document_role)
_EXT_MAP: dict[str, tuple[str, str]] = {
    "est": ("winest", "winest_bid"),
    "pdf": ("spec", "spec"),
    "docx": ("spec", "spec"),
    "doc": ("spec", "manual"),
    "csv": ("bid_tab", "bid_tab"),
    "txt": ("other", "other"),
    "rtf": ("other", "other"),
}


def _detect_file_type(file_path: str) -> tuple[str, str]:
    """Return (metric_type, document_role) for a file path.

    For .xlsx/.xls files, sniffs headers to determine if it is a WinEst export.
    """
    ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""

    if ext == "est":
        return "winest", "winest_bid"

    if ext in ("xlsx", "xls"):
        try:
            if is_winest_xlsx(file_path):
                return "winest", "winest_bid"
        except Exception:
            pass
        return "spreadsheet", "other"

    return _EXT_MAP.get(ext, ("other", "other"))


# ---------------------------------------------------------------------------
# BatchImportService
# ---------------------------------------------------------------------------


class BatchImportService:
    """Processes zip archives of historical project documents."""

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def process_zip(
        self,
        zip_path: str,
        user_id: int,
        db: Session,
    ) -> BatchImportResult:
        """Extract *zip_path*, detect file types, group by folder, and persist DB records.

        Each top-level subfolder inside the zip is treated as one project group.
        Files that live directly in the zip root are collected under a synthetic
        "_root" group.

        Returns a :class:`BatchImportResult` summarising what was found.
        """
        errors: list[str] = []
        files_by_type: dict[str, int] = {}
        groups_created = 0
        library_entries_created = 0
        total_files = 0

        extract_dir = tempfile.mkdtemp(prefix="apex_batch_")
        try:
            # Extract ----------------------------------------------------------------
            try:
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(extract_dir)
            except zipfile.BadZipFile as exc:
                return BatchImportResult(
                    total_files=0,
                    groups_created=0,
                    files_by_type={},
                    library_entries_created=0,
                    errors=[f"Invalid zip file: {exc}"],
                )

            # Collect files, keyed by their immediate parent folder -----------------
            groups: dict[str, list[str]] = {}
            for root, _dirs, filenames in os.walk(extract_dir):
                for fname in filenames:
                    if fname.startswith(".") or fname.startswith("__"):
                        continue
                    full_path = os.path.join(root, fname)
                    rel_path = os.path.relpath(full_path, extract_dir)
                    parts = rel_path.replace("\\", "/").split("/")
                    group_key = parts[0] if len(parts) > 1 else "_root"
                    groups.setdefault(group_key, []).append(full_path)

            # Process each group -----------------------------------------------------
            for group_name, file_paths in groups.items():
                try:
                    result = self._create_group(
                        group_name=group_name,
                        file_paths=file_paths,
                        user_id=user_id,
                        db=db,
                    )
                    groups_created += 1
                    library_entries_created += 1
                    total_files += result["file_count"]
                    for ftype, cnt in result["files_by_type"].items():
                        files_by_type[ftype] = files_by_type.get(ftype, 0) + cnt
                    errors.extend(result["errors"])
                except Exception as exc:
                    logger.exception("Error creating group '%s': %s", group_name, exc)
                    errors.append(f"Group '{group_name}': {exc}")

        finally:
            shutil.rmtree(extract_dir, ignore_errors=True)

        return BatchImportResult(
            total_files=total_files,
            groups_created=groups_created,
            files_by_type=files_by_type,
            library_entries_created=library_entries_created,
            errors=errors,
        )

    def process_winest_file(
        self,
        doc_association_id: int,
        db: Session,
    ) -> list[HistoricalLineItem]:
        """Parse the WinEst file attached to *doc_association_id* and persist line items.

        For each line item the method:
        - Auto-maps CSI code from description if the file did not supply one
        - Calculates productivity_rate = labor_hours / quantity when both are present
        - Denormalises project_type, building_type, location_state from the
          parent EstimateLibraryEntry

        Marks the DocumentAssociation as parsed=True on success.

        Returns the list of created :class:`HistoricalLineItem` instances.
        Raises ValueError on lookup failures or parse errors.
        """
        assoc = db.query(DocumentAssociation).filter(DocumentAssociation.id == doc_association_id).first()
        if not assoc:
            raise ValueError(f"DocumentAssociation {doc_association_id} not found")

        doc = assoc.document
        if not doc:
            raise ValueError(f"Document not found for association {doc_association_id}")

        library_entry: EstimateLibraryEntry | None = assoc.library_entry

        # Parse -------------------------------------------------------------------
        parse_result = parse_winest_file(doc.file_path)
        if not parse_result["success"]:
            err_msg = parse_result.get("error") or "Parse failed"
            assoc.parse_errors = err_msg
            db.commit()
            raise ValueError(f"WinEst parse failed for '{doc.filename}': {err_msg}")

        # Normalize raw items via LineItemNormalizer --------------------------------
        normalizer = LineItemNormalizer()
        normalized_items = normalizer.normalize_winest_items(
            parse_result["line_items"],
            library_entry,
        )

        created_items: list[HistoricalLineItem] = []

        for norm in normalized_items:
            item = HistoricalLineItem(
                library_entry_id=assoc.library_entry_id,
                project_id=assoc.project_id,
                source_file=doc.filename,
                **norm,
            )
            db.add(item)
            created_items.append(item)

        # Mark parsed -------------------------------------------------------------
        assoc.parsed = True
        assoc.parsed_at = datetime.utcnow()
        db.commit()

        logger.info(
            "process_winest_file: assoc=%d → %d line items created",
            doc_association_id,
            len(created_items),
        )
        return created_items

    def process_batch_group(self, group_id: int, db: Session) -> dict:
        """Process all unparsed documents inside a :class:`DocumentGroup`.

        - WinEst files (.est or role=winest_bid) → :meth:`process_winest_file`
        - Spec PDFs (role=spec, ext=pdf) → Agent 1 ingestion + library metadata sync
        - All other documents are skipped (user can trigger manually)

        Returns a summary dict.
        """
        from apex.backend.agents.agent_1_ingestion import run_ingestion_agent

        group = db.query(DocumentGroup).filter(DocumentGroup.id == group_id).first()
        if not group:
            raise ValueError(f"DocumentGroup {group_id} not found")

        summary: dict = {
            "group_id": group_id,
            "winest_files_processed": 0,
            "spec_files_processed": 0,
            "line_items_created": 0,
            "errors": [],
        }

        unparsed = (
            db.query(DocumentAssociation)
            .filter(
                DocumentAssociation.group_id == group_id,
                DocumentAssociation.parsed == False,  # noqa: E712
            )
            .all()
        )

        for assoc in unparsed:
            doc = assoc.document
            if not doc:
                continue

            ext = doc.filename.rsplit(".", 1)[-1].lower() if "." in doc.filename else ""
            role = assoc.document_role

            try:
                if role == "winest_bid" or ext == "est":
                    items = self.process_winest_file(assoc.id, db)
                    summary["winest_files_processed"] += 1
                    summary["line_items_created"] += len(items)

                elif role == "spec" and ext == "pdf":
                    # Agent 1 handles all pending docs for the project
                    run_ingestion_agent(db=db, project_id=doc.project_id)
                    summary["spec_files_processed"] += 1

                    if group.library_entry_id:
                        self._sync_library_from_spec(group.library_entry_id, doc, db)

            except Exception as exc:
                logger.warning("Error on assoc %d (%s): %s", assoc.id, doc.filename, exc)
                assoc.parse_errors = str(exc)
                summary["errors"].append(f"assoc {assoc.id} ({doc.filename}): {exc}")
                db.commit()

        return summary

    # ------------------------------------------------------------------ #
    # Private helpers                                                     #
    # ------------------------------------------------------------------ #

    def _create_group(
        self,
        group_name: str,
        file_paths: list[str],
        user_id: int,
        db: Session,
    ) -> dict:
        """Persist all DB records for one project group.  Returns a summary dict."""
        errors: list[str] = []
        files_by_type: dict[str, int] = {}

        # Placeholder Project — Document.project_id is NOT NULL
        project = Project(
            name=group_name,
            project_number=f"BATCH-{uuid.uuid4().hex[:8].upper()}",
            project_type="commercial",  # placeholder; user can update later
            status="draft",
            owner_id=user_id,
        )
        db.add(project)
        db.flush()

        # Placeholder EstimateLibraryEntry
        library_entry = EstimateLibraryEntry(
            name=group_name,
            total_cost=0.0,
            status="pending",
            source="batch_import",
            created_by=user_id,
            project_id=project.id,
        )
        db.add(library_entry)
        db.flush()

        # DocumentGroup
        group = DocumentGroup(
            name=group_name,
            project_id=project.id,
            library_entry_id=library_entry.id,
        )
        db.add(group)
        db.flush()

        # Per-project upload directory
        upload_dir = os.path.join(UPLOAD_DIR, f"batch_{project.id}")
        os.makedirs(upload_dir, exist_ok=True)

        for src_path in file_paths:
            fname = os.path.basename(src_path)
            ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
            try:
                # Detect type before the file is moved
                metric_type, document_role = _detect_file_type(src_path)
                files_by_type[metric_type] = files_by_type.get(metric_type, 0) + 1

                # Copy to upload directory with a unique prefix
                dest_name = f"{uuid.uuid4().hex}_{fname}"
                dest_path = os.path.join(upload_dir, dest_name)
                shutil.copy2(src_path, dest_path)

                doc = Document(
                    project_id=project.id,
                    filename=fname,
                    file_path=dest_path,
                    file_type=ext if ext else "other",
                    classification=document_role,
                    file_size_bytes=os.path.getsize(dest_path),
                    processing_status="pending",
                )
                db.add(doc)
                db.flush()

                assoc = DocumentAssociation(
                    document_id=doc.id,
                    group_id=group.id,
                    library_entry_id=library_entry.id,
                    project_id=project.id,
                    document_role=document_role,
                    parsed=False,
                )
                db.add(assoc)

            except Exception as exc:
                logger.warning("Failed to stage file '%s': %s", fname, exc)
                errors.append(f"File '{fname}': {exc}")

        db.commit()
        logger.info(
            "_create_group: group='%s' project=%d files=%d",
            group_name,
            project.id,
            len(file_paths),
        )
        return {
            "file_count": len(file_paths),
            "files_by_type": files_by_type,
            "errors": errors,
        }

    def _sync_library_from_spec(
        self,
        library_entry_id: int,
        doc: Document,
        db: Session,
    ) -> None:
        """Best-effort update of EstimateLibraryEntry from spec document metadata."""
        entry = db.query(EstimateLibraryEntry).filter(EstimateLibraryEntry.id == library_entry_id).first()
        if not entry or not doc.metadata_json:
            return

        meta = doc.metadata_json or {}
        if meta.get("square_footage") and not entry.square_footage:
            entry.square_footage = float(meta["square_footage"])
        if meta.get("project_type") and not entry.project_type:
            entry.project_type = str(meta["project_type"])
        if meta.get("building_type") and not entry.building_type:
            entry.building_type = str(meta["building_type"])
        entry.recalculate_cost_per_sqft()
        db.commit()
