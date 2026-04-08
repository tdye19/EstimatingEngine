"""Bulk WinEst XLSX project loader.

Loads any WinEst XLSX export into ComparableProject + HistoricalRateObservation rows.
Supports Format 1 (Civil Est Report) and Format 2 (Estimate Report).

Usage as CLI:
    python -m apex.backend.seed.load_winest_project path/to/file.xlsx "Project Name" \\
        --region michigan --type industrial --market energy --delivery cmar \\
        --contract self_perform --complexity medium --quality 0.7
"""

import argparse
import os
import sys
import uuid
from datetime import datetime, timezone

_here = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(_here)))
for _p in (_repo_root, os.path.dirname(_here)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from apex.backend.db.database import engine, SessionLocal, Base
from apex.backend.models.decision_models import ComparableProject, HistoricalRateObservation
from apex.backend.seed.load_decision_data import _wbs_to_division

# Michigan union labor rate ($/MH) used to derive unit_cost from production rate
ASSUMED_LABOR_RATE_PER_MH = 85.0

_SKIP_PATTERNS = {"SUBTOTAL", "TOTAL", "SUMMARY", "GRAND TOTAL", "SUB TOTAL"}


def _uuid() -> str:
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc)


def _safe_float(val):
    try:
        f = float(val)
        return f if f == f else None  # filter NaN
    except (TypeError, ValueError):
        return None


def _is_skip(description: str) -> bool:
    if not description:
        return True
    d = str(description).strip().upper()
    if d in ("", "NAN"):
        return True
    for pattern in _SKIP_PATTERNS:
        if pattern in d:
            return True
    return False


def _detect_format(df) -> tuple[str | None, int]:
    """Return (format_name, header_row_index) or (None, -1)."""
    import pandas as pd

    for row_idx in range(min(12, len(df))):
        vals = set(str(v).replace("\n", " ").replace("\r", " ").strip()
                   for v in df.iloc[row_idx].tolist() if pd.notna(v))
        # Format 1 (Civil Est Report): Level/WBS + Description + Quantity
        if {"WBS", "Description", "Quantity"}.issubset(vals):
            return "format1", row_idx
        if {"Description", "Quantity", "Unit"}.issubset(vals) and "WBS" not in vals:
            return "format1_simple", row_idx
        # Format 2 (Estimate Report): Item + Description + Takeoff Qty
        if {"Description", "Takeoff Qty"}.issubset(vals):
            return "format2", row_idx
        if {"Item", "Description"}.issubset(vals) and any("Qty" in v or "Quantity" in v for v in vals):
            return "format2", row_idx
        # Format 3 (Productivity Update): WBS + Activity + Qty + Current Prod Rate
        if {"WBS", "Activity", "Qty", "Unit"}.issubset(vals) and any("Prod Rate" in v or "Prod" in v for v in vals):
            return "format3_productivity", row_idx
        # Generic fallback: Activity or Description column + any qty-like column
        has_desc = any(v in vals for v in ("Activity", "Description", "Work Item", "Item Description"))
        has_qty  = any(v in vals for v in ("Qty", "Quantity", "Takeoff Qty", "Take-off Qty"))
        if has_desc and has_qty:
            return "format1_simple", row_idx
    return None, -1


def _infer_division_from_description(description: str) -> str | None:
    """Fallback CSI division inference from description keywords."""
    return _wbs_to_division(description)


def load_winest_project(db, file_path: str, project_metadata: dict) -> dict:
    """Load one WinEst XLSX into the DB.

    project_metadata keys: name, client, location, project_type, market_sector,
    region, delivery_method, contract_type, scope_types, complexity_level,
    data_quality_score (float, default 0.6)

    Returns: {project_id, project_name, observations_loaded, format_detected}
    """
    import pandas as pd

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    df = pd.read_excel(file_path, header=None)
    fmt, header_row = _detect_format(df)

    if fmt is None:
        raise ValueError(
            f"Unsupported WinEst format in {os.path.basename(file_path)}. "
            "Expected headers: (WBS/Description/Quantity) or (Description/Takeoff Qty)."
        )

    # Rebuild with detected header row
    headers = [str(v).strip() for v in df.iloc[header_row].tolist()]
    data = df.iloc[header_row + 1:].reset_index(drop=True)
    data.columns = range(len(headers))

    # Normalize headers: strip newlines and extra whitespace
    headers = [h.replace("\n", " ").replace("\r", " ").strip() for h in headers]

    # Map header names → column indices
    col = {name: idx for idx, name in enumerate(headers)}

    # Handle duplicate project names
    name = project_metadata.get("name", os.path.splitext(os.path.basename(file_path))[0])
    base_name = name
    suffix = 2
    while db.query(ComparableProject).filter(ComparableProject.name == name).first():
        name = f"{base_name} ({suffix})"
        suffix += 1

    proj = ComparableProject(
        id=_uuid(),
        name=name,
        client=project_metadata.get("client"),
        location=project_metadata.get("location"),
        project_type=project_metadata.get("project_type", "commercial"),
        market_sector=project_metadata.get("market_sector", "commercial"),
        region=project_metadata.get("region", "michigan"),
        delivery_method=project_metadata.get("delivery_method", "cmar"),
        contract_type=project_metadata.get("contract_type", "self_perform"),
        scope_types=project_metadata.get("scope_types", '["concrete","sitework"]'),
        complexity_level=project_metadata.get("complexity_level", "medium"),
        data_quality_score=float(project_metadata.get("data_quality_score", 0.6)),
        source_system="winest",
    )
    db.add(proj)
    db.commit()

    obs_count = 0
    dq = 0.7 if fmt == "format1" else 0.5  # Format 1 has cost breakdown cols → higher quality

    for row_idx, row in data.iterrows():
        # Description column — try multiple header names
        desc_col = (col.get("Description") or col.get("Activity") or
                    col.get("Work Item") or col.get("Item Description"))
        description = str(row[desc_col]).strip() if desc_col is not None else ""
        if _is_skip(description):
            continue

        # Quantity column — try multiple header names
        qty_col = (col.get("Quantity") or col.get("Takeoff Qty") or col.get("Qty") or
                   col.get("Take-off Qty"))
        quantity = _safe_float(row[qty_col]) if qty_col is not None else None
        if quantity is None or quantity == 0:
            continue

        # Unit column
        unit_col = col.get("Unit") or col.get("UOM")
        unit = str(row[unit_col]).strip() if unit_col is not None else None
        unit = unit if unit and unit.lower() != "nan" else None

        # WBS / division
        wbs_col = col.get("WBS") or col.get("Level")
        wbs = str(row[wbs_col]).strip() if wbs_col is not None else ""
        division_code = _wbs_to_division(wbs) or _infer_division_from_description(description)

        # Cost columns (Format 1 preferred)
        labor_cost = None
        material_cost = None
        equipment_cost = None
        sub_cost = None
        total_cost = None
        unit_cost = None
        production_rate = None

        if fmt == "format3_productivity":
            # Productivity update format: has Current Prod Rate + Hist Avg Prod Rate
            rate_col     = col.get("Current Prod Rate") or col.get("Prod Rate")
            hist_col     = col.get("Hist Avg Prod Rate") or col.get("Avg Prod Rate")
            prod_rate    = _safe_float(row[rate_col]) if rate_col is not None else None
            hist_rate    = _safe_float(row[hist_col]) if hist_col is not None else None
            production_rate = prod_rate or hist_rate
            if production_rate and production_rate > 0:
                unit_cost = round(ASSUMED_LABOR_RATE_PER_MH / production_rate, 4)
                labor_cost = unit_cost
            dq = 0.55  # derived cost, no dollar data

        elif fmt in ("format1", "format1_simple"):
            labor_col   = col.get("Labor $") or col.get("Labor Cost") or col.get("Labor MH") or col.get("Labor Hours")
            mat_col     = col.get("Material $") or col.get("Material Cost") or col.get("Material")
            equip_col   = col.get("Equipment $") or col.get("Equipment Cost") or col.get("Equipment")
            sub_col     = col.get("Sub $") or col.get("Subcontract") or col.get("Sub")
            total_col   = col.get("Total $") or col.get("Total") or col.get("Cost")
            labor_mh_col = col.get("Labor MH") or col.get("Labor Hours") or col.get("MH")

            labor_cost    = _safe_float(row[labor_col])   if labor_col is not None else None
            material_cost = _safe_float(row[mat_col])     if mat_col is not None else None
            equipment_cost= _safe_float(row[equip_col])   if equip_col is not None else None
            sub_cost      = _safe_float(row[sub_col])     if sub_col is not None else None
            total_cost    = _safe_float(row[total_col])   if total_col is not None else None
            labor_mh      = _safe_float(row[labor_mh_col])if labor_mh_col is not None else None

            if total_cost and total_cost > 0 and quantity > 0:
                unit_cost = round(total_cost / quantity, 4)
            elif labor_cost and labor_cost > 0 and quantity > 0:
                unit_cost = round(labor_cost / quantity, 4)

            # Production rate = quantity / labor_mh
            if labor_mh and labor_mh > 0 and quantity > 0:
                production_rate = round(quantity / labor_mh, 4)

        else:  # format2
            unit_cost_col = col.get("Unit Cost") or col.get("Unit $") or col.get("Rate")
            total_col     = col.get("Total") or col.get("Total $") or col.get("Cost")
            unit_cost_raw = _safe_float(row[unit_cost_col]) if unit_cost_col is not None else None
            total_cost    = _safe_float(row[total_col])     if total_col is not None else None

            if unit_cost_raw and unit_cost_raw > 0:
                unit_cost = unit_cost_raw
            elif total_cost and total_cost > 0 and quantity > 0:
                unit_cost = round(total_cost / quantity, 4)

        # Fallback: derive unit_cost from production_rate if still missing
        if unit_cost is None and production_rate and production_rate > 0:
            unit_cost = round(ASSUMED_LABOR_RATE_PER_MH / production_rate, 4)
            dq = min(dq, 0.5)  # lower quality for derived cost

        # Skip rows with no usable cost or rate data
        if unit_cost is None:
            continue

        db.add(HistoricalRateObservation(
            id=_uuid(),
            comparable_project_id=proj.id,
            raw_activity_name=description,
            division_code=division_code,
            quantity=quantity,
            unit=unit,
            unit_cost=unit_cost,
            total_cost=total_cost if total_cost else (unit_cost * quantity if unit_cost else None),
            labor_cost=labor_cost,
            material_cost=material_cost,
            equipment_cost=equipment_cost,
            sub_cost=sub_cost,
            production_rate=production_rate,
            production_rate_unit="unit/MH" if production_rate else None,
            data_quality_score=dq,
            source_row=int(row_idx),
        ))
        obs_count += 1

    db.commit()
    return {
        "project_id": proj.id,
        "project_name": name,
        "observations_loaded": obs_count,
        "format_detected": fmt,
    }


def bulk_load(db, manifest: list[dict]) -> list[dict]:
    """Load multiple WinEst projects from a manifest list.

    Each item: {file_path, metadata}
    """
    results = []
    for i, item in enumerate(manifest, 1):
        fpath = item["file_path"]
        meta = item.get("metadata", {})
        fname = os.path.basename(fpath)
        print(f"  [{i}/{len(manifest)}] {fname} ...", end=" ", flush=True)
        try:
            result = load_winest_project(db, fpath, meta)
            print(f"✓ {result['observations_loaded']} obs ({result['format_detected']})")
            results.append(result)
        except FileNotFoundError as e:
            print(f"SKIP: {e}")
        except ValueError as e:
            print(f"SKIP (unsupported format): {e}")
        except Exception as e:
            print(f"ERROR: {e}")
    return results


def run_directory(data_dir: str = None) -> None:
    """Scan a directory for .xlsx files and bulk-load them."""
    if not data_dir:
        data_dir = os.environ.get(
            "WINEST_EXPORT_DIR",
            os.path.join(_here, "data", "winest"),
        )

    if not os.path.isdir(data_dir):
        print(f"Directory not found: {data_dir}")
        print(f"Create it and add WinEst XLSX exports: mkdir -p {data_dir}")
        return

    xlsx_files = [f for f in os.listdir(data_dir) if f.lower().endswith((".xlsx", ".xls"))]
    if not xlsx_files:
        print(f"No XLSX files found in {data_dir}")
        return

    print(f"Found {len(xlsx_files)} XLSX files in {data_dir}")

    # Default metadata — use filename as project name
    manifest = []
    for fname in xlsx_files:
        proj_name = os.path.splitext(fname)[0].replace("_", " ").replace("-", " ").strip()
        manifest.append({
            "file_path": os.path.join(data_dir, fname),
            "metadata": {
                "name": proj_name,
                "project_type": "commercial",
                "market_sector": "commercial",
                "region": "michigan",
                "delivery_method": "cmar",
                "contract_type": "self_perform",
                "complexity_level": "medium",
                "data_quality_score": 0.6,
            },
        })

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        results = bulk_load(db, manifest)
        total_obs = sum(r["observations_loaded"] for r in results)
        cp_total = db.query(ComparableProject).count()
        obs_total = db.query(HistoricalRateObservation).count()

        print()
        print("BULK LOAD COMPLETE")
        print(f"New projects: {len(results)}")
        print(f"New observations: {total_obs}")
        print(f"Total in database: {cp_total} projects, {obs_total} observations")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Load a WinEst XLSX file into the decision system.")
    parser.add_argument("file_path", help="Path to WinEst XLSX export")
    parser.add_argument("project_name", nargs="?", help="Project name (defaults to filename)")
    parser.add_argument("--client", default=None)
    parser.add_argument("--location", default=None)
    parser.add_argument("--type", dest="project_type", default="commercial",
                        choices=["industrial","commercial","institutional","healthcare",
                                 "education","data_center","infrastructure"])
    parser.add_argument("--market", dest="market_sector", default="commercial")
    parser.add_argument("--region", default="michigan")
    parser.add_argument("--delivery", dest="delivery_method", default="cmar")
    parser.add_argument("--contract", dest="contract_type", default="self_perform")
    parser.add_argument("--complexity", default="medium", choices=["low","medium","high"])
    parser.add_argument("--quality", dest="data_quality_score", type=float, default=0.6)
    args = parser.parse_args()

    proj_name = args.project_name or os.path.splitext(os.path.basename(args.file_path))[0]
    metadata = {
        "name": proj_name,
        "client": args.client,
        "location": args.location,
        "project_type": args.project_type,
        "market_sector": args.market_sector,
        "region": args.region,
        "delivery_method": args.delivery_method,
        "contract_type": args.contract_type,
        "complexity_level": args.complexity,
        "data_quality_score": args.data_quality_score,
    }

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        result = load_winest_project(db, args.file_path, metadata)
        cp_total = db.query(ComparableProject).count()
        obs_total = db.query(HistoricalRateObservation).count()
        print(f"✓ Loaded: {result['project_name']}")
        print(f"  Observations: {result['observations_loaded']} ({result['format_detected']})")
        print()
        print("BULK LOAD COMPLETE")
        print(f"New projects: 1")
        print(f"New observations: {result['observations_loaded']}")
        print(f"Total in database: {cp_total} projects, {obs_total} observations")
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
