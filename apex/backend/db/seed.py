"""Database seeder for APEX with comprehensive sample data.

Run standalone:  python -m apex.backend.db.seed
Called from app:  seed_if_empty() in lifespan
"""

from datetime import datetime, timedelta, timezone
from random import randint, uniform, choice

from apex.backend.db.database import SessionLocal, engine, Base
from apex.backend.models import (
    User,
    Organization,
    Project,
    Document,
    SpecSection,
    GapReport,
    GapReportItem,
    TakeoffItem,
    LaborEstimate,
    MaterialPrice,
    Estimate,
    EstimateLineItem,
    ProjectActual,
    ProductivityHistory,
    AgentRunLog,
)
from apex.backend.utils.auth import hash_password

now = datetime.now(timezone.utc)


# ------------------------------------------------------------------
# Public entry points
# ------------------------------------------------------------------

def seed_if_empty():
    """Called at app startup — seeds only if the DB is empty."""
    db = SessionLocal()
    try:
        if db.query(Organization).count() > 0:
            return
        print("Seeding APEX database …")
        _seed_all(db)
        db.commit()
        print("APEX database seeded successfully.")
    except Exception as e:
        db.rollback()
        print(f"Seeding failed: {e}")
        raise
    finally:
        db.close()


def main():
    """CLI entry: drop-and-recreate all tables then seed."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        _seed_all(db)
        db.commit()
        print("APEX database seeded successfully.")
    except Exception as e:
        db.rollback()
        print(f"Seeding failed: {e}")
        raise
    finally:
        db.close()


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _seed_all(db):
    org, admin, estimator = _seed_org_and_users(db)
    p1, p2, p3 = _seed_projects(db, org, estimator)
    prod_rows = _seed_productivity_library(db)
    _seed_material_prices(db)

    # Project 1 — healthcare, estimating stage (full pipeline demo)
    doc1, specs1 = _seed_documents_and_specs(db, p1)
    takeoffs1, labor1 = _seed_takeoff_and_labor(db, p1, specs1, prod_rows)
    est1, lines1 = _seed_estimate(db, p1, takeoffs1, labor1)
    _seed_gap_report(db, p1, specs1)
    _seed_agent_logs(db, p1)

    # Project 2 — industrial, bid submitted
    doc2, specs2 = _seed_documents_and_specs(db, p2)
    takeoffs2, labor2 = _seed_takeoff_and_labor(db, p2, specs2, prod_rows)
    est2, lines2 = _seed_estimate(db, p2, takeoffs2, labor2)
    _seed_gap_report(db, p2, specs2)
    _seed_agent_logs(db, p2)

    # Project 3 — commercial, completed + actuals (IMPROVE loop demo)
    doc3, specs3 = _seed_documents_and_specs(db, p3)
    takeoffs3, labor3 = _seed_takeoff_and_labor(db, p3, specs3, prod_rows)
    est3, lines3 = _seed_estimate(db, p3, takeoffs3, labor3)
    _seed_gap_report(db, p3, specs3)
    _seed_actuals(db, p3, lines3, prod_rows)
    _seed_agent_logs(db, p3, include_improve=True)


# ------------------------------------------------------------------
# Organization + Users
# ------------------------------------------------------------------

def _seed_org_and_users(db):
    org = Organization(
        name="Christman Building Innovation Group",
        address="Livonia, MI",
        phone="555-123-4567",
        license_number="MI-GC-2026",
    )
    db.add(org)
    db.flush()

    admin = User(
        email="admin@apex-demo.com",
        hashed_password=hash_password("admin123"),
        full_name="Demo Admin",
        role="admin",
        organization_id=org.id,
    )
    estimator = User(
        email="estimator@apex-demo.com",
        hashed_password=hash_password("estimate123"),
        full_name="Senior Estimator",
        role="estimator",
        organization_id=org.id,
    )
    db.add_all([admin, estimator])
    db.flush()
    return org, admin, estimator


# ------------------------------------------------------------------
# Projects (3 in various stages)
# ------------------------------------------------------------------

def _seed_projects(db, org, owner):
    p1 = Project(
        name="Midtown Medical Office Shell",
        project_number="APX-001",
        project_type="healthcare",
        status="estimating",
        description="3-story medical office shell with structured parking.",
        location="Detroit, MI",
        square_footage=85000,
        estimated_value=32000000,
        bid_date="2026-04-15",
        organization_id=org.id,
        owner_id=owner.id,
    )
    p2 = Project(
        name="Riverfront Warehouse Expansion",
        project_number="APX-002",
        project_type="industrial",
        status="bid_submitted",
        description="120k SF warehouse expansion with dock additions.",
        location="Toledo, OH",
        square_footage=120000,
        estimated_value=18000000,
        bid_date="2026-03-20",
        organization_id=org.id,
        owner_id=owner.id,
    )
    p3 = Project(
        name="Tech Campus Phase 1",
        project_number="APX-003",
        project_type="commercial",
        status="completed",
        description="4-building tech campus — completed with field actuals.",
        location="Ann Arbor, MI",
        square_footage=150000,
        estimated_value=55000000,
        bid_date="2025-06-01",
        organization_id=org.id,
        owner_id=owner.id,
    )
    db.add_all([p1, p2, p3])
    db.flush()
    return p1, p2, p3


# ------------------------------------------------------------------
# Documents + Spec Sections
# ------------------------------------------------------------------

_SPEC_SECTIONS = [
    ("03", "03 30 00", "Cast-in-Place Concrete", "Foundations, slabs, elevated decks. 4000 PSI mix. 3,200 CY structural, 600 CY SOG."),
    ("03", "03 35 00", "Concrete Finishing", "Trowel finish, broom finish, curing compound, sealing. 42,000 SF."),
    ("03", "03 20 00", "Concrete Reinforcing", "Grade 60 rebar #4-#9, WWF, dowels. 280 tons."),
    ("03", "03 10 00", "Concrete Forming", "Elevated slab formwork, edge forms, shoring. 35,000 SF."),
    ("05", "05 12 00", "Structural Steel Framing", "W-shapes, HSS columns, moment frames. 1,200 tons."),
    ("05", "05 31 00", "Steel Decking", "3-in 20GA composite deck. 95,000 SF."),
    ("05", "05 50 00", "Metal Fabrications", "Misc metals, embeds, lintels, shelf angles. 32,000 LB."),
    ("07", "07 21 00", "Thermal Insulation", "Exterior wall rigid insulation R-25. 58,000 SF."),
    ("07", "07 41 00", "Metal Roof Panels", "Standing seam roof. 24,000 SF."),
    ("07", "07 92 00", "Joint Sealants", "Silicone and polyurethane sealants. 12,000 LF."),
    ("08", "08 11 00", "Metal Doors and Frames", "HM doors and frames, 145 EA."),
    ("08", "08 41 00", "Entrances and Storefronts", "Aluminum storefront glazing. 3,600 SF."),
    ("09", "09 29 00", "Gypsum Board", "Metal stud partitions and GWB. 185,000 SF walls, 28,000 SF ceilings."),
    ("09", "09 51 00", "Acoustical Ceilings", "Suspended ACT system. 95,000 SF."),
    ("09", "09 91 00", "Painting", "2-coat latex walls and ceilings. 380,000 SF."),
    ("09", "09 30 00", "Tiling", "Ceramic floor and wall tile in restrooms. 8,500 SF."),
]

_SAMPLE_SPEC_TEXT = """PROJECT SPECIFICATIONS
SECTION 03 30 00 - CAST-IN-PLACE CONCRETE
PART 1 - GENERAL
1.1 SUBMITTALS: Mix designs, test reports
PART 2 - PRODUCTS: ASTM C150 cement, 4000 PSI
PART 3 - EXECUTION: Place 3,200 CY structural, 600 CY SOG.

SECTION 03 20 00 - CONCRETE REINFORCING
PART 2 - PRODUCTS: ASTM A615 Grade 60
PART 3 - EXECUTION: Install 280 tons rebar.

SECTION 05 12 00 - STRUCTURAL STEEL FRAMING
PART 2 - PRODUCTS: ASTM A992
PART 3 - EXECUTION: Erect 1,200 tons structural steel.

SECTION 05 31 00 - STEEL DECKING
PART 2 - PRODUCTS: 3-in 20GA composite per ASTM A653
PART 3 - EXECUTION: Install 95,000 SF composite deck.

SECTION 07 21 00 - THERMAL INSULATION
PART 2 - PRODUCTS: Polyiso rigid insulation per ASTM C578
PART 3 - EXECUTION: Install 58,000 SF R-25 continuous insulation.

SECTION 07 41 00 - METAL ROOF PANELS
PART 2 - PRODUCTS: Standing seam metal panels, 24 GA
PART 3 - EXECUTION: Install 24,000 SF standing seam roof.

SECTION 08 11 00 - METAL DOORS AND FRAMES
PART 2 - PRODUCTS: ANSI A250.8 hollow metal
PART 3 - EXECUTION: Install 145 EA doors and frames.

SECTION 09 29 00 - GYPSUM BOARD
PART 2 - PRODUCTS: 5/8-in Type X per ASTM C1396
PART 3 - EXECUTION: Install 185,000 SF walls, 28,000 SF ceilings.

SECTION 09 51 00 - ACOUSTICAL CEILINGS
PART 2 - PRODUCTS: Lay-in panels per ASTM E1264
PART 3 - EXECUTION: Install 95,000 SF suspended ceiling system.

SECTION 09 91 00 - PAINTING
PART 2 - PRODUCTS: Latex paint per SSPC standards
PART 3 - EXECUTION: Paint 380,000 SF. Bid bond required.
"""


def _seed_documents_and_specs(db, project):
    doc = Document(
        project_id=project.id,
        filename="Specifications_Divisions_03-09.pdf",
        file_path="/data/specs/project_specs.pdf",
        file_type="pdf",
        classification="spec",
        file_size_bytes=4_200_000,
        page_count=186,
        processing_status="completed",
        raw_text=_SAMPLE_SPEC_TEXT,
        metadata_json={"description": "Multi-division project specifications"},
    )
    db.add(doc)
    db.flush()

    specs = []
    for div, sec_num, title, desc in _SPEC_SECTIONS:
        s = SpecSection(
            project_id=project.id,
            document_id=doc.id,
            division_number=div,
            section_number=sec_num,
            title=title,
            work_description=desc,
            materials_referenced=["ASTM C150", "ASTM A615"] if div == "03" else ["ASTM A992"],
            execution_requirements="Per manufacturer instructions and applicable codes.",
            submittal_requirements="Shop drawings, product data, samples.",
            keywords=title.lower().split(),
        )
        specs.append(s)
    db.add_all(specs)
    db.flush()
    return doc, specs


# ------------------------------------------------------------------
# Productivity Library (50+ rates across Div 03, 05, 07, 08, 09)
# ------------------------------------------------------------------

def _seed_productivity_library(db):
    rows = []

    def _add(csi, wtype, crew, rate, unit, src="Baseline", is_act=0, conf=0.7, cnt=5):
        rows.append(ProductivityHistory(
            csi_code=csi, work_type=wtype, crew_type=crew,
            productivity_rate=rate, unit_of_measure=unit,
            source_project=src, is_actual=is_act,
            confidence_score=conf, sample_count=cnt,
        ))

    # Division 03 — Concrete
    _add("03 30 00", "Foundations",           "Concrete Crew",    4.5,  "CY")
    _add("03 30 00", "Slab on grade",         "Concrete Crew",    6.0,  "CY")
    _add("03 30 00", "Elevated decks",        "Concrete Crew",    3.8,  "CY")
    _add("03 35 00", "Slab finishing",         "Concrete Crew",  180.0,  "SF")
    _add("03 35 00", "Deck finishing",         "Concrete Crew",  140.0,  "SF")
    _add("03 20 00", "Reinforcing steel",      "Ironworker Crew", 500.0, "LB")
    _add("03 10 00", "Formwork",              "Carpenter Crew",   55.0,  "SF")
    _add("03 10 00", "Form stripping",         "Carpenter Crew",   85.0,  "SF")
    _add("03 30 00", "Concrete pumping",       "Concrete Crew",   18.0,  "CY")
    _add("03 30 00", "Patching and repair",    "Concrete Crew",   30.0,  "SF")

    # Division 05 — Metals
    _add("05 12 00", "Steel erection main",   "Ironworker Crew",  0.7,  "TON")
    _add("05 12 00", "Steel erection infill",  "Ironworker Crew",  0.9,  "TON")
    _add("05 31 00", "Metal decking install",  "Ironworker Crew", 250.0, "SF")
    _add("05 50 00", "Misc metals install",    "Ironworker Crew",  45.0, "LB")
    _add("05 50 00", "Embeds placement",       "Ironworker Crew",  35.0, "EA")
    _add("05 12 00", "Bolting and welding",    "Ironworker Crew",  22.0, "EA")
    _add("05 12 00", "Touch-up painting",      "Painting Crew",   200.0, "SF")
    _add("05 52 00", "Pipe rail install",      "Ironworker Crew",  30.0, "LF")
    _add("05 73 00", "Metal stairs erection",  "Ironworker Crew",   1.2, "EA")
    _add("05 50 00", "Ladder install",         "Ironworker Crew",   0.6, "EA")

    # Division 07 — Thermal & Moisture
    _add("07 21 00", "Ext wall insulation",    "Insulation Crew", 280.0, "SF")
    _add("07 21 00", "Roof insulation",        "Insulation Crew", 320.0, "SF")
    _add("07 41 00", "Standing seam roof",     "Roofing Crew",    120.0, "SF")
    _add("07 62 00", "Sheet metal flashing",   "Sheet Metal Crew", 40.0, "LF")
    _add("07 92 00", "Joint sealants",         "Caulking Crew",    55.0, "LF")
    _add("07 25 00", "Air barrier install",    "Insulation Crew", 220.0, "SF")
    _add("07 13 00", "Below-grade WP",         "Waterproof Crew",  85.0, "SF")
    _add("07 21 00", "Cavity insulation",      "Insulation Crew", 260.0, "SF")
    _add("07 54 00", "Roof membrane",          "Roofing Crew",    180.0, "SF")
    _add("07 42 00", "Composite wall panels",  "Siding Crew",      95.0, "SF")

    # Division 08 — Openings
    _add("08 11 00", "HM doors install",       "Carpentry Crew",    1.4, "EA")
    _add("08 11 00", "HM frames install",      "Carpentry Crew",    2.0, "EA")
    _add("08 41 00", "Storefront install",     "Glazing Crew",     35.0, "SF")
    _add("08 44 00", "Curtain wall install",   "Glazing Crew",     22.0, "SF")
    _add("08 71 00", "Hardware install",       "Carpentry Crew",    3.5, "EA")
    _add("08 51 00", "Aluminum windows",       "Glazing Crew",      0.9, "EA")
    _add("08 91 00", "Louvers and vents",      "Sheet Metal Crew", 40.0, "SF")
    _add("08 36 00", "Overhead doors",         "Carpentry Crew",    0.9, "EA")
    _add("08 33 00", "Coiling doors",          "Carpentry Crew",    0.8, "EA")
    _add("08 80 00", "Glazing",                "Glazing Crew",     30.0, "SF")

    # Division 09 — Finishes
    _add("09 29 00", "Interior partitions",    "Drywall Crew",    220.0, "SF")
    _add("09 29 00", "Shaft walls",            "Drywall Crew",    165.0, "SF")
    _add("09 51 00", "Acoustic ceilings",      "Ceiling Crew",    300.0, "SF")
    _add("09 65 00", "Resilient flooring",     "Flooring Crew",   280.0, "SF")
    _add("09 68 00", "Carpet tile",            "Flooring Crew",   260.0, "SF")
    _add("09 91 00", "Paint walls",            "Painting Crew",   350.0, "SF")
    _add("09 91 00", "Paint ceilings",         "Painting Crew",   320.0, "SF")
    _add("09 30 00", "Ceramic tile",           "Tile Crew",        95.0, "SF")
    _add("09 64 00", "Wood paneling",          "Carpentry Crew",   75.0, "SF")
    _add("09 84 00", "Acoustic wall panels",   "Carpentry Crew",   60.0, "SF")
    _add("09 29 00", "Metal stud framing",     "Drywall Crew",     30.0, "LF")
    _add("09 29 00", "Drywall hang/finish",    "Drywall Crew",    250.0, "SF")

    # Actuals from completed project
    _add("03 30 00", "Structural Concrete", "Concrete Crew", 1.35, "CY", "APX-003", 1, 0.85, 1)
    _add("05 12 00", "Steel erection main",  "Ironworker Crew", 0.65, "TON", "APX-003", 1, 0.85, 1)
    _add("09 29 00", "Interior partitions",  "Drywall Crew", 235.0, "SF", "APX-003", 1, 0.85, 1)
    _add("09 91 00", "Paint walls",          "Painting Crew", 370.0, "SF", "APX-003", 1, 0.85, 1)

    db.add_all(rows)
    db.flush()
    return rows


# ------------------------------------------------------------------
# Material Prices
# ------------------------------------------------------------------

def _seed_material_prices(db):
    data = [
        ("03 30 00", "Ready-mix concrete 4000 PSI",  165.00, "CY", "vendor_quote"),
        ("03 20 00", "Rebar Grade 60",                 0.85, "LB", "vendor_quote"),
        ("03 10 00", "Formwork lumber and hardware",    3.50, "SF", "rs_means"),
        ("05 12 00", "Structural steel W-shapes",    2800.00, "TON", "vendor_quote"),
        ("05 31 00", "Composite steel deck 20GA",       3.25, "SF", "vendor_quote"),
        ("05 50 00", "Misc steel fabrications",         1.50, "LB", "rs_means"),
        ("07 21 00", "Rigid insulation 2-in polyiso",   1.85, "SF", "vendor_quote"),
        ("07 41 00", "Standing seam metal panels",      9.25, "SF", "vendor_quote"),
        ("07 92 00", "Silicone sealant",                2.25, "LF", "vendor_quote"),
        ("08 11 00", "HM door and frame assembly",    650.00, "EA", "vendor_quote"),
        ("08 41 00", "Storefront glazing system",      85.00, "SF", "vendor_quote"),
        ("09 29 00", "5/8-in gypsum board",             0.65, "SF", "vendor_quote"),
        ("09 29 00", "Metal stud framing material",     8.00, "LF", "vendor_quote"),
        ("09 51 00", "ACT tile and grid",               4.25, "SF", "vendor_quote"),
        ("09 30 00", "Ceramic tile",                    6.50, "SF", "vendor_quote"),
        ("09 91 00", "Paint (2-coat system)",           0.45, "SF", "rs_means"),
    ]
    for csi, desc, cost, unit, src in data:
        db.add(MaterialPrice(
            csi_code=csi, description=desc,
            unit_cost=cost, unit_of_measure=unit,
            source=src, region="Detroit Metro",
        ))
    db.flush()


# ------------------------------------------------------------------
# Takeoff + Labor for a project
# ------------------------------------------------------------------

_TAKEOFF_TEMPLATE = [
    # (spec_idx, csi, description, qty, unit)
    (0, "03 30 00", "Structural concrete placement",   3200, "CY"),
    (0, "03 30 00", "SOG concrete placement",           600, "CY"),
    (1, "03 35 00", "Concrete slab finishing",        42000, "SF"),
    (2, "03 20 00", "Rebar placement",               560000, "LB"),
    (3, "03 10 00", "Elevated slab formwork",         35000, "SF"),
    (4, "05 12 00", "Structural steel erection",       1200, "TON"),
    (5, "05 31 00", "Composite deck install",         95000, "SF"),
    (6, "05 50 00", "Misc metals install",            32000, "LB"),
    (7, "07 21 00", "Rigid insulation install",       58000, "SF"),
    (8, "07 41 00", "Standing seam roof install",     24000, "SF"),
    (9, "07 92 00", "Joint sealant application",      12000, "LF"),
    (10, "08 11 00", "HM door and frame install",       145, "EA"),
    (11, "08 41 00", "Storefront glazing install",     3600, "SF"),
    (12, "09 29 00", "GWB partition install",        185000, "SF"),
    (12, "09 29 00", "GWB ceiling install",           28000, "SF"),
    (13, "09 51 00", "ACT ceiling install",           95000, "SF"),
    (14, "09 91 00", "Interior painting",            380000, "SF"),
    (15, "09 30 00", "Ceramic tile install",           8500, "SF"),
]

# Crew configs for labor calculation
_CREWS = {
    "Concrete Crew":    (6, 78.50),
    "Ironworker Crew":  (4, 92.00),
    "Carpenter Crew":   (4, 72.00),
    "Carpentry Crew":   (4, 72.00),
    "Insulation Crew":  (3, 65.00),
    "Roofing Crew":     (5, 70.00),
    "Sheet Metal Crew": (3, 82.00),
    "Caulking Crew":    (2, 62.00),
    "Drywall Crew":     (4, 68.00),
    "Tile Crew":        (3, 75.00),
    "Ceiling Crew":     (3, 68.00),
    "Painting Crew":    (4, 58.00),
    "Glazing Crew":     (3, 80.00),
    "General Crew":     (4, 65.00),
}

# Map CSI prefix to crew + approximate rate
_CSI_LABOR = {
    "03 30 00": ("Concrete Crew",   "Structural Concrete",    3.8),
    "03 35 00": ("Concrete Crew",   "Concrete Finishing",   160.0),
    "03 20 00": ("Ironworker Crew", "Rebar Placement",      500.0),
    "03 10 00": ("Carpenter Crew",  "Formwork",              55.0),
    "05 12 00": ("Ironworker Crew", "Steel Erection",         0.7),
    "05 31 00": ("Ironworker Crew", "Deck Install",         250.0),
    "05 50 00": ("Ironworker Crew", "Misc Metals",           45.0),
    "07 21 00": ("Insulation Crew", "Rigid Insulation",     280.0),
    "07 41 00": ("Roofing Crew",    "Standing Seam Roof",   120.0),
    "07 92 00": ("Caulking Crew",   "Joint Sealants",        55.0),
    "08 11 00": ("Carpentry Crew",  "Door Install",           1.4),
    "08 41 00": ("Glazing Crew",    "Storefront Install",    35.0),
    "09 29 00": ("Drywall Crew",    "Gypsum Board",         220.0),
    "09 51 00": ("Ceiling Crew",    "ACT Ceilings",         300.0),
    "09 91 00": ("Painting Crew",   "Painting",             350.0),
    "09 30 00": ("Tile Crew",       "Ceramic Tile",          95.0),
}


def _seed_takeoff_and_labor(db, project, specs, prod_rows):
    takeoffs = []
    labor_items = []

    for spec_idx, csi, desc, qty, unit in _TAKEOFF_TEMPLATE:
        sid = specs[min(spec_idx, len(specs) - 1)].id
        t = TakeoffItem(
            project_id=project.id,
            spec_section_id=sid,
            csi_code=csi,
            description=desc,
            quantity=qty,
            unit_of_measure=unit,
            drawing_reference=f"S{randint(1,5)}.{randint(1,15):02d}",
            confidence=round(uniform(0.75, 0.95), 2),
        )
        takeoffs.append(t)
    db.add_all(takeoffs)
    db.flush()

    for t in takeoffs:
        crew_name, work_type, rate = _CSI_LABOR.get(
            t.csi_code, ("General Crew", "General", 10.0)
        )
        crew_size, hourly = _CREWS.get(crew_name, (4, 65.00))
        crew_hours = t.quantity / max(rate, 0.01)
        man_hours = crew_hours * crew_size
        cost = man_hours * hourly

        le = LaborEstimate(
            project_id=project.id,
            takeoff_item_id=t.id,
            csi_code=t.csi_code,
            work_type=work_type,
            crew_type=crew_name,
            productivity_rate=rate,
            productivity_unit=t.unit_of_measure,
            quantity=t.quantity,
            labor_hours=round(crew_hours, 2),
            crew_size=crew_size,
            crew_days=round(crew_hours / 8, 2),
            hourly_rate=hourly,
            total_labor_cost=round(cost, 2),
        )
        labor_items.append(le)
    db.add_all(labor_items)
    db.flush()
    return takeoffs, labor_items


# ------------------------------------------------------------------
# Estimate assembly
# ------------------------------------------------------------------

_MAT_UNIT_COST = {
    "03 30 00": 165.00,
    "03 35 00": 0.35,
    "03 20 00": 0.85,
    "03 10 00": 3.50,
    "05 12 00": 2800.00,
    "05 31 00": 3.25,
    "05 50 00": 1.50,
    "07 21 00": 1.85,
    "07 41 00": 9.25,
    "07 92 00": 2.25,
    "08 11 00": 650.00,
    "08 41 00": 85.00,
    "09 29 00": 0.65,
    "09 51 00": 4.25,
    "09 91 00": 0.45,
    "09 30 00": 6.50,
}


def _seed_estimate(db, project, takeoffs, labor_items):
    total_labor = sum(le.total_labor_cost for le in labor_items)
    total_material = 0.0

    # Build line items
    lines_data = []
    for le, t in zip(labor_items, takeoffs):
        mat_unit = _MAT_UNIT_COST.get(t.csi_code, 1.00)
        mat_cost = mat_unit * t.quantity
        equip_cost = le.total_labor_cost * 0.07
        line_total = le.total_labor_cost + mat_cost + equip_cost
        total_material += mat_cost

        lines_data.append({
            "division_number": t.csi_code[:2],
            "csi_code": t.csi_code,
            "description": f"{le.work_type} - {t.description}",
            "quantity": t.quantity,
            "unit_of_measure": t.unit_of_measure,
            "labor_cost": le.total_labor_cost,
            "material_cost": round(mat_cost, 2),
            "equipment_cost": round(equip_cost, 2),
            "subcontractor_cost": 0.0,
            "total_cost": round(line_total, 2),
            "unit_cost": round(line_total / t.quantity, 2) if t.quantity else 0,
        })

    direct = total_labor + total_material
    overhead = direct * 0.10
    profit = (direct + overhead) * 0.08
    contingency = (direct + overhead + profit) * 0.05
    total_bid = direct + overhead + profit + contingency

    est = Estimate(
        project_id=project.id,
        version=1,
        status="draft",
        total_direct_cost=round(direct, 2),
        total_labor_cost=round(total_labor, 2),
        total_material_cost=round(total_material, 2),
        total_subcontractor_cost=0,
        overhead_pct=10.0, overhead_amount=round(overhead, 2),
        profit_pct=8.0, profit_amount=round(profit, 2),
        contingency_pct=5.0, contingency_amount=round(contingency, 2),
        gc_markup_pct=0.0, gc_markup_amount=0.0,
        total_bid_amount=round(total_bid, 2),
        exclusions=[
            "Hazardous material abatement",
            "Overtime premiums",
            "FF&E",
            "Fire suppression (Div 21)",
            "Plumbing (Div 22)",
            "HVAC (Div 23)",
            "Electrical (Div 26)",
        ],
        assumptions=[
            "Normal working hours 7AM-3:30PM M-F",
            "Site access provided by Owner",
            "Material pricing valid 30 days",
            "Quantities from plan takeoff",
        ],
        alternates=[
            {"name": "ALT-1: Upgraded Lobby Finishes", "amount": 185000},
            {"name": "ALT-2: Enhanced Roofing System", "amount": 320000},
        ],
        bid_bond_required=1,
        summary_json={"divisions_covered": sorted(set(d["division_number"] for d in lines_data))},
    )
    db.add(est)
    db.flush()

    line_items = []
    for ld in lines_data:
        li = EstimateLineItem(estimate_id=est.id, **ld)
        line_items.append(li)
    db.add_all(line_items)
    db.flush()
    return est, line_items


# ------------------------------------------------------------------
# Gap Report
# ------------------------------------------------------------------

def _seed_gap_report(db, project, specs):
    gap_items_data = [
        ("07", "07 10 00", "Dampproofing and Waterproofing", "missing", "critical",
         "Below-grade waterproofing not found in specs.", 10.0),
        ("07", "07 27 00", "Air Barriers", "missing", "critical",
         "Air barrier section missing — required by energy code.", 9.5),
        ("07", "07 84 00", "Firestopping", "missing", "critical",
         "Firestopping not specified for rated assemblies.", 10.0),
        ("08", "08 71 00", "Door Hardware", "missing", "moderate",
         "Hardware schedule may be in door section.", 5.0),
        ("05", "05 52 00", "Metal Railings", "missing", "moderate",
         "Railings may be covered under misc metals.", 4.0),
        ("09", "09 65 00", "Resilient Flooring", "missing", "watch",
         "Verify if carpet-only or resilient flooring needed.", 1.5),
        ("03", "03 40 00", "Precast Concrete", "missing", "watch",
         "Precast not specified — confirm CIP only.", 1.0),
        ("08", "08 50 00", "Windows", "missing", "watch",
         "Window spec missing — may be in storefront section.", 2.0),
    ]

    critical = sum(1 for *_, s, _, _ in gap_items_data if s == "critical")
    moderate = sum(1 for *_, s, _, _ in gap_items_data if s == "moderate")
    watch = sum(1 for *_, s, _, _ in gap_items_data if s == "watch")

    report = GapReport(
        project_id=project.id,
        overall_score=42.5,
        total_gaps=len(gap_items_data),
        critical_count=critical,
        moderate_count=moderate,
        watch_count=watch,
        summary=f"Found {len(gap_items_data)} gaps: {critical} critical, {moderate} moderate, {watch} watch.",
    )
    db.add(report)
    db.flush()

    for div, sec, title, gtype, sev, desc, risk in gap_items_data:
        db.add(GapReportItem(
            gap_report_id=report.id,
            division_number=div,
            section_number=sec,
            title=title,
            gap_type=gtype,
            severity=sev,
            description=desc,
            recommendation=f"Request clarification on {title} scope.",
            risk_score=risk,
        ))
    db.flush()
    return report


# ------------------------------------------------------------------
# Project Actuals (for completed project → IMPROVE loop)
# ------------------------------------------------------------------

def _seed_actuals(db, project, estimate_lines, prod_rows):
    for li in estimate_lines[:min(15, len(estimate_lines))]:
        variance_factor = uniform(0.82, 1.22)
        est_hours = li.labor_cost / 70.0  # approx
        act_hours = est_hours * variance_factor
        act_cost = li.total_cost * variance_factor
        var_cost = act_cost - li.total_cost
        var_pct = (var_cost / li.total_cost * 100) if li.total_cost else 0

        db.add(ProjectActual(
            project_id=project.id,
            csi_code=li.csi_code,
            description=li.description,
            estimated_quantity=li.quantity,
            actual_quantity=li.quantity * uniform(0.95, 1.05),
            estimated_labor_hours=round(est_hours, 2),
            actual_labor_hours=round(act_hours, 2),
            estimated_cost=round(li.total_cost, 2),
            actual_cost=round(act_cost, 2),
            variance_hours=round(act_hours - est_hours, 2),
            variance_cost=round(var_cost, 2),
            variance_pct=round(var_pct, 2),
            crew_type=li.csi_code[:2],
            work_type=li.description[:80],
        ))
    db.flush()


# ------------------------------------------------------------------
# Agent Run Logs
# ------------------------------------------------------------------

def _seed_agent_logs(db, project, include_improve=False):
    agents = [
        (1, "Document Ingestion Agent"),
        (2, "Spec Parser Agent"),
        (3, "Scope Gap Analysis Agent"),
        (4, "Quantity Takeoff Agent"),
        (5, "Labor Productivity Agent"),
        (6, "Estimate Assembly Agent"),
    ]
    if include_improve:
        agents.append((7, "IMPROVE Feedback Agent"))

    for num, name in agents:
        start = now - timedelta(minutes=60 - num * 5)
        dur = uniform(8.0, 45.0)
        db.add(AgentRunLog(
            project_id=project.id,
            agent_number=num,
            agent_name=name,
            status="completed",
            started_at=start,
            completed_at=start + timedelta(seconds=dur),
            duration_seconds=round(dur, 2),
            tokens_used=randint(800, 4500),
            output_summary=f"{name} completed successfully.",
        ))
    db.flush()


# ------------------------------------------------------------------
if __name__ == "__main__":
    main()
