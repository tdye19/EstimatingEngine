"""Parser for EstimationHistory_Enhanced.xlsx — reads the Estimating sheet."""

from datetime import datetime

import pandas as pd

# Column header -> model field mapping
_COL_MAP = {
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
    # Handle accounting-style negatives: (1234)
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _parse_pct(val) -> float | None:
    """Clean percentage: remove % sign, convert to float (keep as percentage, not decimal)."""
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
    """Parse date from various formats."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    # Already a datetime/Timestamp from pandas
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


def parse_estimation_history(filepath: str) -> list[dict]:
    """Read the 'Estimating' sheet and return a list of dicts mapped to BIEstimate fields."""
    df = pd.read_excel(filepath, sheet_name="Estimating", header=0)

    # Build column index: map header text -> model field
    col_idx = {}
    for col_name in df.columns:
        clean_col = str(col_name).strip()
        if clean_col in _COL_MAP:
            col_idx[_COL_MAP[clean_col]] = col_name

    records = []
    for _, row in df.iterrows():
        record = {}
        for field, excel_col in col_idx.items():
            raw = row[excel_col]

            if field in _DATE_FIELDS:
                record[field] = _parse_date(raw)
            elif field in _INT_FIELDS:
                record[field] = _parse_int(raw)
            elif field in _PCT_FIELDS:
                record[field] = _parse_pct(raw)
            elif field in (
                "bid_amount",
                "contract_amount",
                "contract_fee",
                "fee",
                "total_gc_labor",
                "wip_est_cost",
                "wip_est_fee",
                "wip_est_contract",
                "equipment_value",
            ):
                record[field] = _parse_currency(raw)
            elif field in (
                "status",
                "region",
                "market_sector",
                "job_number",
                "estimate_number",
                "name",
                "location",
                "trade",
                "estimator",
                "comments",
                "customer",
                "contract_status",
                "delivery_method",
                "opportunity_source",
                "go_no_go_score",
                "loss_reason",
                "competitor_who_won",
            ):
                record[field] = _clean_value(raw)
            else:
                record[field] = _parse_float(raw)

        # Skip rows with no name (empty / section header rows)
        if not record.get("name"):
            continue

        records.append(record)

    return records
