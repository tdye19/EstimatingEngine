"""Bulk WinEst XLSX project loader — ingests any WinEst export into the decision system.

Supports three WinEst export formats:
  Format 1 (26-col): WBS + Description + Quantity headers
  Format 2 (21-col): Item + Description + Takeoff Qty headers
  Format 3 (Productivity): Activity + Prod Rate or Unit/MH headers
"""

import logging
import os

from sqlalchemy.orm import Session

from apex.backend.models.decision_models import (
    ComparableProject,
    HistoricalRateObservation,
)

logger = logging.getLogger("apex.decision_loader")

_SKIP_PATTERNS = {"subtotal", "total", "summary", "division", "section"}


def _wbs_to_division(wbs: str) -> str:
    if not wbs:
        return "03 30 00"
    w = wbs.lower()
    if "general condition" in w or "000" in w:
        return "01 00 00"
    if "earthwork" in w or "site" in w or "excav" in w:
        return "31 00 00"
    if "foundation" in w or "footing" in w:
        return "03 30 00"
    if "sog" in w or "slab" in w or "flatwork" in w:
        return "03 30 00"
    if "wall" in w or "stem" in w:
        return "03 30 00"
    if "rebar" in w or "reinforc" in w:
        return "03 20 00"
    if "embed" in w or "anchor" in w:
        return "03 15 00"
    if "waterproof" in w or "damp" in w:
        return "07 10 00"
    if "paving" in w or "asphalt" in w:
        return "32 12 00"
    if "pipe" in w or "storm" in w or "sanitary" in w:
        return "33 00 00"
    if "concrete" in w:
        return "03 30 00"
    return "03 30 00"


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        s = str(val).replace(",", "").replace("$", "").strip()
        if s in ("", "nan", "-", "—", "–"):
            return None
        return float(s)
    except (ValueError, TypeError):
        return None


def _detect_format(df) -> int:
    """Auto-detect WinEst export format by scanning first 10 rows."""

    # Flatten first 10 rows into one string for scanning
    sample = df.head(10).to_string().lower()

    has_wbs = "wbs" in sample
    has_desc = "description" in sample
    has_qty = "quantity" in sample
    has_item = "item" in sample
    has_takeoff = "takeoff" in sample
    has_activity = "activity" in sample
    has_prod = "prod rate" in sample or "unit/mh" in sample

    if has_activity and has_prod:
        return 3
    if has_item and has_takeoff:
        return 2
    if has_wbs and has_desc and has_qty:
        return 1
    # Fallback: try to guess from column count
    ncols = len(df.columns)
    if ncols >= 26:
        return 1
    if ncols >= 21:
        return 2
    return 2  # default


def _col_index(header_row, *names) -> int | None:
    """Find column index by matching header names (case-insensitive)."""
    if header_row is None:
        return None
    for i, cell in enumerate(header_row):
        cell_str = str(cell).lower().strip()
        for name in names:
            if name.lower() in cell_str:
                return i
    return None


def _parse_format1(df, proj_id: str, dq: float = 0.7) -> list:
    """Format 1: 26-col WinEst standard export with WBS, Description, Quantity."""
    try:
        import pandas as pd
    except ImportError:
        return []

    observations = []

    # Find header row (first row with "Description" or "WBS")
    header_row_idx = None
    for i, row in df.iterrows():
        row_str = " ".join(str(c).lower() for c in row.values)
        if "description" in row_str and ("wbs" in row_str or "quantity" in row_str):
            header_row_idx = i
            break

    if header_row_idx is None:
        header_row_idx = 0

    header = list(df.iloc[header_row_idx])
    data = df.iloc[header_row_idx + 1 :].reset_index(drop=True)

    col_wbs = _col_index(header, "wbs")
    col_desc = _col_index(header, "description")
    col_qty = _col_index(header, "quantity", "qty")
    col_unit = _col_index(header, "unit")
    col_total = _col_index(header, "total", "amount")
    col_labor = _col_index(header, "labor")
    col_mat = _col_index(header, "material", "mat")
    col_equip = _col_index(header, "equipment", "equip")
    col_mh = _col_index(header, "man hour", "manhour", "labor mh", "labormh")

    if col_desc is None:
        col_desc = 1

    for row_idx, row in data.iterrows():
        desc_val = row.iloc[col_desc] if col_desc is not None else None
        if pd.isna(desc_val) or str(desc_val).strip() in ("", "nan"):
            continue
        desc = str(desc_val).strip()

        # Skip subtotals/totals
        desc_lower = desc.lower()
        if any(p in desc_lower for p in _SKIP_PATTERNS):
            continue

        wbs = str(row.iloc[col_wbs]).strip() if col_wbs is not None and pd.notna(row.iloc[col_wbs]) else ""
        qty = _safe_float(row.iloc[col_qty]) if col_qty is not None else None
        unit_val = str(row.iloc[col_unit]).strip() if col_unit is not None and pd.notna(row.iloc[col_unit]) else None
        total = _safe_float(row.iloc[col_total]) if col_total is not None else None
        labor = _safe_float(row.iloc[col_labor]) if col_labor is not None else None
        mat = _safe_float(row.iloc[col_mat]) if col_mat is not None else None
        equip = _safe_float(row.iloc[col_equip]) if col_equip is not None else None
        mh = _safe_float(row.iloc[col_mh]) if col_mh is not None else None

        if qty is None or qty == 0:
            continue

        unit_cost = None
        if total and qty and qty > 0:
            unit_cost = round(total / qty, 4)

        prod_rate = None
        if qty and mh and mh > 0:
            prod_rate = round(qty / mh, 4)

        observations.append(
            HistoricalRateObservation(
                comparable_project_id=proj_id,
                raw_activity_name=desc,
                division_code=_wbs_to_division(wbs),
                quantity=qty,
                unit=unit_val,
                unit_cost=unit_cost,
                total_cost=total,
                labor_cost=labor,
                material_cost=mat,
                equipment_cost=equip,
                production_rate=prod_rate,
                data_quality_score=dq,
                source_row=int(row_idx),
            )
        )

    return observations


def _parse_format2(df, proj_id: str, dq: float = 0.5) -> list:
    """Format 2: 21-col WinEst export with Item, Description, Takeoff Qty."""
    try:
        import pandas as pd
    except ImportError:
        return []

    observations = []

    # Find header row
    header_row_idx = None
    for i, row in df.iterrows():
        row_str = " ".join(str(c).lower() for c in row.values)
        if "description" in row_str and ("item" in row_str or "takeoff" in row_str):
            header_row_idx = i
            break

    if header_row_idx is None:
        header_row_idx = 0

    header = list(df.iloc[header_row_idx])
    data = df.iloc[header_row_idx + 1 :].reset_index(drop=True)

    col_desc = _col_index(header, "description")
    col_qty = _col_index(header, "takeoff qty", "qty", "quantity")
    col_unit = _col_index(header, "unit")
    col_total = _col_index(header, "total", "amount", "extended")

    if col_desc is None:
        col_desc = 1
    if col_qty is None:
        col_qty = 3

    for row_idx, row in data.iterrows():
        desc_val = row.iloc[col_desc] if col_desc is not None else None
        if pd.isna(desc_val) or str(desc_val).strip() in ("", "nan"):
            continue
        desc = str(desc_val).strip()
        desc_lower = desc.lower()
        if any(p in desc_lower for p in _SKIP_PATTERNS):
            continue

        qty = _safe_float(row.iloc[col_qty]) if col_qty is not None else None
        unit_val = str(row.iloc[col_unit]).strip() if col_unit is not None and pd.notna(row.iloc[col_unit]) else None
        total = _safe_float(row.iloc[col_total]) if col_total is not None else None

        if qty is None or qty == 0:
            continue

        unit_cost = None
        if total and qty and qty > 0:
            unit_cost = round(total / qty, 4)

        observations.append(
            HistoricalRateObservation(
                comparable_project_id=proj_id,
                raw_activity_name=desc,
                division_code="03 30 00",
                quantity=qty,
                unit=unit_val,
                unit_cost=unit_cost,
                total_cost=total,
                data_quality_score=dq,
                source_row=int(row_idx),
            )
        )

    return observations


def _parse_format3(df, proj_id: str, dq: float = 0.65) -> list:
    """Format 3: Productivity-style export with Activity + Prod Rate."""
    try:
        import pandas as pd
    except ImportError:
        return []

    observations = []

    # Find header row
    header_row_idx = None
    for i, row in df.iterrows():
        row_str = " ".join(str(c).lower() for c in row.values)
        if "activity" in row_str and ("prod rate" in row_str or "unit/mh" in row_str or "production" in row_str):
            header_row_idx = i
            break

    if header_row_idx is None:
        header_row_idx = 0

    header = list(df.iloc[header_row_idx])
    data = df.iloc[header_row_idx + 1 :].reset_index(drop=True)

    col_activity = _col_index(header, "activity", "description")
    col_unit = _col_index(header, "unit")
    col_prod = _col_index(header, "prod rate", "unit/mh", "production rate", "avg prod")
    col_wbs = _col_index(header, "wbs", "area")

    if col_activity is None:
        col_activity = 1

    for row_idx, row in data.iterrows():
        act_val = row.iloc[col_activity] if col_activity is not None else None
        if pd.isna(act_val) or str(act_val).strip() in ("", "nan", "—", "–"):
            continue
        activity = str(act_val).strip()
        activity_lower = activity.lower()
        if any(p in activity_lower for p in _SKIP_PATTERNS):
            continue

        wbs = str(row.iloc[col_wbs]).strip() if col_wbs is not None and pd.notna(row.iloc[col_wbs]) else ""
        unit_val = str(row.iloc[col_unit]).strip() if col_unit is not None and pd.notna(row.iloc[col_unit]) else None
        prod_rate = _safe_float(row.iloc[col_prod]) if col_prod is not None else None

        unit_cost = None
        if prod_rate and prod_rate > 0:
            unit_cost = round(85.0 / prod_rate, 4)

        observations.append(
            HistoricalRateObservation(
                comparable_project_id=proj_id,
                raw_activity_name=activity,
                division_code=_wbs_to_division(wbs),
                unit=unit_val,
                production_rate=prod_rate,
                unit_cost=unit_cost,
                data_quality_score=dq,
                source_row=int(row_idx),
            )
        )

    return observations


def load_winest_project(db: Session, file_path: str, metadata: dict) -> dict:
    """Load a single WinEst XLSX file into the decision system.

    metadata = {name, client, location, project_type, market_sector, region,
                delivery_method, contract_type, scope_types, complexity_level,
                data_quality_score}
    Returns {project_id, project_name, observations_loaded}
    """
    try:
        import pandas as pd
    except ImportError:
        raise RuntimeError("pandas is required for WinEst loading") from None

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    try:
        df = pd.read_excel(file_path, header=None)
    except Exception as e:
        raise ValueError(f"Cannot read Excel file {file_path}: {e}") from e

    if df.empty:
        raise ValueError(f"Empty file: {file_path}")

    fmt = _detect_format(df)
    logger.info("Detected format %d for %s", fmt, file_path)

    dq_map = {1: 0.7, 2: 0.5, 3: 0.65}
    dq = metadata.get("data_quality_score", dq_map.get(fmt, 0.6))

    proj = ComparableProject(
        name=metadata.get("name", os.path.basename(file_path)),
        client=metadata.get("client"),
        location=metadata.get("location"),
        project_type=metadata.get("project_type", "commercial"),
        market_sector=metadata.get("market_sector", "commercial"),
        region=metadata.get("region", "michigan"),
        delivery_method=metadata.get("delivery_method", "cmar"),
        contract_type=metadata.get("contract_type", "self_perform"),
        scope_types=metadata.get("scope_types", '["concrete","sitework"]'),
        complexity_level=metadata.get("complexity_level", "medium"),
        data_quality_score=dq,
        source_system="winest",
    )
    db.add(proj)
    db.flush()

    if fmt == 1:
        observations = _parse_format1(df, proj.id, dq)
    elif fmt == 3:
        observations = _parse_format3(df, proj.id, dq)
    else:
        observations = _parse_format2(df, proj.id, dq)

    for obs in observations:
        db.add(obs)
    db.flush()

    return {
        "project_id": proj.id,
        "project_name": proj.name,
        "observations_loaded": len(observations),
    }
