"""Quantity import utilities — parse WinEst XLSX or CSV into quantity dicts."""

import csv
import io
import logging
from typing import Optional

logger = logging.getLogger("apex.quantity_import")


def _safe_float(val) -> Optional[float]:
    try:
        f = float(val)
        return f if f == f else None  # filter NaN
    except (TypeError, ValueError):
        return None


def _wbs_to_division(wbs: str) -> Optional[str]:
    """Map WBS area name to CSI division code."""
    if not wbs:
        return None
    w = str(wbs).lower()
    if "general condition" in w or "000" in w:
        return "01 00 00"
    if "earthwork" in w or "excav" in w or "backfill" in w:
        return "31 00 00"
    if "site" in w:
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
    return None


def _is_skip_row(description: str) -> bool:
    """Return True for summary/total rows that should be excluded."""
    if not description:
        return True
    desc_upper = str(description).upper().strip()
    return (
        "SUBTOTAL" in desc_upper
        or "TOTAL" in desc_upper
        or "SUMMARY" in desc_upper
        or desc_upper == "NAN"
        or desc_upper == ""
    )


def _detect_format(df) -> Optional[str]:
    """Auto-detect WinEst format by scanning first 10 rows for header patterns."""
    import pandas as pd

    for row_idx in range(min(10, len(df))):
        row_vals = set(str(v).strip() for v in df.iloc[row_idx].tolist() if pd.notna(v))
        # Format 1 (Civil Est Report): WBS + Description + Quantity headers
        if {"WBS", "Description", "Quantity"}.issubset(row_vals):
            return f"format1:{row_idx}"
        # Format 2 (Estimate Report): Item + Description + Takeoff Qty headers
        if {"Item", "Description", "Takeoff Qty"}.issubset(row_vals):
            return f"format2:{row_idx}"
        # Also accept the existing winest_parser Format 1
        if {"Description", "Quantity", "Unit"}.issubset(row_vals):
            return f"format1:{row_idx}"
    return None


def parse_winest_xlsx(file_path: str) -> list[dict]:
    """Parse a WinEst XLSX export into a list of quantity dicts.

    Returns: [{description, quantity, unit, division_code}]
    Raises ValueError on unsupported/undetectable format.
    """
    import pandas as pd

    df = pd.read_excel(file_path, header=None)

    fmt_info = _detect_format(df)
    if not fmt_info:
        raise ValueError(
            "Could not detect WinEst format. Expected headers containing "
            "('WBS','Description','Quantity') or ('Item','Description','Takeoff Qty')."
        )

    fmt_type, header_row = fmt_info.split(":")
    header_row = int(header_row)

    # Rebuild DataFrame using detected header row
    headers = [str(v).strip() for v in df.iloc[header_row].tolist()]
    data = df.iloc[header_row + 1:].reset_index(drop=True)
    data.columns = headers

    quantities = []

    if fmt_type == "format1":
        # Format 1: Description, Quantity, Unit, WBS (optional)
        desc_col = next((c for c in headers if c == "Description"), None)
        qty_col = next((c for c in headers if c in ("Quantity", "Qty")), None)
        unit_col = next((c for c in headers if c in ("Unit", "UOM")), None)
        wbs_col = next((c for c in headers if c == "WBS"), None)

        if not desc_col or not qty_col:
            raise ValueError("Format 1: missing Description or Quantity columns.")

        for _, row in data.iterrows():
            description = str(row.get(desc_col, "")).strip()
            if _is_skip_row(description):
                continue
            qty = _safe_float(row.get(qty_col))
            if qty is None or qty == 0:
                continue
            unit = str(row.get(unit_col, "")).strip() if unit_col else None
            wbs = str(row.get(wbs_col, "")).strip() if wbs_col else ""
            division_code = _wbs_to_division(wbs)
            quantities.append({
                "description": description,
                "quantity": qty,
                "unit": unit or None,
                "division_code": division_code,
            })

    else:  # format2
        # Format 2: Item, Description, Takeoff Qty, Unit
        desc_col = next((c for c in headers if c == "Description"), None)
        qty_col = next((c for c in headers if c == "Takeoff Qty"), None)
        unit_col = next((c for c in headers if c in ("Unit", "UOM")), None)

        if not desc_col or not qty_col:
            raise ValueError("Format 2: missing Description or 'Takeoff Qty' columns.")

        for _, row in data.iterrows():
            description = str(row.get(desc_col, "")).strip()
            if _is_skip_row(description):
                continue
            qty = _safe_float(row.get(qty_col))
            if qty is None or qty == 0:
                continue
            unit = str(row.get(unit_col, "")).strip() if unit_col else None
            quantities.append({
                "description": description,
                "quantity": qty,
                "unit": unit or None,
                "division_code": None,
            })

    if not quantities:
        raise ValueError("No valid quantity rows found in the file.")

    logger.info("Parsed %d quantities from %s (format: %s)", len(quantities), file_path, fmt_type)
    return quantities


def parse_csv_quantities(csv_text: str) -> list[dict]:
    """Parse CSV text: description,quantity,unit,division_code per line."""
    quantities = []
    reader = csv.reader(io.StringIO(csv_text.strip()))
    for row in reader:
        if not row:
            continue
        # Skip header-like rows
        if row[0].strip().lower() in ("description", "work item", "#"):
            continue
        if len(row) < 2:
            continue
        description = row[0].strip()
        if _is_skip_row(description):
            continue
        qty = _safe_float(row[1]) if len(row) > 1 else None
        if qty is None or qty == 0:
            continue
        unit = row[2].strip() if len(row) > 2 else None
        division_code = row[3].strip() if len(row) > 3 else None
        quantities.append({
            "description": description,
            "quantity": qty,
            "unit": unit or None,
            "division_code": division_code or None,
        })
    return quantities
