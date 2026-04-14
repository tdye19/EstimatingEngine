"""Canonical estimating ontology seed data.

Architecture §11: The system needs a controlled vocabulary for work items.
This is the shared language between scope extraction, takeoff mapping,
historical data, field actuals, and estimator review.

Run with:  python -m apex.backend.db.ontology_seed
Or called from seed.py during initial DB setup.
"""

import json

from sqlalchemy.orm import Session

CANONICAL_ACTIVITIES = [
    # ── Division 01 — General Requirements ──────────────────────────────────
    {
        "name": "Mobilization",
        "division_code": "01 50 00",
        "division_name": "Temporary Facilities and Controls",
        "expected_unit": "LS",
        "scope_family": "general_requirements",
        "typical_cost_bucket": "general_conditions",
        "common_dependencies": json.dumps([]),
        "notes": "Includes site setup, office trailers, equipment staging.",
        "aliases": ["mob", "mob/demob", "mobilization/demobilization", "project startup"],
    },
    {
        "name": "Layout / Survey",
        "division_code": "01 71 23",
        "division_name": "Field Engineering",
        "expected_unit": "LS",
        "scope_family": "general_requirements",
        "typical_cost_bucket": "direct_labor",
        "common_dependencies": json.dumps(["Mobilization"]),
        "notes": "Control point establishment and construction layout.",
        "aliases": ["survey", "field layout", "staking", "construction survey"],
    },
    {
        "name": "Temporary Facilities",
        "division_code": "01 50 00",
        "division_name": "Temporary Facilities and Controls",
        "expected_unit": "LS",
        "scope_family": "general_requirements",
        "typical_cost_bucket": "general_conditions",
        "common_dependencies": json.dumps(["Mobilization"]),
        "notes": "Temporary power, water, sanitation, fencing.",
        "aliases": ["temp facilities", "temporary utilities", "temp power", "temp water"],
    },
    {
        "name": "Testing / Inspection",
        "division_code": "01 45 00",
        "division_name": "Quality Control",
        "expected_unit": "LS",
        "scope_family": "general_requirements",
        "typical_cost_bucket": "testing",
        "common_dependencies": json.dumps(["CIP Concrete Footings", "CIP Concrete Slabs"]),
        "notes": "Third-party materials testing, special inspections per IBC.",
        "aliases": ["special inspection", "materials testing", "QC testing", "testing and inspection"],
    },
    {
        "name": "Traffic Control",
        "division_code": "01 55 26",
        "division_name": "Traffic Control",
        "expected_unit": "LS",
        "scope_family": "general_requirements",
        "typical_cost_bucket": "general_conditions",
        "common_dependencies": json.dumps(["Mobilization"]),
        "notes": "Flaggers, signage, temporary traffic signals.",
        "aliases": ["flagging", "traffic management", "TCP"],
    },
    {
        "name": "Cleanup / Closeout",
        "division_code": "01 77 00",
        "division_name": "Closeout Procedures",
        "expected_unit": "LS",
        "scope_family": "general_requirements",
        "typical_cost_bucket": "general_conditions",
        "common_dependencies": json.dumps([]),
        "notes": "Final cleaning, punch list, demobilization.",
        "aliases": ["final clean", "demobilization", "closeout", "punch list"],
    },
    # ── Division 02 — Site Preparation ──────────────────────────────────────
    {
        "name": "Erosion Control",
        "division_code": "31 25 00",
        "division_name": "Erosion and Sedimentation Controls",
        "expected_unit": "LS",
        "scope_family": "sitework",
        "typical_cost_bucket": "direct_labor",
        "common_dependencies": json.dumps(["Mobilization"]),
        "notes": "SWPPP implementation, silt fence, inlet protection.",
        "aliases": ["SWPPP", "silt fence", "erosion and sediment control", "ESC"],
    },
    {
        "name": "Clearing and Grubbing",
        "division_code": "31 11 00",
        "division_name": "Clearing and Grubbing",
        "expected_unit": "AC",
        "scope_family": "sitework",
        "typical_cost_bucket": "direct_labor",
        "common_dependencies": json.dumps(["Erosion Control"]),
        "notes": "Tree removal, brush clearing, stump grubbing.",
        "aliases": ["clearing", "tree removal", "site clearing", "C&G"],
    },
    {
        "name": "Earthwork Excavation",
        "division_code": "31 23 16",
        "division_name": "Excavation",
        "expected_unit": "CY",
        "scope_family": "sitework",
        "typical_cost_bucket": "direct_labor",
        "common_dependencies": json.dumps(["Clearing and Grubbing", "Layout / Survey"]),
        "notes": "Mass excavation and grading. Includes haul to spoil or stockpile.",
        "aliases": ["mass excavation", "bulk earthwork", "cut and fill", "grading", "excavation"],
    },
    {
        "name": "Undercut / Proof Roll",
        "division_code": "31 23 23",
        "division_name": "Fill",
        "expected_unit": "CY",
        "scope_family": "sitework",
        "typical_cost_bucket": "direct_labor",
        "common_dependencies": json.dumps(["Earthwork Excavation"]),
        "notes": "Over-excavation and recompaction of unsuitable material.",
        "aliases": ["proof rolling", "subgrade repair", "subgrade undercut", "over-excavation"],
    },
    {
        "name": "Aggregate Base",
        "division_code": "32 11 23",
        "division_name": "Aggregate Base Courses",
        "expected_unit": "TN",
        "scope_family": "sitework",
        "typical_cost_bucket": "direct_material",
        "common_dependencies": json.dumps(["Earthwork Excavation"]),
        "notes": 'Crushed stone base, typically 6-12" compacted thickness.',
        "aliases": ["gravel base", "crushed stone", "ABC", "base course", "sub-base"],
    },
    {
        "name": "Dewatering",
        "division_code": "31 23 19",
        "division_name": "Dewatering",
        "expected_unit": "LS",
        "scope_family": "sitework",
        "typical_cost_bucket": "direct_equipment",
        "common_dependencies": json.dumps(["Earthwork Excavation", "CIP Concrete Footings"]),
        "notes": "Groundwater control during below-grade work. Often a risk allowance.",
        "aliases": ["well pointing", "pump and haul", "groundwater control"],
    },
    # ── Division 03 — Concrete ───────────────────────────────────────────────
    {
        "name": "Formwork",
        "division_code": "03 11 00",
        "division_name": "Concrete Forming",
        "expected_unit": "SFCA",
        "scope_family": "concrete",
        "typical_cost_bucket": "direct_labor",
        "common_dependencies": json.dumps(["Layout / Survey"]),
        "notes": "Structural formwork for footings, walls, slabs. Excludes SOG.",
        "aliases": ["concrete forming", "forms", "shoring", "falsework"],
    },
    {
        "name": "Rebar",
        "division_code": "03 21 00",
        "division_name": "Reinforcing Steel",
        "expected_unit": "TN",
        "scope_family": "concrete",
        "typical_cost_bucket": "direct_material",
        "common_dependencies": json.dumps(["Formwork"]),
        "notes": "Deformed reinforcing bar, placed and tied. Excludes PT.",
        "aliases": ["reinforcing steel", "reinforcing bar", "rebar installation", "#4 rebar", "#5 rebar"],
    },
    {
        "name": "CIP Concrete Footings",
        "division_code": "03 30 00",
        "division_name": "Cast-in-Place Concrete",
        "expected_unit": "CY",
        "scope_family": "concrete",
        "typical_cost_bucket": "direct_material",
        "common_dependencies": json.dumps(["Formwork", "Rebar", "Earthwork Excavation", "Testing / Inspection"]),
        "notes": "Spread, continuous, and pile cap footings. Unit cost includes labor+material+equipment.",
        "aliases": ["footings", "concrete footings", "spread footings", "foundation concrete"],
    },
    {
        "name": "CIP Concrete Walls",
        "division_code": "03 30 00",
        "division_name": "Cast-in-Place Concrete",
        "expected_unit": "CY",
        "scope_family": "concrete",
        "typical_cost_bucket": "direct_material",
        "common_dependencies": json.dumps(["Formwork", "Rebar", "Dewatering"]),
        "notes": "Below-grade and above-grade structural walls.",
        "aliases": ["concrete walls", "retaining walls", "foundation walls", "shear walls"],
    },
    {
        "name": "CIP Concrete Slabs",
        "division_code": "03 30 00",
        "division_name": "Cast-in-Place Concrete",
        "expected_unit": "CY",
        "scope_family": "concrete",
        "typical_cost_bucket": "direct_material",
        "common_dependencies": json.dumps(["Aggregate Base", "Rebar", "Testing / Inspection"]),
        "notes": "Slab-on-grade and elevated structural slabs.",
        "aliases": ["concrete slab", "slab on grade", "SOG", "floor slab", "elevated slab"],
    },
    {
        "name": "Joint Sealants",
        "division_code": "07 92 00",
        "division_name": "Joint Sealants",
        "expected_unit": "LF",
        "scope_family": "concrete",
        "typical_cost_bucket": "direct_labor",
        "common_dependencies": json.dumps(["CIP Concrete Slabs"]),
        "notes": "Control joint sealing in slabs and walls.",
        "aliases": ["joint sealing", "caulking", "control joints", "expansion joints"],
    },
]


def seed_canonical_activities(db: Session, overwrite: bool = False) -> int:
    """Insert canonical activities if they don't already exist.

    Args:
        db: SQLAlchemy session.
        overwrite: If True, update existing records with seed data.

    Returns:
        Number of records inserted or updated.
    """
    from apex.backend.models.decision_models import ActivityAlias, CanonicalActivity

    count = 0
    for entry in CANONICAL_ACTIVITIES:
        aliases_data = entry.pop("aliases", [])
        existing = db.query(CanonicalActivity).filter_by(name=entry["name"]).first()

        if existing and not overwrite:
            entry["aliases"] = aliases_data  # restore for next loop
            continue

        if existing and overwrite:
            for k, v in entry.items():
                setattr(existing, k, v)
            activity = existing
        else:
            activity = CanonicalActivity(**entry)
            db.add(activity)
            db.flush()

        # Upsert aliases
        existing_aliases = {a.alias for a in db.query(ActivityAlias).filter_by(canonical_activity_id=activity.id).all()}
        for alias_text in aliases_data:
            if alias_text not in existing_aliases:
                db.add(
                    ActivityAlias(
                        canonical_activity_id=activity.id,
                        alias=alias_text,
                        source="ontology_seed",
                        confidence=1.0,
                    )
                )

        entry["aliases"] = aliases_data  # restore for idempotency
        count += 1

    db.commit()
    return count


if __name__ == "__main__":
    import os
    import sys

    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
    import apex.backend.models  # noqa — ensure all tables are registered
    from apex.backend.db.database import SessionLocal

    db = SessionLocal()
    try:
        n = seed_canonical_activities(db)
        print(f"Seeded {n} canonical activities.")
    finally:
        db.close()
