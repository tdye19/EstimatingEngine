"""Parser for EstimationHistory .xlsx — reads the Estimating sheet.

Tolerates both the original 48-column Enhanced file and the 42-column
production file (missing 8 trailing Enhanced columns + one None header).
"""

from datetime import datetime

import pandas as pd

# ---------------------------------------------------------------------------
# Column contract
# ---------------------------------------------------------------------------

# Required columns — upload returns 422 if any are absent from the header row.
REQUIRED_COLUMNS = {"Status", "Estimate #", "Name", "Bid Date", "Bid Amount", "Trade", "Estimator"}

# Full header → model field mapping. Columns absent from the file are silently
# set to None; only REQUIRED_COLUMNS cause a pre-flight rejection.
COLUMN_MAP = {
    "Status": "status",
    "Region": "region",
    "Market Sector": "market_sector",
    "Month": "month",
    "Job #": "job_number",
    "Estimate #": "estimate_number",
    "Name": "name",
    "Bid Date": "bid_date",
    "Sales Date": "sales_date",
    "Bid Amount": "bid_amount",
    "Location": "location",
    "Trade": "trade",
    "Estimator": "estimator",
    "Contract Amount": "contract_amount",
    "Contract Fee": "contract_fee",
    "Contract Hours": "contract_hours",
    "Comments": "comments",
    "Conc Vol (CY)": "conc_vol_cy",
    "Building SF": "building_sf",
    "Production MH": "production_mh",
    "Installation MH": "installation_mh",
    "GC MH": "gc_mh",
    "Total MH": "total_mh",
    "Fee": "fee",
    "Duration (PM) Weeks": "duration_weeks",
    "Total GC Labor": "total_gc_labor",
    "Staff Labor Hours": "staff_labor_hours",
    "Total GC's": "total_gcs",
    "GC %": "gc_pct",
    "Customer": "customer",
    "Final Hours": "final_hours",
    "WIP Est Cost": "wip_est_cost",
    "WIP Est Fee": "wip_est_fee",
    "WIP Est Contract": "wip_est_contract",
    "WIP Fee %": "wip_fee_pct",
    "Contract Status": "contract_status",
    "Job Start Date": "job_start_date",
    "Job End Date": "job_end_date",
    "Weeks": "weeks",
    "Equipment Value": "equipment_value",
    # 8 "Enhanced" columns — optional, absent in the 42-col production file
    "Delivery Method": "delivery_method",
    "# of Bidders": "num_bidders",
    "Opportunity Source": "opportunity_source",
    "Go/No-Go Score": "go_no_go_score",
    "Loss Reason": "loss_reason",
    "Competitor Who Won": "competitor_who_won",
    "Our Rank (if lost)": "our_rank",
    "Bid Delta % (Contract vs Bid)": "bid_delta_pct",
}

_DATE_FIELDS = {"bid_date", "sales_date", "job_start_date", "job_end_date"}
_INT_FIELDS = {"month", "num_bidders", "our_rank"}
_PCT_FIELDS = {"gc_pct", "wip_fee_pct", "bid_delta_pct"}
_CURRENCY_FIELDS = {
    "bid_amount", "contract_amount", "contract_fee", "fee", "total_gc_labor",
    "wip_est_cost", "wip_est_fee", "wip_est_contract", "equipment_value",
}
_STRING_FIELDS = {
    "status", "region", "market_sector", "job_number", "estimate_number",
    "name", "location", "trade", "estimator", "comments", "customer",
    "contract_status", "delivery_method", "opportunity_source",
    "go_no_go_score", "loss_reason", "competitor_who_won",
}


# ---------------------------------------------------------------------------
# Type coercion helpers
# ---------------------------------------------------------------------------

def _clean_value(val):
    """Return None for NaN, dash placeholders, and empty strings."""
    if pd.isna(val):
        return None
    s = str(val).strip()
    if s in ("", "—", "--", "-", "nan", "NaN", "N/A", "n/a"):
        return None
    return s


def _parse_currency(val) -> float | None:
    """Clean currency: remove $, commas, parens for negatives."""
    s = _clean_value(val)
    if s is None:
        return None
    s = s.replace("$", "").replace(",", "").strip()
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _parse_pct(val) -> float | None:
    """Clean percentage: remove % sign, return as float (not decimal)."""
    s = _clean_value(val)
    if s is None:
        return None
    s = s.replace("%", "").replace(",", "").strip()
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _parse_float(val) -> float | None:
    s = _clean_value(val)
    if s is None:
        return None
    s = str(s).replace(",", "").replace("$", "").strip()
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _parse_int(val) -> int | None:
    f = _parse_float(val)
    return int(f) if f is not None else None


def _parse_date(val):
    """Parse date from datetime, Timestamp, or string."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, datetime | pd.Timestamp):
        return val.date() if not pd.isna(val) else None
    s = _clean_value(val)
    if s is None:
        return None
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y", "%B %d, %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _coerce(field: str, raw):
    """Coerce a raw cell value to the correct Python type for *field*."""
    if field in _DATE_FIELDS:
        return _parse_date(raw)
    if field in _INT_FIELDS:
        return _parse_int(raw)
    if field in _PCT_FIELDS:
        return _parse_pct(raw)
    if field in _CURRENCY_FIELDS:
        return _parse_currency(raw)
    if field in _STRING_FIELDS:
        return _clean_value(raw)
    return _parse_float(raw)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def parse_estimation_history(filepath: str) -> tuple[list[dict], list[dict], list[str]]:
    """Read the 'Estimating' sheet and parse rows to BIEstimate field dicts.

    Returns:
        (records, row_errors, found_headers) where:
        - records: list of field-dict for successfully parsed rows
        - row_errors: list of {row, error, raw} for rows that raised
        - found_headers: list of recognised header strings (for 422 diagnostics)

    Raises:
        ValueError with a dict payload (as str) when required columns are absent.
        The router unpacks this into a 422 JSON body.
    """
    df = pd.read_excel(filepath, sheet_name="Estimating", header=0)

    # Build column-index → field-name map, skipping None/empty/whitespace headers.
    col_idx: dict[str, str] = {}   # field_name → excel column label
    found_headers: list[str] = []

    for col_name in df.columns:
        # Pandas represents empty header cells as NaN / float
        if col_name is None or (isinstance(col_name, float) and pd.isna(col_name)):
            continue
        clean_col = str(col_name).strip()
        if not clean_col or clean_col.lower() in ("nan", "none"):
            continue
        found_headers.append(clean_col)
        if clean_col in COLUMN_MAP:
            col_idx[COLUMN_MAP[clean_col]] = col_name

    # Pre-flight: all required columns must be present.
    present_headers = set(found_headers)
    missing = [col for col in sorted(REQUIRED_COLUMNS) if col not in present_headers]
    if missing:
        import json
        raise ValueError(
            json.dumps({
                "error": "missing_required_columns",
                "missing": missing,
                "found_columns": sorted(present_headers),
            })
        )

    records: list[dict] = []
    row_errors: list[dict] = []

    for row_idx, (_, row) in enumerate(df.iterrows(), start=2):  # 1-based, header is row 1
        try:
            record: dict = {}
            for field, excel_col in col_idx.items():
                record[field] = _coerce(field, row[excel_col])

            # Skip blank rows (no name)
            if not record.get("name"):
                continue

            record["_row_num"] = row_idx  # consumed by service for duplicate tracking
            records.append(record)

        except Exception as exc:
            raw_preview = [str(row.iloc[i]) for i in range(min(3, len(row)))]
            row_errors.append({"row": row_idx, "error": str(exc), "raw": raw_preview})

    return records, row_errors, found_headers
