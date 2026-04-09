"""Decision system data seeder — loads Christman historical productivity data.

Separate from seed.py (demo data). Safe to run multiple times; skips if already seeded.
"""

import logging
import os
from apex.backend.db.database import Base, SessionLocal
from apex.backend.models.decision_models import (
    CanonicalActivity,
    ComparableProject,
    HistoricalRateObservation,
)

logger = logging.getLogger("apex.seed_decision")

# ---------------------------------------------------------------------------
# Canonical ontology — 24 activities
# ---------------------------------------------------------------------------
_CANONICAL_ACTIVITIES = [
    ("CIP Concrete Foundation",         "03 30 00", "CY",  "concrete"),
    ("CIP Concrete Slab on Grade",       "03 30 00", "CY",  "concrete"),
    ("CIP Concrete Wall",               "03 30 00", "CY",  "concrete"),
    ("Formwork — Foundation",           "03 10 00", "SF",  "concrete"),
    ("Formwork — Wall",                 "03 10 00", "SF",  "concrete"),
    ("Formwork — Slab Edge",            "03 10 00", "LF",  "concrete"),
    ("Rebar — Foundations",             "03 20 00", "TON", "concrete"),
    ("Rebar — Slabs",                   "03 20 00", "TON", "concrete"),
    ("Rebar — Walls",                   "03 20 00", "TON", "concrete"),
    ("Concrete Placement — Pump",       "03 30 00", "CY",  "concrete"),
    ("Concrete Placement — Direct",     "03 30 00", "CY",  "concrete"),
    ("Concrete Finishing — Broom",      "03 35 00", "SF",  "concrete"),
    ("Concrete Finishing — Trowel",     "03 35 00", "SF",  "concrete"),
    ("Concrete Curing",                 "03 39 00", "SF",  "concrete"),
    ("Sawcutting",                      "03 35 00", "LF",  "concrete"),
    ("Excavation — Machine",            "31 23 00", "CY",  "sitework"),
    ("Backfill",                        "31 23 00", "CY",  "sitework"),
    ("Fine Grade — Hand",               "31 22 00", "SF",  "sitework"),
    ("Fine Grade — Machine",            "31 22 00", "SF",  "sitework"),
    ("Embeds / Anchor Bolts",           "03 15 00", "EA",  "concrete"),
    ("Waterstop",                       "03 15 00", "LF",  "concrete"),
    ("Expansion Joints",                "03 15 00", "LF",  "concrete"),
    ("Dampproofing",                    "07 11 00", "SF",  "waterproofing"),
    ("Vapor Barrier",                   "07 26 00", "SF",  "concrete"),
]


def seed_canonical_ontology(db):
    """Insert 24 CanonicalActivity rows if they don't already exist."""
    existing_names = {r[0] for r in db.query(CanonicalActivity.name).all()}
    added = 0
    for name, division_code, expected_unit, scope_family in _CANONICAL_ACTIVITIES:
        if name not in existing_names:
            db.add(CanonicalActivity(
                name=name,
                division_code=division_code,
                expected_unit=expected_unit,
                scope_family=scope_family,
            ))
            added += 1
    db.flush()
    logger.info("Canonical ontology: added %d activities", added)
    return added


# ---------------------------------------------------------------------------
# WBS → CSI division helper
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# CityGate loader
# ---------------------------------------------------------------------------
_CITYGATE_PROJECTS = [
    ("Flint City Gate",   "Flint"),
    ("Bancroft City Gate","Bancroft"),
    ("Hanover City Gate", "Hanover"),
    ("Highland City Gate","Highland"),
]

_CITYGATE_COL_OFFSET = 5  # columns 5-8 → project data


def load_citygate_rates(db, data_dir: str):
    """Parse CityGate_Master_Productivity_Rates_1.xlsx → 4 ComparableProject rows."""
    try:
        import pandas as pd
    except ImportError:
        logger.warning("pandas not available; skipping CityGate loader")
        return 0

    path = os.path.join(data_dir, "CityGate_Master_Productivity_Rates_1.xlsx")
    if not os.path.exists(path):
        logger.warning("CityGate file not found at %s", path)
        return 0

    df = pd.read_excel(path, sheet_name="Averaged Prod Rates", header=None)

    # Row 3 (index 2) is the header; data from row 4 (index 3)
    data = df.iloc[3:].reset_index(drop=True)

    # Create the 4 ComparableProject rows
    _common = dict(
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
    for name, _ in _CITYGATE_PROJECTS:
        proj = ComparableProject(name=name, **_common)
        db.add(proj)
        db.flush()
        projects.append(proj)

    current_wbs = ""
    obs_count = 0

    for _, row in data.iterrows():
        col0 = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
        col1 = row.iloc[1]
        col2 = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ""
        col3 = str(row.iloc[3]).strip() if pd.notna(row.iloc[3]) else ""

        # Track WBS area
        if pd.isna(col1) and col0:
            current_wbs = col0
            continue

        # Skip empty or dashes
        if pd.isna(col1) or str(col1).strip() in ("", "—", "–", "-", "nan"):
            continue
        activity = str(col1).strip()
        if activity in ("—", "–", "-"):
            continue

        unit = col2 or None
        division_code = _wbs_to_division(current_wbs)

        # Average productivity (col 4)
        try:
            avg_prod = float(str(row.iloc[4]).replace(",", "").strip())
        except (ValueError, TypeError):
            avg_prod = None

        # Labor $/unit (col 11), Mat $/unit (col 12)
        try:
            avg_labor = float(str(row.iloc[11]).replace(",", "").strip())
        except (ValueError, TypeError):
            avg_labor = None
        try:
            avg_mat = float(str(row.iloc[12]).replace(",", "").strip())
        except (ValueError, TypeError):
            avg_mat = None

        unit_cost = None
        if avg_labor is not None and avg_mat is not None:
            unit_cost = avg_labor + avg_mat
        elif avg_labor is not None:
            unit_cost = avg_labor
        elif avg_prod and avg_prod > 0:
            unit_cost = round(85.0 / avg_prod, 4)

        for proj_idx, (proj_obj, (_, _loc)) in enumerate(zip(projects, _CITYGATE_PROJECTS)):
            col_idx = _CITYGATE_COL_OFFSET + proj_idx
            try:
                prod_val = float(str(row.iloc[col_idx]).replace(",", "").strip())
            except (ValueError, TypeError):
                prod_val = None

            obs = HistoricalRateObservation(
                comparable_project_id=proj_obj.id,
                raw_activity_name=activity,
                division_code=division_code,
                unit=unit,
                production_rate=prod_val,
                unit_cost=unit_cost,
                data_quality_score=0.8,
            )
            db.add(obs)
            obs_count += 1

    db.flush()
    logger.info("CityGate: loaded %d observations across 4 projects", obs_count)
    return obs_count


# ---------------------------------------------------------------------------
# Leonidas + Spring Arbor loader
# ---------------------------------------------------------------------------
_LEONIDAS_PROJECTS = [
    ("Leonidas",     "Leonidas"),
    ("Spring Arbor", "Spring Arbor"),
]


def load_leonidas_spring_arbor(db, data_dir: str):
    """Parse Leonidas_SpringArbor_Productivity_Updates_version_1.xlsx."""
    try:
        import pandas as pd
    except ImportError:
        logger.warning("pandas not available; skipping Leonidas loader")
        return 0

    path = os.path.join(
        data_dir,
        "Leonidas_SpringArbor_Productivity_Updates_version_1.xlsx",
    )
    if not os.path.exists(path):
        logger.warning("Leonidas file not found at %s", path)
        return 0

    _common = dict(
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

    obs_count = 0

    for sheet_name, proj_name in _LEONIDAS_PROJECTS:
        try:
            df = pd.read_excel(path, sheet_name=sheet_name, header=None)
        except Exception as e:
            logger.warning("Could not read sheet '%s': %s", sheet_name, e)
            continue

        proj = ComparableProject(name=proj_name, **_common)
        db.add(proj)
        db.flush()

        data = df.iloc[3:].reset_index(drop=True)

        for _, row in data.iterrows():
            # Col 2: Activity description
            col2 = row.iloc[2] if len(row) > 2 else None
            if pd.isna(col2) or str(col2).strip() in ("", "nan", "—", "–", "-"):
                continue
            activity = str(col2).strip()
            if activity.upper().startswith("PROD"):
                continue

            # Col 1: WBS
            wbs = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
            # Col 4: Unit
            unit = str(row.iloc[4]).strip() if len(row) > 4 and pd.notna(row.iloc[4]) else None
            # Col 6: Current Prod Rate
            prod_rate = None
            if len(row) > 6:
                try:
                    prod_rate = float(str(row.iloc[6]).replace(",", "").strip())
                except (ValueError, TypeError):
                    pass

            division_code = _wbs_to_division(wbs)
            unit_cost = None
            dq = 0.7
            if prod_rate and prod_rate > 0:
                unit_cost = round(85.0 / prod_rate, 4)
                dq = 0.65

            obs = HistoricalRateObservation(
                comparable_project_id=proj.id,
                raw_activity_name=activity,
                division_code=division_code,
                unit=unit,
                production_rate=prod_rate,
                unit_cost=unit_cost,
                data_quality_score=dq,
            )
            db.add(obs)
            obs_count += 1

    db.flush()
    logger.info("Leonidas/SpringArbor: loaded %d observations", obs_count)
    return obs_count


# ---------------------------------------------------------------------------
# Estimation history loader
# ---------------------------------------------------------------------------

def load_estimation_history(db, data_dir: str):
    """Parse EstimationHistory_Enhanced.xlsx → one ComparableProject per row."""
    try:
        import pandas as pd
    except ImportError:
        logger.warning("pandas not available; skipping EstimationHistory loader")
        return 0

    path = os.path.join(data_dir, "EstimationHistory_Enhanced.xlsx")
    if not os.path.exists(path):
        logger.warning("EstimationHistory file not found at %s", path)
        return 0

    df = pd.read_excel(path, sheet_name="Estimating")

    proj_count = 0

    for _, row in df.iterrows():
        def _safe(col):
            v = row.get(col)
            return str(v).strip() if v is not None and not (isinstance(v, float) and __import__('math').isnan(v)) else None

        name = _safe("Name") or f"Estimation History #{proj_count + 1}"
        region = (_safe("Region") or "unknown").lower().replace(" ", "_")
        market_sector = (_safe("Market Sector") or "commercial").lower().replace(" ", "_")
        project_type = market_sector
        location = _safe("Location")
        delivery = (_safe("Delivery Method") or "").lower().replace(" ", "_") or None

        contract_amount = None
        for col in ("Contract Amount", "Bid Amount"):
            v = row.get(col)
            if v is not None:
                try:
                    contract_amount = float(str(v).replace(",", "").replace("$", "").strip())
                    break
                except (ValueError, TypeError):
                    pass

        size_sf = None
        v = row.get("Building SF")
        if v is not None:
            try:
                size_sf = float(str(v).replace(",", "").strip())
            except (ValueError, TypeError):
                pass

        proj = ComparableProject(
            name=name,
            location=location,
            project_type=project_type,
            market_sector=market_sector,
            region=region,
            delivery_method=delivery,
            final_contract_value=contract_amount,
            size_sf=size_sf,
            data_quality_score=0.4,
            source_system="estimation_history",
        )
        db.add(proj)
        proj_count += 1

    db.flush()
    logger.info("EstimationHistory: loaded %d projects", proj_count)
    return proj_count


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_decision_seed(data_dir: str = None):
    """Find data directory, create tables, skip if already seeded, then run loaders."""
    # Resolve data directory
    if data_dir is None:
        data_dir = os.getenv("SEED_DATA_DIR")
    if not data_dir:
        candidates = [
            os.path.join(os.path.dirname(__file__), "data"),
            "/workspaces/EstimatingEngine",
        ]
        for candidate in candidates:
            if os.path.isdir(candidate):
                data_dir = candidate
                break
    if not data_dir:
        data_dir = os.path.join(os.path.dirname(__file__), "data")

    # Create all decision system tables
    Base.metadata.create_all(bind=__import__('apex.backend.db.database', fromlist=['engine']).engine)

    db = SessionLocal()
    try:
        count = db.query(ComparableProject).count()
        if count > 0:
            logger.info("Decision seed already present (%d projects); skipping.", count)
            return

        logger.info("Seeding decision system from %s", data_dir)
        seed_canonical_ontology(db)
        citygate_obs = load_citygate_rates(db, data_dir)
        leonidas_obs = load_leonidas_spring_arbor(db, data_dir)
        hist_projs = load_estimation_history(db, data_dir)
        db.commit()

        total_projects = db.query(ComparableProject).count()
        total_obs = db.query(HistoricalRateObservation).count()
        total_activities = db.query(CanonicalActivity).count()

        print(
            f"[decision-seed] Done — "
            f"{total_projects} comparable projects, "
            f"{total_obs} rate observations, "
            f"{total_activities} canonical activities"
        )
    except Exception:
        db.rollback()
        logger.exception("Decision seed failed")
        raise
    finally:
        db.close()
