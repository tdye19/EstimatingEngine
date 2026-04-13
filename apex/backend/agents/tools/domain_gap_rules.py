"""Domain-specific gap analysis rules for concrete and civil scopes.

25 rules encoding construction estimating expertise:
- 15 Concrete (CGR-001 to CGR-015)
- 10 Civil/Earthwork (CIV-001 to CIV-010)

These rules fire during Agent 3's rule-based fallback path,
producing richer gap findings than the generic checklist comparison.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel

logger = logging.getLogger("apex.tools.domain_gap_rules")


class DomainGapRule(BaseModel):
    """A domain-specific gap analysis rule with trigger conditions and output data."""

    id: str
    name: str
    gap_type: str  # "missing", "ambiguous", "scope_boundary"
    severity: str  # "critical", "moderate", "watch"
    scope_includes_any: list[str] = []  # CSI codes — at least one must be in parsed sections
    scope_excludes_all: list[str] = []  # CSI codes — ALL must be absent for rule to fire
    spec_keywords: list[str] = []  # Keywords to find in spec content
    spec_keyword_match: str = "any"  # "any" or "all"
    title: str = ""
    description: str = ""
    recommendation: str = ""
    typical_responsibility: str = ""
    cost_impact_description: str = ""
    cost_impact_low: float | None = None
    cost_impact_high: float | None = None
    rfi_language: str = ""
    affected_csi_codes: list[str] = []


CONCRETE_GAP_RULES: list[DomainGapRule] = [
    DomainGapRule(
        id="CGR-001",
        name="Vapor Barrier Responsibility",
        gap_type="missing",
        severity="critical",
        scope_includes_any=["03 31 09", "03 31 10"],
        scope_excludes_all=["03 15 05"],
        spec_keywords=[
            "vapor barrier",
            "vapor retarder",
            "underslab membrane",
            "moisture barrier",
            "ASTM E1745",
            "15-mil",
            "10-mil",
        ],
        title="Vapor Barrier / Retarder Under SOG",
        description=(
            "Spec requires a vapor barrier or retarder under slabs on grade, but your concrete "
            "scope does not include vapor barriers (03 15 05). This is a common scope gap — verify "
            "if carried under Division 07 by waterproofing sub, or add to your concrete scope."
        ),
        typical_responsibility="Varies — often installed by concrete crew, sometimes by waterproofing sub",
        cost_impact_description="$0.50–$1.50/SF of SOG area",
        cost_impact_low=0.50,
        cost_impact_high=1.50,
        recommendation=(
            "Clarify in bid. If by concrete contractor, add material + labor for vapor barrier installation."
        ),
        rfi_language=(
            "Please clarify: Is the underslab vapor barrier to be furnished and installed by the "
            "concrete contractor or by a separate waterproofing contractor?"
        ),
        affected_csi_codes=["03 15 05", "07 26 00"],
    ),
    DomainGapRule(
        id="CGR-002",
        name="Embedded Items — Anchor Bolts & Embeds",
        gap_type="scope_boundary",
        severity="critical",
        scope_includes_any=["03 31 04", "03 31 06", "03 31 01", "03 31 02", "03 31 12"],
        scope_excludes_all=["03 15 06", "03 15 08"],
        spec_keywords=[
            "anchor bolt",
            "embed",
            "steel embed",
            "embed plate",
            "nelson stud",
            "headed stud",
            "base plate",
            "connection",
        ],
        title="Anchor Bolts & Steel Embeds Responsibility",
        description=(
            "Structural concrete elements are in scope but anchor bolts and steel embeds are not "
            "explicitly included. These are a frequent source of scope disputes. Structural steel "
            "fabricator typically furnishes, concrete contractor places. Clarify who furnishes, who "
            "places, and who is responsible for layout accuracy."
        ),
        typical_responsibility="Furnished by steel fabricator, placed by concrete contractor, layout by surveyor",
        cost_impact_description="Material: $2–$15/embed; Labor: 0.25–1.0 hr/embed; Layout: LS",
        cost_impact_low=500,
        cost_impact_high=15000,
        recommendation=(
            "Include placement labor in your scope. Exclude material (furnished by others). "
            "Qualify layout responsibility."
        ),
        rfi_language=(
            "Please confirm: Anchor bolts and steel embeds to be (a) furnished by structural steel "
            "fabricator and (b) placed by concrete contractor? Layout and survey responsibility?"
        ),
        affected_csi_codes=["03 15 06", "03 15 08", "05 12 00"],
    ),
    DomainGapRule(
        id="CGR-003",
        name="Rebar Coating Specification",
        gap_type="missing",
        severity="moderate",
        scope_includes_any=["03 21 01"],
        scope_excludes_all=["03 21 02", "03 21 03", "03 21 05"],
        spec_keywords=[
            "epoxy coated",
            "epoxy-coated",
            "galvanized rebar",
            "ASTM A775",
            "ASTM A934",
            "ASTM A767",
            "fusion bonded",
            "corrosion protection",
            "stainless steel rebar",
        ],
        title="Rebar Coating Required by Spec",
        description=(
            "Your scope includes uncoated (black) rebar, but specs reference coated or "
            "corrosion-protected reinforcing. Epoxy coating adds 15–25% to rebar material cost. "
            "Galvanized adds 30–50%. Stainless steel can be 5–8x standard rebar cost. Verify which "
            "elements require coating and update your scope and pricing."
        ),
        typical_responsibility="Concrete contractor / rebar sub",
        cost_impact_description="Epoxy: +$0.08–$0.15/lb; Galv: +$0.15–$0.30/lb; Stainless: +$2.00–$4.00/lb",
        cost_impact_low=0.08,
        cost_impact_high=4.00,
        recommendation=(
            "Review structural drawings for coating callouts. Price to the most expensive specified condition."
        ),
        affected_csi_codes=["03 21 02", "03 21 03", "03 21 05"],
    ),
    DomainGapRule(
        id="CGR-004",
        name="Architectural Concrete Requirements",
        gap_type="missing",
        severity="critical",
        scope_includes_any=["03 11 01", "03 11 02", "03 11 04", "03 31 04", "03 31 05"],
        scope_excludes_all=["03 33 01", "03 33 02", "03 33 03", "03 33 04"],
        spec_keywords=[
            "architectural concrete",
            "exposed concrete",
            "form liner",
            "board form",
            "board-formed",
            "special finish",
            "Class A finish",
            "Class B finish",
            "rubbed finish",
            "bush hammer",
            "sandblast finish",
            "concrete mockup",
            "sample panel",
        ],
        title="Architectural / Exposed Concrete Finish Required",
        description=(
            "Specs call for architectural or exposed concrete finishes, but your scope does not "
            "include architectural concrete items. Architectural concrete requires premium forming "
            "(tight joints, high-quality materials), special release agents, possible form liners, "
            "and concrete mockup panels. This can increase forming costs 2–5x over standard."
        ),
        typical_responsibility="Concrete contractor — but commonly underpriced or missed entirely",
        cost_impact_description="2–5x standard forming cost; mockup: $5,000–$25,000 each",
        cost_impact_low=5000,
        cost_impact_high=100000,
        recommendation=(
            "Add architectural concrete line items. Verify mockup requirements. "
            "Price form liners as a separate material item."
        ),
        rfi_language=(
            "Please identify all locations of architectural / exposed concrete finish. "
            "Are mockup panels required prior to production? How many?"
        ),
        affected_csi_codes=["03 33 01", "03 33 02", "03 33 03", "03 33 04"],
    ),
    DomainGapRule(
        id="CGR-005",
        name="Concrete Pumping Costs",
        gap_type="scope_boundary",
        severity="moderate",
        scope_includes_any=["03 31 08", "03 31 09", "03 31 03"],
        scope_excludes_all=[],
        spec_keywords=[
            "concrete pump",
            "pumping",
            "boom pump",
            "line pump",
            "pump mix",
            "pumpable",
        ],
        title="Concrete Pumping Responsibility",
        description=(
            "Your scope includes concrete elements that may require pumping (elevated slabs, large "
            "SOG pours, or mat foundations). Concrete pump costs are frequently missed or assumed to "
            "be included in the ready-mix price. Verify who provides and pays for the pump."
        ),
        typical_responsibility="Usually concrete contractor arranges and pays for pump",
        cost_impact_description="Line pump: $1,500–$3,500/day; Boom pump: $2,500–$6,000/day",
        cost_impact_low=1500,
        cost_impact_high=30000,
        recommendation=("Include pump costs. Estimate number of pump days based on pour volumes and schedule."),
        affected_csi_codes=["03 30 00"],
    ),
    DomainGapRule(
        id="CGR-006",
        name="Cold/Hot Weather Concrete Provisions",
        gap_type="missing",
        severity="moderate",
        scope_includes_any=["03 30 00", "03 31 00"],
        scope_excludes_all=[],
        spec_keywords=[
            "cold weather",
            "hot weather",
            "winter protection",
            "heated enclosure",
            "thermal blanket",
            "hoarding",
            "ACI 306",
            "ACI 305",
            "curing temperature",
            "minimum temperature",
            "accelerator",
            "calcium chloride",
        ],
        title="Weather Protection for Concrete",
        description=(
            "Specs reference cold or hot weather concrete provisions. If the project schedule "
            "includes winter pours (Michigan — likely), budget for heated enclosures, blankets, "
            "ground thaw, accelerators, and extended curing. Hot weather provisions include ice, "
            "retarders, shade structures, and night pours."
        ),
        typical_responsibility="Concrete contractor — often carried as separate line item or allowance",
        cost_impact_description=("Winter: $2–$8/SF enclosure + $500–$2,000/day heating; Hot weather: $1–$3/CY"),
        cost_impact_low=5000,
        cost_impact_high=100000,
        recommendation="Carry as separate allowance. Review project schedule vs. weather windows.",
        affected_csi_codes=["03 30 00"],
    ),
    DomainGapRule(
        id="CGR-007",
        name="Waterstop at Construction & Expansion Joints",
        gap_type="missing",
        severity="moderate",
        scope_includes_any=["03 31 04", "03 31 05"],
        scope_excludes_all=["03 15 01"],
        spec_keywords=[
            "waterstop",
            "water stop",
            "hydrophilic",
            "PVC waterstop",
            "bentonite",
            "construction joint",
            "water-tight",
            "below grade waterproofing",
        ],
        title="Waterstops Required at Joints",
        description=(
            "Specs indicate waterstops at construction or expansion joints in below-grade concrete, "
            "but waterstops are not in your scope. Waterstops are commonly missed in concrete "
            "estimates for foundation walls and retaining walls."
        ),
        typical_responsibility="Concrete contractor — material + installation",
        cost_impact_description="PVC: $3–$8/LF installed; Hydrophilic: $5–$12/LF installed",
        cost_impact_low=3,
        cost_impact_high=12,
        recommendation=("Add waterstop to scope. Calculate total LF of construction joints in below-grade walls."),
        affected_csi_codes=["03 15 01"],
    ),
    DomainGapRule(
        id="CGR-008",
        name="Post-Tensioning Required",
        gap_type="missing",
        severity="critical",
        scope_includes_any=["03 31 08", "03 31 09"],
        scope_excludes_all=["03 22 01", "03 22 02"],
        spec_keywords=[
            "post-tension",
            "post tension",
            "PT slab",
            "PT strand",
            "unbonded tendon",
            "bonded tendon",
            "stressing",
            "PTI",
            "post-tensioning institute",
        ],
        title="Post-Tensioning Specified",
        description=(
            "Specs call for post-tensioned slabs or other PT elements, but post-tensioning is not "
            "in your scope. PT is typically subcontracted to a specialty contractor. However, the "
            "concrete contractor must coordinate embed layout, blockout locations, pour sequences, "
            "and stressing schedule. PT system cost is significant and must be carried somewhere "
            "in the estimate."
        ),
        typical_responsibility="Subcontracted to PT specialty contractor; coordinated by concrete contractor",
        cost_impact_description="PT system: $3–$8/SF of PT slab; coordination: LS",
        cost_impact_low=3,
        cost_impact_high=8,
        recommendation=("Get PT sub quote. Include coordination effort and potential schedule impact in your scope."),
        rfi_language=(
            "Please confirm post-tensioning system type (bonded vs. unbonded), "
            "and identify all PT elements on drawings."
        ),
        affected_csi_codes=["03 22 01", "03 22 02"],
    ),
    DomainGapRule(
        id="CGR-009",
        name="Testing & Inspection Responsibility",
        gap_type="scope_boundary",
        severity="watch",
        scope_includes_any=["03 30 00", "03 31 00"],
        scope_excludes_all=[],
        spec_keywords=[
            "concrete testing",
            "compressive strength test",
            "cylinder",
            "slump test",
            "air content",
            "field testing",
            "special inspection",
            "third party testing",
            "Section 01 45",
            "Section 01 40",
        ],
        title="Concrete Testing & Special Inspection",
        description=(
            "Specs reference concrete testing and/or special inspection. This is typically paid "
            "for by the owner/CM, but verify. If the concrete contractor is responsible for any "
            "testing, include costs. At minimum, verify you are responsible for providing access, "
            "holding pours for testing, and casting cylinders."
        ),
        typical_responsibility="Owner/CM pays testing agency. Contractor provides access and cast cylinders.",
        cost_impact_description="$3,000–$15,000 if contractor-responsible",
        cost_impact_low=0,
        cost_impact_high=15000,
        recommendation="Review Division 01 for testing requirements. Include in bid qualifications.",
        affected_csi_codes=["01 45 00", "01 40 00"],
    ),
    DomainGapRule(
        id="CGR-010",
        name="High-Strength or Specialty Mix Designs",
        gap_type="missing",
        severity="moderate",
        scope_includes_any=["03 31 00", "03 30 00"],
        scope_excludes_all=["03 37 06", "03 37 05"],
        spec_keywords=[
            "6000 psi",
            "7000 psi",
            "8000 psi",
            "10000 psi",
            "high strength",
            "high-strength",
            "high performance",
            "self-consolidating",
            "SCC",
            "low heat",
            "supplementary cementitious",
            "fly ash",
            "slag cement",
            "silica fume",
            "GGBFS",
        ],
        title="High-Strength or Specialty Concrete Mix",
        description=(
            "Specs reference high-strength or specialty concrete mixes beyond standard 4000–5000 PSI. "
            "High-strength concrete has significant cost premiums and may require special placement "
            "procedures, extended curing, and pre-qualified mix designs. Verify all mix design "
            "requirements and price accordingly."
        ),
        typical_responsibility="Concrete contractor prices mix; ready-mix supplier develops mix design",
        cost_impact_description="6000 PSI: +$15–$30/CY; 8000+ PSI: +$40–$80/CY; SCC: +$30–$50/CY",
        cost_impact_low=15,
        cost_impact_high=80,
        recommendation="Get ready-mix quotes for all specified mixes. Carry premium per CY.",
        affected_csi_codes=["03 37 06", "03 37 05"],
    ),
    DomainGapRule(
        id="CGR-011",
        name="Mechanical Rebar Splices / Couplers",
        gap_type="missing",
        severity="moderate",
        scope_includes_any=["03 21 01", "03 21 00"],
        scope_excludes_all=["03 21 11"],
        spec_keywords=[
            "mechanical splice",
            "coupler",
            "mechanical coupler",
            "cadweld",
            "headed bar",
            "headed rebar",
            "ASTM A1034",
            "Type 1 splice",
            "Type 2 splice",
        ],
        title="Mechanical Rebar Splices Required",
        description=(
            "Specs require mechanical rebar splices or couplers instead of (or in addition to) "
            "standard lap splices. Mechanical splices are significantly more expensive than lap "
            "splices but may be required for congested areas, seismic detailing, or large bar sizes "
            "(#8 and above)."
        ),
        typical_responsibility="Concrete contractor / rebar sub furnishes and installs",
        cost_impact_description="$5–$50 per splice depending on bar size and type",
        cost_impact_low=5,
        cost_impact_high=50,
        recommendation=("Count splices on drawings. Get supplier quote for specific coupler type and bar sizes."),
        affected_csi_codes=["03 21 11"],
    ),
    DomainGapRule(
        id="CGR-012",
        name="Control Joint Sawcutting",
        gap_type="missing",
        severity="watch",
        scope_includes_any=["03 31 09", "03 31 10"],
        scope_excludes_all=["03 15 03"],
        spec_keywords=[
            "saw cut",
            "sawcut",
            "control joint",
            "contraction joint",
            "joint spacing",
            "joint layout",
            "slab joint",
        ],
        title="Control Joint Sawcutting for Slabs",
        description=(
            "SOG or topping slabs are in your scope but control/contraction joints are not "
            "explicitly included. Sawcutting is typically the concrete contractor's responsibility. "
            "Verify joint spacing and layout requirements."
        ),
        typical_responsibility="Concrete contractor",
        cost_impact_description="$0.75–$2.00/LF sawcut",
        cost_impact_low=0.75,
        cost_impact_high=2.00,
        recommendation=("Calculate total LF of sawcuts based on joint spacing and slab area. Include in scope."),
        affected_csi_codes=["03 15 03"],
    ),
    DomainGapRule(
        id="CGR-013",
        name="Special Curing Requirements",
        gap_type="missing",
        severity="moderate",
        scope_includes_any=["03 35 00", "03 31 00"],
        scope_excludes_all=[],
        spec_keywords=[
            "wet cure",
            "wet curing",
            "7-day cure",
            "14-day cure",
            "moist cure",
            "ponding",
            "burlap",
            "curing blanket",
            "curing compound",
            "membrane curing",
            "extended curing",
            "ASTM C309",
            "ASTM C171",
        ],
        title="Special Curing Beyond Standard",
        description=(
            "Specs call for extended or special curing methods beyond standard spray-on curing "
            "compound. Wet curing, burlap, ponding, or extended cure periods add significant labor "
            "cost and can impact the schedule. Verify curing requirements for each concrete element."
        ),
        typical_responsibility="Concrete contractor",
        cost_impact_description=("Standard cure: $0.10–$0.20/SF; Wet cure: $0.50–$1.50/SF; Extended: +$/day"),
        cost_impact_low=0.10,
        cost_impact_high=1.50,
        recommendation=("Identify elements requiring special curing. Add labor for daily wet cure maintenance."),
        affected_csi_codes=["03 35 07"],
    ),
    DomainGapRule(
        id="CGR-014",
        name="Fiber Reinforcement Specified",
        gap_type="missing",
        severity="moderate",
        scope_includes_any=["03 31 09", "03 31 10"],
        scope_excludes_all=["03 21 07", "03 21 08", "03 21 09"],
        spec_keywords=[
            "fiber reinforcement",
            "steel fiber",
            "synthetic fiber",
            "macro fiber",
            "micro fiber",
            "polypropylene fiber",
            "fiber dosage",
            "fibers per cubic yard",
        ],
        title="Fiber Reinforcement Required",
        description=(
            "Specs call for fiber reinforcement in concrete, but fiber reinforcement is not in your "
            "scope. Fiber is typically added at the batch plant and is either a ready-mix add charge "
            "or furnished by the contractor. Verify type, dosage, and responsibility."
        ),
        typical_responsibility="Usually specified as ready-mix additive; contractor pays upcharge",
        cost_impact_description=("Micro synthetic: $3–$6/CY; Macro synthetic: $8–$15/CY; Steel: $20–$45/CY"),
        cost_impact_low=3,
        cost_impact_high=45,
        recommendation=("Get ready-mix pricing with fiber dosage. May replace or supplement WWR — verify."),
        affected_csi_codes=["03 21 07", "03 21 08", "03 21 09"],
    ),
    DomainGapRule(
        id="CGR-015",
        name="Reshoring & Stripping Requirements",
        gap_type="missing",
        severity="moderate",
        scope_includes_any=["03 11 05", "03 31 08"],
        scope_excludes_all=[],
        spec_keywords=[
            "reshoring",
            "reshore",
            "shoring plan",
            "stripping time",
            "minimum strip time",
            "shore removal",
            "backshore",
            "28-day strength",
            "75% strength",
        ],
        title="Reshoring & Formwork Stripping Requirements",
        description=(
            "Elevated concrete is in scope. Verify reshoring requirements per the structural "
            "engineer's shoring plan. Multiple levels of reshoring can significantly increase "
            "form/shore material requirements and tie up equipment longer than planned. Extended "
            "strip times affect schedule."
        ),
        typical_responsibility="Concrete contractor per structural engineer's shoring plan",
        cost_impact_description=("Each additional level of reshoring: $1.50–$3.00/SF; Extended strip: schedule impact"),
        cost_impact_low=1.50,
        cost_impact_high=3.00,
        recommendation=("Get or develop shoring plan early. Price reshoring materials and extended rental."),
        affected_csi_codes=["03 11 05"],
    ),
]

CIVIL_GAP_RULES: list[DomainGapRule] = [
    DomainGapRule(
        id="CIV-001",
        name="Dewatering Not Included",
        gap_type="missing",
        severity="critical",
        scope_includes_any=["31 22 01", "31 23 00", "31 23 01", "31 23 02"],
        scope_excludes_all=["31 23 19"],
        spec_keywords=[
            "dewatering",
            "water table",
            "groundwater",
            "high water table",
            "well points",
            "sump pump",
            "cofferdam",
            "geotechnical report",
            "seasonal water",
        ],
        title="Dewatering Excluded from Earthwork Scope",
        description=(
            "Excavation is in your scope but dewatering is not. Specs or geotech report indicate "
            "potential groundwater issues. Dewatering can be one of the largest unforeseen costs in "
            "civil work. Even seasonal high water tables in Michigan can require dewatering for deep "
            "excavations."
        ),
        typical_responsibility="Civil contractor or specialty dewatering sub",
        cost_impact_description="$5,000–$50,000+ depending on conditions and duration",
        cost_impact_low=5000,
        cost_impact_high=50000,
        recommendation="Review geotech boring logs for water table elevation. Price as alternate if not included.",
        rfi_language=(
            "Geotech report indicates water table at elevation ___. Please confirm dewatering "
            "requirements and responsibility for excavations below this elevation."
        ),
        affected_csi_codes=["31 23 19"],
    ),
    DomainGapRule(
        id="CIV-002",
        name="Rock Excavation Potential",
        gap_type="ambiguous",
        severity="critical",
        scope_includes_any=["31 22 01", "31 23 00", "31 23 01"],
        scope_excludes_all=["31 33 00"],
        spec_keywords=[
            "rock excavation",
            "rock removal",
            "blasting",
            "rock line",
            "bedrock",
            "rock encountered",
            "hard excavation",
            "ripping",
            "hoe ram",
            "rock unit price",
        ],
        title="Rock Excavation Not Addressed",
        description=(
            "Excavation is in your scope but rock excavation is not. Review geotech report for "
            "bedrock depth. If rock is within excavation limits, mechanical removal (hoe ram) or "
            "blasting may be required. This is often handled as a unit price item but must be "
            "carried somewhere."
        ),
        typical_responsibility="Civil contractor — often unit price alternate",
        cost_impact_description="$15–$50/CY for mechanical removal; $5–$20/CY for blasting",
        cost_impact_low=15,
        cost_impact_high=50,
        recommendation="Carry rock excavation as unit price alternate in bid. Review geotech borings.",
        affected_csi_codes=["31 33 00"],
    ),
    DomainGapRule(
        id="CIV-003",
        name="Contaminated / Unsuitable Soil",
        gap_type="ambiguous",
        severity="critical",
        scope_includes_any=["31 22 01", "31 23 00", "31 25 01"],
        scope_excludes_all=[],
        spec_keywords=[
            "contaminated",
            "hazardous",
            "LNAPL",
            "DNAPL",
            "petroleum",
            "underground storage tank",
            "UST",
            "Phase I",
            "Phase II",
            "environmental",
            "special waste",
            "unsuitable material",
            "regulated material",
        ],
        title="Potential Contaminated Soil",
        description=(
            "Specs or environmental reports reference potential soil contamination. Contaminated "
            "soil disposal costs are dramatically higher than clean soil. Special handling, "
            "manifesting, and disposal at licensed facilities may be required. This can blow a "
            "budget if not properly addressed."
        ),
        typical_responsibility="Varies — often owner risk with contractor handling. Verify contract terms.",
        cost_impact_description=("Clean disposal: $10–$25/CY; Contaminated: $50–$300+/CY; Hazardous: $200–$1,000+/CY"),
        cost_impact_low=50,
        cost_impact_high=300,
        recommendation=(
            "Qualify bid: clean soil only. Contaminated soil as change order or unit price. Review Phase I/II."
        ),
        rfi_language=(
            "Has a Phase I or Phase II environmental assessment been performed? Are there known "
            "soil contamination conditions? Please clarify disposal requirements and responsibility."
        ),
        affected_csi_codes=["31 25 01"],
    ),
    DomainGapRule(
        id="CIV-004",
        name="Cut/Fill Imbalance — Import/Export",
        gap_type="scope_boundary",
        severity="moderate",
        scope_includes_any=["31 22 01", "31 22 02"],
        scope_excludes_all=[],
        spec_keywords=[
            "import",
            "export",
            "borrow",
            "waste",
            "haul off",
            "disposal",
            "off-site",
            "spoils",
            "cut and fill",
            "earthwork balance",
            "mass diagram",
        ],
        title="Earthwork Balance — Import/Export Costs",
        description=(
            "Your scope includes mass earthwork (cut and fill). Verify the earthwork balance — "
            "is the site balanced, or will significant import or export of material be required? "
            "Hauling costs are distance-dependent and can be a major cost driver."
        ),
        typical_responsibility="Civil contractor",
        cost_impact_description="Haul: $8–$20/CY depending on distance; Import fill: $12–$25/CY delivered",
        cost_impact_low=8,
        cost_impact_high=25,
        recommendation="Calculate cut/fill balance from grading plan. Get haul distance and disposal/source quotes.",
        affected_csi_codes=["31 25 00", "31 25 01", "31 25 02"],
    ),
    DomainGapRule(
        id="CIV-005",
        name="Erosion Control Maintenance Duration",
        gap_type="scope_boundary",
        severity="moderate",
        scope_includes_any=["31 14 00", "31 14 01"],
        scope_excludes_all=[],
        spec_keywords=[
            "SWPPP",
            "NPDES",
            "erosion control maintenance",
            "inspection",
            "weekly inspection",
            "storm event",
            "BMP maintenance",
            "sediment removal",
            "final stabilization",
            "EGLE",
            "DEQ",
        ],
        title="Erosion Control Maintenance Responsibility & Duration",
        description=(
            "Erosion control installation is in your scope. Clarify: Are you responsible for "
            "ongoing maintenance, weekly inspections, and post-storm event repairs? For how long? "
            "Until final stabilization? This can extend well beyond your earthwork scope duration "
            "and the costs add up."
        ),
        typical_responsibility=(
            "Varies — initial install by civil; maintenance may be GC or civil depending on contract"
        ),
        cost_impact_description="Maintenance: $500–$2,000/month; Repairs: $2,000–$10,000 per event",
        cost_impact_low=500,
        cost_impact_high=25000,
        recommendation="Clarify maintenance duration and responsibility in bid. Include monthly allowance.",
        affected_csi_codes=["31 14 00"],
    ),
    DomainGapRule(
        id="CIV-006",
        name="Utility Crossings & Conflicts",
        gap_type="ambiguous",
        severity="moderate",
        scope_includes_any=["33 11 00", "33 31 00", "33 41 00"],
        scope_excludes_all=[],
        spec_keywords=[
            "utility crossing",
            "conflict",
            "existing utility",
            "Miss Dig",
            "MISS DIG",
            "pothole",
            "test pit",
            "utility relocation",
            "protect in place",
        ],
        title="Existing Utility Crossings & Conflicts",
        description=(
            "New utility installation is in your scope. Verify existing utility locations and "
            "potential conflicts. Crossings, protection-in-place, and relocations can add "
            "significant cost. Review available utility survey and require test pits / potholing "
            "at critical crossings."
        ),
        typical_responsibility="Civil contractor; relocations may be by utility company",
        cost_impact_description=(
            "Test pits: $500–$1,500/each; Protection: $1,000–$5,000/crossing; Relocation: $5,000–$50,000+"
        ),
        cost_impact_low=500,
        cost_impact_high=50000,
        recommendation=(
            "Request utility survey. Identify crossings on plans. Carry allowance for unforeseen conflicts."
        ),
        affected_csi_codes=["33 10 00", "33 30 00", "33 40 00"],
    ),
    DomainGapRule(
        id="CIV-007",
        name="Compaction Testing Responsibility",
        gap_type="scope_boundary",
        severity="watch",
        scope_includes_any=["31 23 16", "31 23 10"],
        scope_excludes_all=[],
        spec_keywords=[
            "compaction test",
            "proctor",
            "nuclear density",
            "field density",
            "95% compaction",
            "90% compaction",
            "modified proctor",
            "standard proctor",
        ],
        title="Compaction Testing Responsibility",
        description=(
            "Backfill and compaction are in your scope. Verify who is responsible for compaction "
            "testing (nuclear density, sand cone, etc.). Typically owner/CM, but failing tests "
            "mean rework costs for the contractor."
        ),
        typical_responsibility="Owner/CM pays for testing; contractor pays for rework if failing",
        cost_impact_description="Testing: $2,000–$10,000 if contractor-responsible; Rework: $5–$15/CY",
        cost_impact_low=0,
        cost_impact_high=10000,
        recommendation="Verify testing responsibility in Division 01. Budget for potential rework.",
        affected_csi_codes=["31 23 16"],
    ),
    DomainGapRule(
        id="CIV-008",
        name="Trench Safety & OSHA Requirements",
        gap_type="missing",
        severity="critical",
        scope_includes_any=["31 23 02", "33 11 00", "33 31 00", "33 41 00"],
        scope_excludes_all=["31 54 00"],
        spec_keywords=[
            "trench safety",
            "trench box",
            "shoring",
            "sloping",
            "benching",
            "trench shield",
            "OSHA",
            "competent person",
            "excavation safety",
            "29 CFR 1926",
        ],
        title="Trench Safety / Shoring for Utilities",
        description=(
            "Utility trench excavation is in your scope but trench shoring is not explicitly "
            "included. OSHA requires protection for trenches >5 ft deep. Even if not spec'd, this "
            "is a regulatory requirement and a cost that must be carried. Include trench box rental "
            "or sloping costs."
        ),
        typical_responsibility="Civil contractor — mandatory regardless of spec",
        cost_impact_description="Trench box rental: $500–$2,000/month; Sloping: additional excavation volume",
        cost_impact_low=500,
        cost_impact_high=10000,
        recommendation="Budget trench box rental for duration of utility work. Always required >5 ft depth.",
        affected_csi_codes=["31 54 00"],
    ),
    DomainGapRule(
        id="CIV-009",
        name="Subgrade Preparation for Building/Paving",
        gap_type="scope_boundary",
        severity="moderate",
        scope_includes_any=["31 23 20", "31 22 00"],
        scope_excludes_all=[],
        spec_keywords=[
            "subgrade",
            "subbase",
            "proof roll",
            "lime stabilization",
            "cement stabilization",
            "geogrid",
            "geotextile",
            "bearing capacity",
            "subgrade modulus",
        ],
        title="Subgrade Preparation Scope Boundary",
        description=(
            "Fine grading / earthwork is in your scope. Clarify the handoff point: Does your "
            "scope include subgrade preparation to specific tolerances for building foundations, "
            "slabs on grade, and pavement? Or does the concrete / paving contractor handle final "
            "subgrade prep? This is a common gap between civil and concrete scopes."
        ),
        typical_responsibility="Usually civil prepares to rough subgrade; concrete/paving does final prep",
        cost_impact_description="Lime/cement stabilization: $3–$8/SY; Geogrid: $1.50–$4.00/SY",
        cost_impact_low=1.50,
        cost_impact_high=8.00,
        recommendation="Define handoff tolerance clearly. Include in bid qualifications.",
        affected_csi_codes=["31 23 20", "31 31 00"],
    ),
    DomainGapRule(
        id="CIV-010",
        name="Utility Connection / Tap Fees",
        gap_type="scope_boundary",
        severity="moderate",
        scope_includes_any=["33 11 00", "33 12 00", "33 31 00", "33 32 00"],
        scope_excludes_all=[],
        spec_keywords=[
            "tap fee",
            "connection fee",
            "permit",
            "road cut",
            "road opening",
            "utility tap",
            "main connection",
            "wet tap",
            "hot tap",
            "shutdown",
        ],
        title="Utility Connection & Tap Fees",
        description=(
            "Utility installation is in your scope. Clarify: Are tap fees, connection fees, and "
            "road opening permits included in your scope or paid by the owner? Also verify who "
            "performs the actual connection to existing mains — utility company or contractor."
        ),
        typical_responsibility=("Owner typically pays fees; contractor performs connections (varies by municipality)"),
        cost_impact_description=("Tap fees: $500–$10,000+ per connection; Road cut: $2,000–$15,000 per opening"),
        cost_impact_low=500,
        cost_impact_high=25000,
        recommendation=(
            "Contact local utility and municipality for fee schedules. Exclude fees; include labor for connections."
        ),
        affected_csi_codes=["33 10 00", "33 30 00"],
    ),
]

ALL_DOMAIN_RULES: list[DomainGapRule] = CONCRETE_GAP_RULES + CIVIL_GAP_RULES


def _normalize_csi_set(parsed_sections: list[dict]) -> set[str]:
    """Build normalized set of CSI codes from parsed sections for matching."""
    codes = set()
    for s in parsed_sections:
        sec = s.get("section_number", "").replace(" ", "").replace(".", "")
        codes.add(sec)
        if len(sec) >= 4:
            codes.add(sec[:4])
        if len(sec) >= 6:
            codes.add(sec[:6])
    return codes


def _code_matches(csi_code: str, normalized_set: set[str]) -> bool:
    """Check if a CSI code matches anything in the normalized set."""
    clean = csi_code.replace(" ", "").replace(".", "")
    if clean in normalized_set:
        return True
    if len(clean) >= 4 and clean[:4] in normalized_set:
        return True
    if len(clean) >= 6 and clean[:6] in normalized_set:
        return True
    return False


def run_domain_rules(
    parsed_sections: list[dict],
    spec_content_text: str = "",
) -> list[dict]:
    """Run all domain gap rules against parsed spec sections.

    Args:
        parsed_sections: List of dicts with section_number, division_number keys
            (same format Agent 3 already uses).
        spec_content_text: Concatenated text content from SpecSection rows.
            Used for keyword matching. If empty, keyword check is skipped
            (rules fire on scope conditions alone).

    Returns:
        List of gap dicts compatible with gap_scorer_tool / risk_tagger_tool.
    """
    normalized = _normalize_csi_set(parsed_sections)
    text_lower = spec_content_text.lower() if spec_content_text else ""
    triggered: list[dict] = []

    for rule in ALL_DOMAIN_RULES:
        # Check scope_includes_any: at least one must match
        if rule.scope_includes_any:
            if not any(_code_matches(c, normalized) for c in rule.scope_includes_any):
                continue

        # Check scope_excludes_all: ALL must be absent
        if rule.scope_excludes_all:
            if any(_code_matches(c, normalized) for c in rule.scope_excludes_all):
                continue

        # Check spec keywords
        if rule.spec_keywords and text_lower:
            kw_hits = [kw.lower() in text_lower for kw in rule.spec_keywords]
            if rule.spec_keyword_match == "all":
                if not all(kw_hits):
                    continue
            else:
                if not any(kw_hits):
                    continue

        # Rule triggered — build gap dict
        triggered.append(
            {
                "division_number": rule.affected_csi_codes[0][:2] if rule.affected_csi_codes else "00",
                "section_number": rule.affected_csi_codes[0] if rule.affected_csi_codes else None,
                "title": rule.title,
                "gap_type": rule.gap_type,
                "severity": rule.severity,
                "description": rule.description,
                "recommendation": rule.recommendation,
                "cost_impact_description": rule.cost_impact_description,
                "cost_impact_low": rule.cost_impact_low,
                "cost_impact_high": rule.cost_impact_high,
                "typical_responsibility": rule.typical_responsibility,
                "rfi_language": rule.rfi_language,
                "rule_id": rule.id,
            }
        )

    logger.info(f"Domain rules: {len(triggered)} of {len(ALL_DOMAIN_RULES)} rules triggered")
    return triggered
