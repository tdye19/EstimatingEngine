"""Seed script — load Christman historical productivity data into decision system models."""

import os
import sys
import uuid
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Path setup so this script can be run directly or imported
# ---------------------------------------------------------------------------
_here = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(_here)))
for _p in (_repo_root, os.path.dirname(_here)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from apex.backend.db.database import engine, SessionLocal, Base
from apex.backend.models.decision_models import (
    ComparableProject,
    HistoricalRateObservation,
    CanonicalActivity,
    FieldActual,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uuid() -> str:
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc)


def _find_data_dir() -> str:
    """Return the first directory that exists and may contain Excel files."""
    candidates = [
        os.environ.get("SEED_DATA_DIR", ""),
        os.path.join(_here, "data"),
        os.getcwd(),
        "/workspaces/EstimatingEngine",
        _repo_root,
    ]
    for c in candidates:
        if c and os.path.isdir(c):
            return c
    return os.getcwd()


def _wbs_to_division(wbs: str) -> str | None:
    """Map WBS area name to CSI division code."""
    if not wbs:
        return None
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
    return None


# ---------------------------------------------------------------------------
# Seed canonical ontology
# ---------------------------------------------------------------------------

CANONICAL_ACTIVITIES = [
    ("CIP Concrete Foundation",       "03 30 00", "Cast-in-Place Concrete",   "CY",  "concrete"),
    ("CIP Concrete Slab on Grade",    "03 30 00", "Cast-in-Place Concrete",   "CY",  "concrete"),
    ("CIP Concrete Wall",             "03 30 00", "Cast-in-Place Concrete",   "CY",  "concrete"),
    ("Formwork — Foundation",         "03 10 00", "Concrete Forming",         "SF",  "concrete"),
    ("Formwork — Wall",               "03 10 00", "Concrete Forming",         "SF",  "concrete"),
    ("Formwork — Slab Edge",          "03 10 00", "Concrete Forming",         "LF",  "concrete"),
    ("Rebar — Foundations",           "03 20 00", "Concrete Reinforcing",     "TON", "concrete"),
    ("Rebar — Slabs",                 "03 20 00", "Concrete Reinforcing",     "TON", "concrete"),
    ("Rebar — Walls",                 "03 20 00", "Concrete Reinforcing",     "TON", "concrete"),
    ("Concrete Placement — Pump",     "03 30 00", "Cast-in-Place Concrete",   "CY",  "concrete"),
    ("Concrete Placement — Direct",   "03 30 00", "Cast-in-Place Concrete",   "CY",  "concrete"),
    ("Concrete Finishing — Broom",    "03 35 00", "Concrete Finishing",       "SF",  "concrete"),
    ("Concrete Finishing — Trowel",   "03 35 00", "Concrete Finishing",       "SF",  "concrete"),
    ("Concrete Curing",               "03 39 00", "Concrete Curing",          "SF",  "concrete"),
    ("Sawcutting",                    "03 35 00", "Concrete Finishing",       "LF",  "concrete"),
    ("Excavation — Machine",          "31 23 00", "Excavation and Fill",      "CY",  "sitework"),
    ("Backfill",                      "31 23 00", "Excavation and Fill",      "CY",  "sitework"),
    ("Fine Grade — Hand",             "31 22 00", "Grading",                  "SF",  "sitework"),
    ("Fine Grade — Machine",          "31 22 00", "Grading",                  "SF",  "sitework"),
    ("Embeds / Anchor Bolts",         "03 15 00", "Concrete Accessories",     "EA",  "concrete"),
    ("Waterstop",                     "03 15 00", "Concrete Accessories",     "LF",  "concrete"),
    ("Expansion Joints",              "03 15 00", "Concrete Accessories",     "LF",  "concrete"),
    ("Dampproofing",                  "07 11 00", "Dampproofing",             "SF",  "waterproofing"),
    ("Vapor Barrier",                 "07 26 00", "Vapor Retarders",          "SF",  "concrete"),
]


def seed_canonical_ontology(db) -> int:
    """Insert canonical activity rows (skip duplicates by name)."""
    existing = {r.name for r in db.query(CanonicalActivity).all()}
    added = 0
    for name, div_code, div_name, unit, scope in CANONICAL_ACTIVITIES:
        if name in existing:
            continue
        db.add(CanonicalActivity(
            id=_uuid(),
            name=name,
            division_code=div_code,
            division_name=div_name,
            expected_unit=unit,
            scope_family=scope,
            typical_cost_bucket="labor_material",
        ))
        added += 1
    db.commit()
    return added


# ---------------------------------------------------------------------------
# CityGate rates loader
# ---------------------------------------------------------------------------

def load_citygate_rates(db, data_dir: str) -> int:
    """Load CityGate_Master_Productivity_Rates_1.xlsx if present."""
    import pandas as pd

    xlsx_path = os.path.join(data_dir, "CityGate_Master_Productivity_Rates_1.xlsx")
    if not os.path.exists(xlsx_path):
        print(f"  [SKIP] CityGate file not found at {xlsx_path}")
        return 0

    project_names = [
        "Flint City Gate",
        "Bancroft City Gate",
        "Hanover City Gate",
        "Highland City Gate",
    ]
    common_ctx = dict(
        client="Consumers Energy",
        location="Michigan",
        project_type="industrial",
        market_sector="energy",
        region="michigan",
        delivery_method="cmar",
        contract_type="self_perform",
        scope_types='["concrete","sitework"]',
        complexity_level="medium",
        data_quality_score=0.8,
        source_system="winest",
    )

    projects = []
    for pname in project_names:
        proj = ComparableProject(id=_uuid(), name=pname, **common_ctx)
        db.add(proj)
        projects.append(proj)
    db.commit()

    # Sheet: "Averaged Prod Rates", header at row 3 (0-indexed row 2), data from row 4
    df = pd.read_excel(xlsx_path, sheet_name="Averaged Prod Rates", header=None)
    # Row index 2 = header row, row 3+ = data
    col_names = df.iloc[2].tolist()
    data = df.iloc[3:].reset_index(drop=True)
    data.columns = range(len(data.columns))

    added = 0
    current_wbs = None

    for _, row in data.iterrows():
        col0 = str(row[0]).strip() if pd.notna(row[0]) else ""
        col1 = str(row[1]).strip() if pd.notna(row[1]) else ""

        # Update WBS area when col1 is empty and col0 has content
        if col0 and not col1:
            current_wbs = col0
            continue

        # Skip section headers (contain em-dash) or empty activity
        if not col1 or "—" in col1 or "TOTAL" in col1.upper():
            continue

        unit = str(row[2]).strip() if pd.notna(row[2]) else None

        def safe_float(val):
            try:
                f = float(val)
                return f if f == f else None  # filter NaN
            except (TypeError, ValueError):
                return None

        avg_labor = safe_float(row[11]) if len(row) > 11 else None
        avg_mat = safe_float(row[12]) if len(row) > 12 else None
        unit_cost = None
        if avg_labor is not None or avg_mat is not None:
            unit_cost = (avg_labor or 0.0) + (avg_mat or 0.0)

        division_code = _wbs_to_division(current_wbs or "")

        # Cols 5-8 are the four project-specific production rates
        for idx, proj in enumerate(projects):
            rate_col = 5 + idx
            prod_rate = safe_float(row[rate_col]) if len(row) > rate_col else None
            if prod_rate is None:
                continue
            db.add(HistoricalRateObservation(
                id=_uuid(),
                comparable_project_id=proj.id,
                raw_activity_name=col1,
                division_code=division_code,
                unit=unit,
                unit_cost=unit_cost,
                labor_cost=avg_labor,
                material_cost=avg_mat,
                production_rate=prod_rate,
                data_quality_score=0.8,
            ))
            added += 1

    db.commit()
    return added


# ---------------------------------------------------------------------------
# Leonidas + Spring Arbor loader
# ---------------------------------------------------------------------------

def load_leonidas_spring_arbor(db, data_dir: str) -> int:
    """Load Leonidas_SpringArbor_Productivity_Updates_version_1.xlsx."""
    import pandas as pd

    xlsx_path = os.path.join(data_dir, "Leonidas_SpringArbor_Productivity_Updates_version_1.xlsx")
    if not os.path.exists(xlsx_path):
        print(f"  [SKIP] Leonidas/SpringArbor file not found at {xlsx_path}")
        return 0

    common_ctx = dict(
        client="Consumers Energy",
        location="Michigan",
        project_type="industrial",
        market_sector="energy",
        region="michigan",
        delivery_method="cmar",
        contract_type="self_perform",
        scope_types='["concrete","sitework"]',
        complexity_level="medium",
        data_quality_score=0.7,
        source_system="winest",
    )

    added = 0
    for sheet_name in ["Leonidas", "Spring Arbor"]:
        try:
            df = pd.read_excel(xlsx_path, sheet_name=sheet_name, header=None)
        except Exception as e:
            print(f"  [WARN] Could not read sheet '{sheet_name}': {e}")
            continue

        proj = ComparableProject(id=_uuid(), name=sheet_name, **common_ctx)
        db.add(proj)
        db.commit()

        # Row index 2 = header, row 3+ = data
        if len(df) < 4:
            continue
        data = df.iloc[3:].reset_index(drop=True)

        for _, row in data.iterrows():
            activity = str(row[2]).strip() if len(row) > 2 and pd.notna(row[2]) else ""
            if not activity or activity == "nan" or "—" in activity or activity.upper().startswith("PROD"):
                continue

            def safe_float(val):
                try:
                    f = float(val)
                    return f if f == f else None
                except (TypeError, ValueError):
                    return None

            qty = safe_float(row[3]) if len(row) > 3 else None
            unit = str(row[4]).strip() if len(row) > 4 and pd.notna(row[4]) else None
            prod_rate = safe_float(row[6]) if len(row) > 6 else None
            wbs = str(row[1]).strip() if len(row) > 1 and pd.notna(row[1]) else ""

            db.add(HistoricalRateObservation(
                id=_uuid(),
                comparable_project_id=proj.id,
                raw_activity_name=activity,
                division_code=_wbs_to_division(wbs),
                quantity=qty,
                unit=unit,
                production_rate=prod_rate,
                data_quality_score=0.7,
            ))
            added += 1

        db.commit()

    return added


# ---------------------------------------------------------------------------
# Estimation history loader
# ---------------------------------------------------------------------------

def load_estimation_history(db, data_dir: str) -> int:
    """Load EstimationHistory_Enhanced.xlsx — project-level records only."""
    import pandas as pd

    xlsx_path = os.path.join(data_dir, "EstimationHistory_Enhanced.xlsx")
    if not os.path.exists(xlsx_path):
        print(f"  [SKIP] EstimationHistory file not found at {xlsx_path}")
        return 0

    df = pd.read_excel(xlsx_path, sheet_name="Estimating")
    added = 0

    for _, row in df.iterrows():
        def col(name, default=None):
            if name in row.index and pd.notna(row[name]):
                return row[name]
            return default

        # Derive name from "Name" column (fallback to index)
        name = str(col("Name", "Unknown Project")).strip()
        if not name or name == "nan":
            continue

        def norm(val):
            if val is None:
                return None
            return str(val).lower().replace(" ", "_").replace("-", "_")

        def safe_float(val):
            try:
                return float(val)
            except (TypeError, ValueError):
                return None

        contract_val = safe_float(col("Contract Amount")) or safe_float(col("Bid Amount"))

        db.add(ComparableProject(
            id=_uuid(),
            name=name,
            location=str(col("Location", "")) or None,
            project_type=norm(col("Market Sector")),
            market_sector=norm(col("Market Sector")),
            region=norm(col("Region")),
            delivery_method=norm(col("Delivery Method")),
            final_contract_value=contract_val,
            size_sf=safe_float(col("Building SF")),
            data_quality_score=0.4,
            source_system="estimation_history",
        ))
        added += 1

    db.commit()
    return added


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run():
    """Create tables, check if already seeded, load all data, print summary."""
    # Create all decision system tables (safe — only creates missing ones)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        existing_count = db.query(ComparableProject).count()
        if existing_count > 0:
            print(f"Already seeded ({existing_count} comparable projects). Skipping.")
            return

        data_dir = _find_data_dir()
        print(f"Loading seed data from: {data_dir}")

        print("  Seeding canonical ontology...")
        canon_added = seed_canonical_ontology(db)

        print("  Loading CityGate rates...")
        cg_obs = load_citygate_rates(db, data_dir)

        print("  Loading Leonidas + Spring Arbor...")
        ls_obs = load_leonidas_spring_arbor(db, data_dir)

        print("  Loading estimation history...")
        hist_added = load_estimation_history(db, data_dir)

        total_projects = db.query(ComparableProject).count()
        total_obs = db.query(HistoricalRateObservation).count()
        total_canon = db.query(CanonicalActivity).count()

        print()
        print("SEED COMPLETE")
        print(f"Comparable projects: {total_projects}")
        print(f"Rate observations: {total_obs}")
        print(f"Canonical activities: {total_canon}")

    finally:
        db.close()


if __name__ == "__main__":
    run()
