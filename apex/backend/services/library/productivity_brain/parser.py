"""
Format detection and Excel parsing for WinEst exports and averaged-rate files.

Supports three formats:
  - 26-column CCI Civil Est Report
  - 21-column CCI Estimate Report
  - Averaged-rates (e.g. CityGate_Master_Productivity_Rates.xlsx)
"""

import hashlib

import pandas as pd

# ── Column mappings ported from productivity_brain/scripts/ingest.py ──

FORMAT_26_COLS = {
    "wbs": 1,
    "desc": 3,
    "qty": 4,
    "unit": 5,
    "prod": 6,
    "prod_unit": 7,
    "crew": 8,
    "labor_hrs": 10,
    "labor_up": 11,
    "mat_up": 12,
    "equip_up": 17,
    "subs_up": 18,
    "labor_total": 19,
    "mat_total": 20,
    "equip_total": 21,
    "subs_total": 22,
    "grand_total": 25,
}

FORMAT_21_COLS = {
    "wbs": 1,
    "desc": 2,
    "qty": 3,
    "unit": 4,
    "crew": 5,
    "prod": 6,
    "prod_unit": 7,
    "labor_hrs": 8,
    "labor_up": 9,
    "mat_up": 10,
    "equip_up": 12,
    "subs_up": 13,
    "labor_total": 14,
    "mat_total": 15,
    "equip_total": 16,
    "subs_total": 17,
    "grand_total": 20,
}


# ── Helpers ──


def _safe_float(val):
    if pd.isna(val):
        return None
    try:
        return float(str(val).replace(",", "").replace("$", ""))
    except (ValueError, TypeError):
        return None


def _safe_str(val):
    if pd.isna(val):
        return None
    s = str(val).strip()
    return s if s and s != "nan" else None


def _clean_dash(val):
    """Treat '—' / '--' / '-' as None."""
    s = _safe_str(val)
    if s in ("—", "--", "-"):
        return None
    return s


# ── Public API ──


def compute_file_hash(filepath: str) -> str:
    """MD5 hash of file contents for dedup."""
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def detect_format(filepath: str) -> str:
    """Classify file as '26col_civil', '21col_estimate', 'averaged_rates', or 'unknown'."""
    df = pd.read_excel(filepath, header=None, nrows=5)
    cell_a1 = str(df.iloc[0, 0]) if pd.notna(df.iloc[0, 0]) else ""

    if "_CCI Civil Est Report" in cell_a1 or "CCI Civil Est Report" in cell_a1:
        return "26col_civil"
    if "_CCI Estimate Report" in cell_a1 or "CCI Estimate Report" in cell_a1:
        return "21col_estimate"

    # Check averaged-rates: header row at row 3 with known column names
    if df.shape[0] > 3:
        row3 = [str(c).strip() for c in df.iloc[3] if pd.notna(c)]
        row3_joined = " ".join(row3).lower()
        if "wbs area" in row3_joined and "avg prod" in row3_joined:
            return "averaged_rates"

    # Column-count fallback (matches original ingest.py)
    if df.shape[1] >= 25:
        return "26col_civil"
    if df.shape[1] >= 20:
        return "21col_estimate"

    return "unknown"


def parse_26col(filepath: str) -> list[dict]:
    """Parse a 26-column CCI Civil Est Report export."""
    df = pd.read_excel(filepath, header=None)
    cols = FORMAT_26_COLS
    items = []

    for idx in range(4, len(df)):
        row = df.iloc[idx]
        desc = _safe_str(row[cols["desc"]])
        if desc is None:
            continue

        items.append(
            {
                "wbs_area": _safe_str(row[cols["wbs"]]),
                "activity": desc,
                "quantity": _safe_float(row[cols["qty"]]),
                "unit": _safe_str(row[cols["unit"]]),
                "crew_trade": _safe_str(row[cols["crew"]]),
                "production_rate": _safe_float(row[cols["prod"]]),
                "labor_hours": _safe_float(row[cols["labor_hrs"]]),
                "labor_cost_per_unit": _safe_float(row[cols["labor_up"]]),
                "material_cost_per_unit": _safe_float(row[cols["mat_up"]]),
                "equipment_cost": _safe_float(row[cols["equip_up"]]),
                "sub_cost": _safe_float(row[cols["subs_up"]]),
                "total_cost": _safe_float(row[cols["grand_total"]]),
            }
        )

    return items


def parse_21col(filepath: str) -> list[dict]:
    """Parse a 21-column CCI Estimate Report export."""
    df = pd.read_excel(filepath, header=None)
    cols = FORMAT_21_COLS
    items = []

    for idx in range(4, len(df)):
        row = df.iloc[idx]
        desc = _safe_str(row[cols["desc"]])
        if desc is None:
            continue

        items.append(
            {
                "wbs_area": _safe_str(row[cols["wbs"]]),
                "activity": desc,
                "quantity": _safe_float(row[cols["qty"]]),
                "unit": _safe_str(row[cols["unit"]]),
                "crew_trade": _safe_str(row[cols["crew"]]),
                "production_rate": _safe_float(row[cols["prod"]]),
                "labor_hours": _safe_float(row[cols["labor_hrs"]]),
                "labor_cost_per_unit": _safe_float(row[cols["labor_up"]]),
                "material_cost_per_unit": _safe_float(row[cols["mat_up"]]),
                "equipment_cost": _safe_float(row[cols["equip_up"]]),
                "sub_cost": _safe_float(row[cols["subs_up"]]),
                "total_cost": _safe_float(row[cols["grand_total"]]),
            }
        )

    return items


def parse_averaged_rates(filepath: str) -> list[dict]:
    """Parse an averaged-rates file (e.g. CityGate_Master_Productivity_Rates.xlsx).

    Expected layout:
      Row 0: title
      Row 3: header — WBS Area | Activity Description | Unit | Crew/Trade | AVG Prod |
              <per-project cols> | Count | Spread | Avg Labor $/Unit | Avg Mat $/Unit
    """
    df = pd.read_excel(filepath, header=None)

    # Find header row at row 3
    header_row = 3
    headers = [str(c).strip() if pd.notna(c) else "" for c in df.iloc[header_row]]

    # Map known column names to indices (case-insensitive)
    col_map = {}
    project_cols = []  # indices of per-project rate columns
    for i, h in enumerate(headers):
        hl = h.lower()
        if "wbs" in hl:
            col_map["wbs"] = i
        elif "activity" in hl and "description" in hl:
            col_map["activity"] = i
        elif hl == "unit":
            col_map["unit"] = i
        elif "crew" in hl or "trade" in hl:
            col_map["crew"] = i
        elif "avg prod" in hl:
            col_map["avg_prod"] = i
        elif "count" == hl:
            col_map["count"] = i
        elif "spread" == hl:
            col_map["spread"] = i
        elif "avg labor" in hl:
            col_map["labor_up"] = i
        elif "avg mat" in hl:
            col_map["mat_up"] = i
        elif col_map.get("avg_prod") and "count" not in col_map:
            # Columns between AVG Prod and Count are per-project columns
            project_cols.append((h, i))

    items = []
    for idx in range(header_row + 1, len(df)):
        row = df.iloc[idx]
        activity = _safe_str(row[col_map.get("activity", 1)])
        if activity is None:
            continue  # Skip section headers

        avg_prod = _safe_float(row[col_map["avg_prod"]]) if "avg_prod" in col_map else None

        base = {
            "wbs_area": _safe_str(row[col_map["wbs"]]) if "wbs" in col_map else None,
            "activity": activity,
            "unit": _safe_str(row[col_map["unit"]]) if "unit" in col_map else None,
            "crew_trade": _safe_str(row[col_map["crew"]]) if "crew" in col_map else None,
            "production_rate": avg_prod,
            "labor_cost_per_unit": _safe_float(row[col_map["labor_up"]]) if "labor_up" in col_map else None,
            "material_cost_per_unit": _safe_float(row[col_map["mat_up"]]) if "mat_up" in col_map else None,
            "quantity": None,
            "labor_hours": None,
            "equipment_cost": None,
            "sub_cost": None,
            "total_cost": None,
        }

        # Emit per-project rows if project columns exist
        if project_cols:
            for proj_name, col_idx in project_cols:
                val = _clean_dash(row[col_idx])
                rate = _safe_float(val) if val is not None else None
                if rate is not None:
                    item = {**base, "production_rate": rate, "source_project": proj_name}
                    items.append(item)
            # Also emit an "averaged" row using AVG Prod
            if avg_prod is not None:
                items.append({**base, "source_project": "_averaged"})
        else:
            # No per-project columns — just emit the row
            if avg_prod is not None:
                items.append(base)

    return items
