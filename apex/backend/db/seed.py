"""Database seeder — populates sample data for development and demo."""

import logging
from datetime import datetime, timezone, timedelta
from apex.backend.db.database import SessionLocal
from apex.backend.models.user import User
from apex.backend.models.organization import Organization
from apex.backend.models.project import Project
from apex.backend.models.document import Document
from apex.backend.models.spec_section import SpecSection
from apex.backend.models.gap_report import GapReport, GapReportItem
from apex.backend.models.takeoff_item import TakeoffItem
from apex.backend.models.labor_estimate import LaborEstimate
from apex.backend.models.material_price import MaterialPrice
from apex.backend.models.estimate import Estimate, EstimateLineItem
from apex.backend.models.project_actual import ProjectActual
from apex.backend.models.productivity_history import ProductivityHistory
from apex.backend.models.agent_run_log import AgentRunLog
from apex.backend.utils.auth import hash_password

logger = logging.getLogger("apex.seed")

now = datetime.now(timezone.utc)


def seed_if_empty():
    db = SessionLocal()
    try:
        if db.query(Organization).count() > 0:
            logger.info("Database already seeded, skipping.")
            return
        logger.info("Seeding database with sample data...")
        _seed(db)
        logger.info("Database seeding complete.")
    finally:
        db.close()


def _seed(db):
    # --- Organization ---
    org = Organization(name="Summit Builders Inc.", address="1200 Industrial Pkwy, Denver, CO 80202", phone="303-555-0100", license_number="GC-2024-8847")
    db.add(org)
    db.commit()
    db.refresh(org)

    # --- Users ---
    admin = User(email="admin@summitbuilders.com", hashed_password=hash_password("admin123"), full_name="Mike Reynolds", role="admin", organization_id=org.id)
    estimator = User(email="estimator@summitbuilders.com", hashed_password=hash_password("estimate123"), full_name="Sarah Chen", role="estimator", organization_id=org.id)
    db.add_all([admin, estimator])
    db.commit()

    # --- Projects ---
    p1 = Project(
        name="Meridian Office Tower", project_number="SOT-2025-001",
        project_type="commercial", status="estimating",
        description="12-story Class A office building with ground-floor retail, 285,000 SF",
        location="Denver, CO", square_footage=285000, estimated_value=42000000,
        bid_date="2025-04-15", owner_id=estimator.id, organization_id=org.id,
    )
    p2 = Project(
        name="Westfield Medical Center Expansion", project_number="WMC-2025-002",
        project_type="healthcare", status="draft",
        description="45,000 SF addition to existing medical center including surgery suites and imaging wing",
        location="Aurora, CO", square_footage=45000, estimated_value=18500000,
        bid_date="2025-05-20", owner_id=estimator.id, organization_id=org.id,
    )
    p3 = Project(
        name="Rocky Mountain Fulfillment Center", project_number="RMFC-2024-003",
        project_type="industrial", status="completed",
        description="180,000 SF tilt-up warehouse with 30,000 SF office build-out — COMPLETED with actuals",
        location="Commerce City, CO", square_footage=210000, estimated_value=15200000,
        bid_date="2024-06-01", owner_id=estimator.id, organization_id=org.id,
    )
    db.add_all([p1, p2, p3])
    db.commit()
    db.refresh(p1)
    db.refresh(p2)
    db.refresh(p3)

    # --- Documents for Project 1 ---
    docs = [
        Document(project_id=p1.id, filename="Meridian_Specs_Divisions_03-09.pdf", file_path="/data/specs/meridian_03-09.pdf", file_type="pdf", classification="spec", file_size_bytes=4200000, page_count=186, processing_status="completed", raw_text=_sample_spec_text()),
        Document(project_id=p1.id, filename="Meridian_Structural_Drawings.pdf", file_path="/data/drawings/meridian_structural.pdf", file_type="pdf", classification="drawing", file_size_bytes=12800000, page_count=42, processing_status="completed"),
        Document(project_id=p1.id, filename="Addendum_01.pdf", file_path="/data/addenda/meridian_add01.pdf", file_type="pdf", classification="addendum", file_size_bytes=850000, page_count=8, processing_status="completed"),
    ]
    db.add_all(docs)
    db.commit()
    for d in docs:
        db.refresh(d)

    # --- Spec Sections for Project 1 ---
    spec_sections_data = [
        ("03", "03 10 00", "Concrete Forming and Accessories", "Furnish and install all formwork for cast-in-place concrete. Includes shores, reshores, and form ties. 45,000 SF of elevated slab forming, 12,000 LF of edge forms.", ["ASTM A615", "ACI 318"], "Product Data, Shop Drawings for shoring layout"),
        ("03", "03 20 00", "Concrete Reinforcing", "Furnish and install all reinforcing steel. #4 through #11 bars, WWF 6x6-W2.9xW2.9. Approximately 380 tons.", ["ASTM A615 Grade 60", "ASTM A185"], "Mill certificates, placing drawings"),
        ("03", "03 30 00", "Cast-in-Place Concrete", "Place and finish all structural and architectural concrete. 4,200 CY structural, 850 CY slab-on-grade, 3,500 psi to 6,000 psi mix designs.", ["ASTM C150", "ACI 301", "ACI 318"], "Mix designs, test reports"),
        ("05", "05 12 00", "Structural Steel Framing", "Furnish and erect structural steel framing. W-shapes, HSS columns, moment frames. Approximately 1,850 tons.", ["ASTM A992", "AISC 360", "AWS D1.1"], "Shop drawings, mill certs"),
        ("05", "05 31 00", "Steel Decking", "Furnish and install composite steel floor deck. 3\" 20GA composite deck, 165,000 SF.", ["ASTM A653", "SDI"], "Shop drawings, load tables"),
        ("05", "05 50 00", "Metal Fabrications", "Miscellaneous metals: embed plates, lintels, shelf angles, bollards. 45,000 LB.", ["ASTM A36"], "Shop drawings"),
        ("07", "07 21 00", "Thermal Insulation", "Rigid insulation at building envelope. R-25 continuous insulation, 82,000 SF.", ["ASTM C578"], "Product data, thermal calculations"),
        ("07", "07 50 00", "Membrane Roofing", "60-mil TPO fully adhered roof system. 28,500 SF including cant strips and termination bars.", ["ASTM D6878"], "Manufacturer warranty, installer qualification"),
        ("07", "07 60 00", "Flashing and Sheet Metal", "Sheet metal copings, counterflashing, through-wall flashing. 4,200 LF.", ["ASTM B209"], "Shop drawings, product data"),
        ("07", "07 92 00", "Joint Sealants", "Exterior and interior joint sealants. Silicone at curtain wall, polyurethane at concrete joints. 18,500 LF.", ["ASTM C920"], "Product data, compatibility test results"),
        ("08", "08 11 00", "Metal Doors and Frames", "Hollow metal doors and frames. 186 EA standard, 24 EA fire-rated.", ["ANSI A250.8"], "Product data, hardware schedule"),
        ("08", "08 50 00", "Windows", "Aluminum-framed windows. Fixed and operable. 340 EA total.", ["AAMA/WDMA"], "Product data, structural calculations"),
        ("09", "09 29 00", "Gypsum Board", "Metal stud framing and gypsum board assemblies. 285,000 SF walls, 42,000 SF ceilings.", ["ASTM C1396", "ASTM C645"], "Product data, fire-test reports"),
        ("09", "09 30 00", "Tiling", "Ceramic and porcelain tile. Lobbies, restrooms, break rooms. 14,500 SF floor, 3,200 SF wall.", ["ANSI A137.1"], "Product data, shop drawings"),
        ("09", "09 51 00", "Acoustical Ceilings", "Suspended acoustical ceiling system. 2x4 lay-in panels. 165,000 SF.", ["ASTM E1264"], "Product data, reflected ceiling plans"),
        ("09", "09 91 00", "Painting", "Interior and exterior painting. All exposed surfaces. 520,000 SF.", ["SSPC standards"], "Product data, color schedule"),
    ]

    sections = []
    for div, sec_num, title, desc, mats, submittals in spec_sections_data:
        s = SpecSection(
            project_id=p1.id, document_id=docs[0].id,
            division_number=div, section_number=sec_num, title=title,
            work_description=desc, materials_referenced=mats,
            execution_requirements=f"Install per manufacturer requirements and {mats[0] if mats else 'industry'} standards.",
            submittal_requirements=submittals,
            keywords=title.lower().split(),
        )
        db.add(s)
        sections.append(s)
    db.commit()
    for s in sections:
        db.refresh(s)

    # --- Gap Report for Project 1 ---
    gap_report = GapReport(
        project_id=p1.id, overall_score=42.5, total_gaps=8,
        critical_count=3, moderate_count=2, watch_count=3,
        summary="Analysis of 16 spec sections against 6 divisions. Found 8 gaps: 3 critical, 2 moderate, 3 watch.",
    )
    db.add(gap_report)
    db.commit()
    db.refresh(gap_report)

    gap_items_data = [
        ("07", "07 10 00", "Dampproofing and Waterproofing", "missing", "critical", "Below-grade waterproofing section not found. Required for basement levels.", 10.0),
        ("07", "07 27 00", "Air Barriers", "missing", "critical", "Air barrier section missing. Required by energy code for commercial buildings.", 9.5),
        ("07", "07 84 00", "Firestopping", "missing", "critical", "Firestopping section not found. Required for fire-rated assemblies.", 10.0),
        ("08", "08 41 00", "Entrances and Storefronts", "missing", "moderate", "Ground-floor retail entrances/storefronts not specified.", 6.0),
        ("08", "08 71 00", "Door Hardware", "missing", "moderate", "Door hardware section missing — may be included in door section.", 5.0),
        ("05", "05 52 00", "Metal Railings", "missing", "watch", "Metal railings section not found — may be in misc metals.", 2.0),
        ("09", "09 65 00", "Resilient Flooring", "missing", "watch", "Resilient flooring not specified — verify if carpet only.", 1.5),
        ("03", "03 35 00", "Concrete Finishing", "missing", "watch", "Concrete finishing may be included in 03 30 00.", 1.0),
    ]
    for div, sec, title, gtype, sev, desc, risk in gap_items_data:
        db.add(GapReportItem(
            gap_report_id=gap_report.id, division_number=div, section_number=sec,
            title=title, gap_type=gtype, severity=sev, description=desc,
            recommendation=f"Request clarification on {title} scope.", risk_score=risk,
        ))
    db.commit()

    # --- Takeoff Items for Project 1 ---
    takeoff_data = [
        (sections[0].id, "03 10 00", "Elevated slab formwork", 45000, "SF", "S-101, S-102", 0.9),
        (sections[0].id, "03 10 00", "Edge forms", 12000, "LF", "S-101", 0.85),
        (sections[1].id, "03 20 00", "Reinforcing steel #4-#11", 760000, "LB", "S-201", 0.88),
        (sections[2].id, "03 30 00", "Structural concrete", 4200, "CY", "S-101, S-102", 0.92),
        (sections[2].id, "03 30 00", "Slab-on-grade concrete", 850, "CY", "S-001", 0.90),
        (sections[3].id, "05 12 00", "Structural steel framing", 1850, "TON", "S-301 thru S-312", 0.95),
        (sections[4].id, "05 31 00", "Composite steel deck", 165000, "SF", "S-401", 0.93),
        (sections[5].id, "05 50 00", "Miscellaneous metals", 45000, "LB", "S-501", 0.80),
        (sections[6].id, "07 21 00", "Rigid insulation", 82000, "SF", "A-201", 0.87),
        (sections[7].id, "07 50 00", "TPO roof membrane", 28500, "SF", "A-501", 0.91),
        (sections[8].id, "07 60 00", "Sheet metal flashing", 4200, "LF", "A-502", 0.85),
        (sections[9].id, "07 92 00", "Joint sealants", 18500, "LF", "A-201, A-301", 0.82),
        (sections[10].id, "08 11 00", "Hollow metal doors and frames", 210, "EA", "A-801", 0.94),
        (sections[11].id, "08 50 00", "Aluminum windows", 340, "EA", "A-802", 0.93),
        (sections[12].id, "09 29 00", "Gypsum board walls", 285000, "SF", "A-901", 0.89),
        (sections[12].id, "09 29 00", "Gypsum board ceilings", 42000, "SF", "A-902", 0.87),
        (sections[13].id, "09 30 00", "Floor tile", 14500, "SF", "A-903", 0.88),
        (sections[13].id, "09 30 00", "Wall tile", 3200, "SF", "A-903", 0.85),
        (sections[14].id, "09 51 00", "Acoustical ceilings", 165000, "SF", "A-904", 0.91),
        (sections[15].id, "09 91 00", "Painting", 520000, "SF", "A-905", 0.86),
    ]

    takeoff_items = []
    for sec_id, csi, desc, qty, unit, dwg, conf in takeoff_data:
        t = TakeoffItem(
            project_id=p1.id, spec_section_id=sec_id, csi_code=csi,
            description=desc, quantity=qty, unit_of_measure=unit,
            drawing_reference=dwg, confidence=conf,
        )
        db.add(t)
        takeoff_items.append(t)
    db.commit()
    for t in takeoff_items:
        db.refresh(t)

    # --- Productivity History (50+ rates) ---
    prod_data = [
        ("03 10 00", "Concrete Forming", "Carpenter Crew", 50, "SF", "Baseline", 0, 0.7, 5),
        ("03 10 00", "Edge Forming", "Carpenter Crew", 80, "LF", "Baseline", 0, 0.65, 3),
        ("03 20 00", "Rebar Placement", "Ironworker Crew", 500, "LB", "Baseline", 0, 0.7, 6),
        ("03 30 00", "Structural Concrete", "Concrete Crew", 1.5, "CY", "Baseline", 0, 0.75, 8),
        ("03 30 00", "SOG Concrete", "Concrete Crew", 3.0, "CY", "Baseline", 0, 0.7, 5),
        ("03 35 00", "Concrete Finishing", "Concrete Crew", 200, "SF", "Baseline", 0, 0.6, 4),
        ("03 40 00", "Precast Erection", "Crane Crew", 8, "EA", "Baseline", 0, 0.55, 2),
        ("05 12 00", "Structural Steel Erection", "Ironworker Crew", 0.15, "TON", "Baseline", 0, 0.8, 10),
        ("05 21 00", "Steel Joist Install", "Ironworker Crew", 12, "EA", "Baseline", 0, 0.6, 3),
        ("05 31 00", "Steel Deck Install", "Ironworker Crew", 300, "SF", "Baseline", 0, 0.75, 7),
        ("05 40 00", "Cold-Formed Framing", "Carpenter Crew", 120, "LF", "Baseline", 0, 0.55, 2),
        ("05 50 00", "Misc Metal Fabrication", "Ironworker Crew", 100, "LB", "Baseline", 0, 0.65, 4),
        ("05 52 00", "Metal Railing Install", "Ironworker Crew", 15, "LF", "Baseline", 0, 0.6, 3),
        ("07 10 00", "Waterproofing", "Waterproofing Crew", 100, "SF", "Baseline", 0, 0.6, 3),
        ("07 21 00", "Batt Insulation", "Insulation Crew", 120, "SF", "Baseline", 0, 0.7, 5),
        ("07 21 00", "Rigid Insulation", "Insulation Crew", 80, "SF", "Baseline", 0, 0.7, 5),
        ("07 26 00", "Vapor Retarder", "Insulation Crew", 200, "SF", "Baseline", 0, 0.6, 3),
        ("07 27 00", "Air Barrier", "Insulation Crew", 90, "SF", "Baseline", 0, 0.55, 2),
        ("07 41 00", "Metal Roof Panels", "Roofing Crew", 40, "SF", "Baseline", 0, 0.6, 3),
        ("07 46 00", "Metal Siding", "Siding Crew", 35, "SF", "Baseline", 0, 0.55, 2),
        ("07 50 00", "TPO Roofing", "Roofing Crew", 25, "SQ", "Baseline", 0, 0.7, 6),
        ("07 60 00", "Flashing & Sheet Metal", "Sheet Metal Crew", 20, "LF", "Baseline", 0, 0.65, 5),
        ("07 70 00", "Roof Accessories", "Roofing Crew", 4, "EA", "Baseline", 0, 0.5, 2),
        ("07 84 00", "Firestopping", "Firestop Crew", 30, "EA", "Baseline", 0, 0.6, 4),
        ("07 92 00", "Joint Sealants", "Caulking Crew", 80, "LF", "Baseline", 0, 0.7, 5),
        ("08 11 00", "HM Doors & Frames", "Carpentry Crew", 4, "EA", "Baseline", 0, 0.75, 6),
        ("08 14 00", "Wood Doors", "Carpentry Crew", 6, "EA", "Baseline", 0, 0.7, 5),
        ("08 31 00", "Access Doors", "Carpentry Crew", 8, "EA", "Baseline", 0, 0.6, 3),
        ("08 41 00", "Storefront", "Glazing Crew", 15, "LF", "Baseline", 0, 0.6, 3),
        ("08 44 00", "Curtain Wall", "Glazing Crew", 8, "SF", "Baseline", 0, 0.7, 4),
        ("08 50 00", "Windows", "Glazing Crew", 3, "EA", "Baseline", 0, 0.7, 5),
        ("08 71 00", "Door Hardware", "Carpentry Crew", 8, "EA", "Baseline", 0, 0.65, 4),
        ("08 80 00", "Glazing", "Glazing Crew", 30, "SF", "Baseline", 0, 0.65, 4),
        ("09 21 00", "Metal Stud Framing", "Drywall Crew", 100, "LF", "Baseline", 0, 0.7, 6),
        ("09 22 00", "GWB Framing Supports", "Drywall Crew", 150, "SF", "Baseline", 0, 0.6, 3),
        ("09 29 00", "Gypsum Board", "Drywall Crew", 150, "SF", "Baseline", 0, 0.75, 8),
        ("09 30 00", "Ceramic Tile", "Tile Crew", 15, "SF", "Baseline", 0, 0.7, 5),
        ("09 51 00", "Acoustical Ceilings", "Ceiling Crew", 100, "SF", "Baseline", 0, 0.75, 7),
        ("09 65 00", "Resilient Flooring", "Flooring Crew", 80, "SF", "Baseline", 0, 0.6, 3),
        ("09 68 00", "Carpet", "Flooring Crew", 120, "SF", "Baseline", 0, 0.65, 4),
        ("09 72 00", "Wall Covering", "Painting Crew", 60, "SF", "Baseline", 0, 0.55, 2),
        ("09 91 00", "Interior Painting", "Painting Crew", 250, "SF", "Baseline", 0, 0.8, 10),
        ("09 91 00", "Exterior Painting", "Painting Crew", 200, "SF", "Baseline", 0, 0.7, 5),
        ("09 96 00", "High-Performance Coating", "Painting Crew", 100, "SF", "Baseline", 0, 0.6, 3),
        # Additional from completed project (actuals)
        ("03 30 00", "Structural Concrete", "Concrete Crew", 1.35, "CY", "RMFC-2024-003", 1, 0.85, 1),
        ("05 12 00", "Structural Steel Erection", "Ironworker Crew", 0.14, "TON", "RMFC-2024-003", 1, 0.85, 1),
        ("05 31 00", "Steel Deck Install", "Ironworker Crew", 320, "SF", "RMFC-2024-003", 1, 0.85, 1),
        ("09 29 00", "Gypsum Board", "Drywall Crew", 160, "SF", "RMFC-2024-003", 1, 0.85, 1),
        ("09 91 00", "Interior Painting", "Painting Crew", 270, "SF", "RMFC-2024-003", 1, 0.85, 1),
        ("07 50 00", "TPO Roofing", "Roofing Crew", 22, "SQ", "RMFC-2024-003", 1, 0.85, 1),
        ("07 21 00", "Rigid Insulation", "Insulation Crew", 85, "SF", "RMFC-2024-003", 1, 0.85, 1),
    ]
    for csi, wtype, crew, rate, unit, src, is_act, conf, cnt in prod_data:
        db.add(ProductivityHistory(
            csi_code=csi, work_type=wtype, crew_type=crew,
            productivity_rate=rate, unit_of_measure=unit,
            source_project=src, is_actual=is_act,
            confidence_score=conf, sample_count=cnt,
        ))
    db.commit()

    # --- Material Prices ---
    material_data = [
        ("03 10 00", "Formwork materials (plywood, lumber, hardware)", 3.50, "SF", "rs_means"),
        ("03 20 00", "Reinforcing steel Grade 60", 0.85, "LB", "vendor_quote"),
        ("03 30 00", "Ready-mix concrete 4000 psi", 165.00, "CY", "vendor_quote"),
        ("05 12 00", "Structural steel W-shapes", 2800.00, "TON", "vendor_quote"),
        ("05 31 00", "Composite steel deck 20GA", 3.25, "SF", "vendor_quote"),
        ("05 50 00", "Miscellaneous metals", 1.50, "LB", "rs_means"),
        ("07 21 00", "Rigid insulation 2\" polyiso", 1.85, "SF", "vendor_quote"),
        ("07 50 00", "TPO membrane 60 mil", 185.00, "SQ", "vendor_quote"),
        ("07 60 00", "Sheet metal 24GA galv", 8.50, "LF", "rs_means"),
        ("07 92 00", "Silicone sealant", 2.25, "LF", "vendor_quote"),
        ("08 11 00", "HM door & frame assembly", 650.00, "EA", "vendor_quote"),
        ("08 50 00", "Aluminum window assembly", 425.00, "EA", "vendor_quote"),
        ("09 29 00", "5/8\" gypsum board", 0.65, "SF", "vendor_quote"),
        ("09 30 00", "Ceramic tile material", 6.50, "SF", "vendor_quote"),
        ("09 51 00", "ACT tile and grid", 2.15, "SF", "vendor_quote"),
        ("09 91 00", "Paint (2-coat system)", 0.45, "SF", "rs_means"),
    ]
    for csi, desc, cost, unit, src in material_data:
        db.add(MaterialPrice(
            csi_code=csi, description=desc, unit_cost=cost,
            unit_of_measure=unit, source=src, region="Denver, CO",
        ))
    db.commit()

    # --- Labor Estimates for Project 1 ---
    labor_data = [
        (takeoff_items[0], "03 10 00", "Concrete Forming", "Carpenter Crew", 50, 45000, 4, 72.00),
        (takeoff_items[1], "03 10 00", "Edge Forming", "Carpenter Crew", 80, 12000, 4, 72.00),
        (takeoff_items[2], "03 20 00", "Rebar Placement", "Ironworker Crew", 500, 760000, 4, 92.00),
        (takeoff_items[3], "03 30 00", "Structural Concrete", "Concrete Crew", 1.5, 4200, 6, 78.50),
        (takeoff_items[4], "03 30 00", "SOG Concrete", "Concrete Crew", 3.0, 850, 6, 78.50),
        (takeoff_items[5], "05 12 00", "Structural Steel", "Ironworker Crew", 0.15, 1850, 4, 92.00),
        (takeoff_items[6], "05 31 00", "Steel Decking", "Ironworker Crew", 300, 165000, 4, 92.00),
        (takeoff_items[7], "05 50 00", "Misc Metals", "Ironworker Crew", 100, 45000, 4, 92.00),
        (takeoff_items[8], "07 21 00", "Rigid Insulation", "Insulation Crew", 80, 82000, 3, 65.00),
        (takeoff_items[9], "07 50 00", "TPO Roofing", "Roofing Crew", 25, 28500, 5, 70.00),
        (takeoff_items[10], "07 60 00", "Flashing", "Sheet Metal Crew", 20, 4200, 3, 82.00),
        (takeoff_items[11], "07 92 00", "Joint Sealants", "Caulking Crew", 80, 18500, 2, 62.00),
        (takeoff_items[12], "08 11 00", "Metal Doors", "Carpentry Crew", 4, 210, 4, 72.00),
        (takeoff_items[13], "08 50 00", "Windows", "Glazing Crew", 3, 340, 3, 80.00),
        (takeoff_items[14], "09 29 00", "Drywall Walls", "Drywall Crew", 150, 285000, 4, 68.00),
        (takeoff_items[15], "09 29 00", "Drywall Ceilings", "Drywall Crew", 150, 42000, 4, 68.00),
        (takeoff_items[16], "09 30 00", "Floor Tile", "Tile Crew", 15, 14500, 3, 75.00),
        (takeoff_items[17], "09 30 00", "Wall Tile", "Tile Crew", 15, 3200, 3, 75.00),
        (takeoff_items[18], "09 51 00", "ACT Ceilings", "Ceiling Crew", 100, 165000, 3, 68.00),
        (takeoff_items[19], "09 91 00", "Painting", "Painting Crew", 250, 520000, 4, 58.00),
    ]

    labor_items = []
    for ti, csi, wtype, crew, rate, qty, crew_size, hr_rate in labor_data:
        hours = qty / rate
        man_hours = hours * crew_size
        cost = man_hours * hr_rate
        le = LaborEstimate(
            project_id=p1.id, takeoff_item_id=ti.id, csi_code=csi,
            work_type=wtype, crew_type=crew, productivity_rate=rate,
            quantity=qty, labor_hours=round(hours, 2), crew_size=crew_size,
            crew_days=round(hours / 8, 2), hourly_rate=hr_rate,
            total_labor_cost=round(cost, 2),
        )
        db.add(le)
        labor_items.append(le)
    db.commit()

    # --- Estimate for Project 1 ---
    total_labor = sum(le.total_labor_cost for le in labor_items)
    total_material = 0
    for ti, mat_price in zip(takeoff_items, [3.50*45000, 3.50*12000, 0.85*760000, 165*4200, 165*850,
                                              2800*1850, 3.25*165000, 1.50*45000, 1.85*82000, 185*285,
                                              8.50*4200, 2.25*18500, 650*210, 425*340, 0.65*285000,
                                              0.65*42000, 6.50*14500, 6.50*3200, 2.15*165000, 0.45*520000]):
        total_material += mat_price

    total_direct = total_labor + total_material
    overhead = total_direct * 0.10
    profit = (total_direct + overhead) * 0.08
    contingency = (total_direct + overhead + profit) * 0.05
    total_bid = total_direct + overhead + profit + contingency

    estimate = Estimate(
        project_id=p1.id, version=1, status="draft",
        total_direct_cost=round(total_direct, 2),
        total_labor_cost=round(total_labor, 2),
        total_material_cost=round(total_material, 2),
        total_subcontractor_cost=0,
        overhead_pct=10.0, overhead_amount=round(overhead, 2),
        profit_pct=8.0, profit_amount=round(profit, 2),
        contingency_pct=5.0, contingency_amount=round(contingency, 2),
        total_bid_amount=round(total_bid, 2),
        exclusions=[
            "Hazardous material abatement",
            "Overtime premiums",
            "Furniture, fixtures & equipment",
            "Fire suppression systems (Division 21)",
            "Plumbing systems (Division 22)",
            "HVAC systems (Division 23)",
            "Electrical systems (Division 26)",
        ],
        assumptions=[
            "Normal working hours (7AM-3:30PM, M-F)",
            "Site access provided by Owner",
            "Material pricing valid 30 days",
            "Quantities based on plan takeoff",
        ],
        alternates=[
            {"name": "ALT-1: Upgraded Lobby Finishes", "amount": 185000},
            {"name": "ALT-2: Green Roof at Level 12", "amount": 420000},
        ],
        bid_bond_required=1,
        summary_json={"divisions_covered": ["03", "05", "07", "08", "09"]},
    )
    db.add(estimate)
    db.commit()
    db.refresh(estimate)

    # Estimate line items
    mat_prices_list = [3.50, 3.50, 0.85, 165, 165, 2800, 3.25, 1.50, 1.85, 185/100,
                       8.50, 2.25, 650, 425, 0.65, 0.65, 6.50, 6.50, 2.15, 0.45]
    for i, (le, ti) in enumerate(zip(labor_items, takeoff_items)):
        mat_cost = mat_prices_list[i] * ti.quantity
        equip_cost = le.total_labor_cost * 0.07
        total = le.total_labor_cost + mat_cost + equip_cost
        db.add(EstimateLineItem(
            estimate_id=estimate.id, division_number=le.csi_code[:2],
            csi_code=le.csi_code, description=f"{le.work_type} - {ti.description}",
            quantity=ti.quantity, unit_of_measure=ti.unit_of_measure,
            labor_cost=le.total_labor_cost, material_cost=round(mat_cost, 2),
            equipment_cost=round(equip_cost, 2), subcontractor_cost=0,
            total_cost=round(total, 2),
            unit_cost=round(total / ti.quantity, 2) if ti.quantity else 0,
        ))
    db.commit()

    # --- Project 3 Actuals (completed project for IMPROVE demo) ---
    actuals_data = [
        ("03 30 00", "Structural Concrete", 3200, 3100, 2400, 2580, 475000, 512000, "Concrete Crew", "Structural Concrete"),
        ("05 12 00", "Structural Steel", 950, 950, 6333, 6800, 740000, 785000, "Ironworker Crew", "Structural Steel"),
        ("05 31 00", "Steel Decking", 120000, 120000, 400, 380, 185000, 178000, "Ironworker Crew", "Steel Decking"),
        ("07 21 00", "Rigid Insulation", 65000, 67000, 812, 790, 115000, 118000, "Insulation Crew", "Rigid Insulation"),
        ("07 50 00", "TPO Roofing", 180000, 180000, 7200, 8180, 580000, 650000, "Roofing Crew", "TPO Roofing"),
        ("09 29 00", "Gypsum Board", 30000, 30000, 200, 188, 75000, 72000, "Drywall Crew", "Gypsum Board"),
        ("09 91 00", "Painting", 180000, 185000, 720, 685, 95000, 92000, "Painting Crew", "Interior Painting"),
    ]
    for csi, desc, est_qty, act_qty, est_hrs, act_hrs, est_cost, act_cost, crew, wtype in actuals_data:
        db.add(ProjectActual(
            project_id=p3.id, csi_code=csi, description=desc,
            estimated_quantity=est_qty, actual_quantity=act_qty,
            estimated_labor_hours=est_hrs, actual_labor_hours=act_hrs,
            estimated_cost=est_cost, actual_cost=act_cost,
            variance_hours=act_hrs - est_hrs, variance_cost=act_cost - est_cost,
            variance_pct=round((act_cost - est_cost) / est_cost * 100, 2) if est_cost else 0,
            crew_type=crew, work_type=wtype,
        ))
    db.commit()

    # --- Agent Run Logs for Project 1 ---
    base_time = now - timedelta(hours=2)
    logs = [
        ("Document Ingestion Agent", 1, "completed", 0, 45.2, 1200, "Ingested 3 documents"),
        ("Spec Parser Agent", 2, "completed", 50, 32.8, 2400, "Parsed 16 spec sections"),
        ("Scope Gap Analysis Agent", 3, "completed", 85, 18.5, 800, "Found 8 scope gaps"),
        ("Quantity Takeoff Agent", 4, "completed", 85, 22.1, 1600, "Generated 20 takeoff items"),
        ("Labor Productivity Agent", 5, "completed", 110, 15.3, 600, "Estimated 20 labor items"),
        ("Estimate Assembly Agent", 6, "completed", 130, 12.7, 1000, "Assembled estimate v1"),
    ]
    for name, num, status, offset_s, dur, tokens, summary in logs:
        start = base_time + timedelta(seconds=offset_s)
        db.add(AgentRunLog(
            project_id=p1.id, agent_name=name, agent_number=num,
            status=status, started_at=start,
            completed_at=start + timedelta(seconds=dur),
            duration_seconds=dur, tokens_used=tokens, output_summary=summary,
        ))
    db.commit()


def _sample_spec_text():
    return """PROJECT SPECIFICATIONS
MERIDIAN OFFICE TOWER
SUMMIT BUILDERS INC.

SECTION 03 10 00 - CONCRETE FORMING AND ACCESSORIES
PART 1 - GENERAL
1.1 SUBMITTALS
Submit shop drawings for shoring layout.
PART 2 - PRODUCTS
Forms: Steel-framed plywood panels per ACI 347
PART 3 - EXECUTION
Install formwork for elevated slabs. 45,000 SF forming.

SECTION 03 20 00 - CONCRETE REINFORCING
PART 1 - GENERAL
1.1 SUBMITTALS: Mill certificates, placing drawings
PART 2 - PRODUCTS: ASTM A615 Grade 60 deformed bars
PART 3 - EXECUTION: Place approximately 380 tons reinforcing steel.

SECTION 03 30 00 - CAST-IN-PLACE CONCRETE
PART 1 - GENERAL
1.1 SUBMITTALS: Mix designs, strength test reports
PART 2 - PRODUCTS: ASTM C150 Portland cement, 4000-6000 psi
PART 3 - EXECUTION: Place 4,200 CY structural concrete, 850 CY SOG.

SECTION 05 12 00 - STRUCTURAL STEEL FRAMING
PART 1 - GENERAL
1.1 SUBMITTALS: Shop drawings per AISC 360
PART 2 - PRODUCTS: ASTM A992 W-shapes, HSS
PART 3 - EXECUTION: Erect 1,850 tons structural steel. Refer to S-301.

SECTION 05 31 00 - STEEL DECKING
PART 1 - GENERAL
PART 2 - PRODUCTS: 3" 20GA composite deck per ASTM A653
PART 3 - EXECUTION: Install 165,000 SF composite deck.

SECTION 05 50 00 - METAL FABRICATIONS
PART 1 - GENERAL
PART 2 - PRODUCTS: ASTM A36 steel
PART 3 - EXECUTION: Fabricate and install misc metals. 45,000 LB.

SECTION 07 21 00 - THERMAL INSULATION
PART 1 - GENERAL
PART 2 - PRODUCTS: Rigid polyiso insulation per ASTM C578
PART 3 - EXECUTION: Install 82,000 SF R-25 continuous insulation.

SECTION 07 50 00 - MEMBRANE ROOFING
PART 1 - GENERAL
PART 2 - PRODUCTS: 60-mil TPO per ASTM D6878
PART 3 - EXECUTION: Install 28,500 SF fully adhered TPO roof system.

SECTION 07 60 00 - FLASHING AND SHEET METAL
PART 2 - PRODUCTS: ASTM B209 aluminum sheet
PART 3 - EXECUTION: Install copings, counterflashing. 4,200 LF.

SECTION 07 92 00 - JOINT SEALANTS
PART 2 - PRODUCTS: Silicone per ASTM C920
PART 3 - EXECUTION: Seal all exterior joints. 18,500 LF.

SECTION 08 11 00 - METAL DOORS AND FRAMES
PART 2 - PRODUCTS: Per ANSI A250.8
PART 3 - EXECUTION: Install 210 EA doors and frames.

SECTION 08 50 00 - WINDOWS
PART 2 - PRODUCTS: Aluminum per AAMA/WDMA
PART 3 - EXECUTION: Install 340 EA windows.

SECTION 09 29 00 - GYPSUM BOARD
PART 2 - PRODUCTS: 5/8" Type X per ASTM C1396
PART 3 - EXECUTION: Install 285,000 SF walls, 42,000 SF ceilings.

SECTION 09 30 00 - TILING
PART 2 - PRODUCTS: Per ANSI A137.1
PART 3 - EXECUTION: 14,500 SF floor tile, 3,200 SF wall tile.

SECTION 09 51 00 - ACOUSTICAL CEILINGS
PART 2 - PRODUCTS: Lay-in panels per ASTM E1264
PART 3 - EXECUTION: Install 165,000 SF suspended ceiling system.

SECTION 09 91 00 - PAINTING
PART 2 - PRODUCTS: Per SSPC standards
PART 3 - EXECUTION: Paint 520,000 SF. 2-coat system all surfaces.
"""
