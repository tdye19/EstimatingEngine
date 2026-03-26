"""Domain-specific gap analysis rules for concrete and civil scopes.

25 rules encoding construction estimating expertise:
- 15 Concrete (CGR-001 to CGR-015)
- 10 Civil/Earthwork (CIV-001 to CIV-010)

These rules fire during Agent 3's rule-based fallback path,
producing richer gap findings than the generic checklist comparison.
"""

from __future__ import annotations
import logging
from typing import Optional
from pydantic import BaseModel

logger = logging.getLogger("apex.tools.domain_gap_rules")


class DomainGapRule(BaseModel):
    """A domain-specific gap analysis rule with trigger conditions and output data."""
    id: str
    name: str
    gap_type: str          # "missing", "ambiguous", "scope_boundary"
    severity: str          # "critical", "moderate", "watch"
    scope_includes_any: list[str] = []    # CSI codes — at least one must be in parsed sections
    scope_excludes_all: list[str] = []    # CSI codes — ALL must be absent for rule to fire
    spec_keywords: list[str] = []         # Keywords to find in spec content
    spec_keyword_match: str = "any"       # "any" or "all"
    title: str = ""
    description: str = ""
    recommendation: str = ""
    typical_responsibility: str = ""
    cost_impact_description: str = ""
    cost_impact_low: Optional[float] = None
    cost_impact_high: Optional[float] = None
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
            "vapor barrier", "vapor retarder", "underslab membrane",
            "moisture barrier", "ASTM E1745", "15-mil", "10-mil",
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
            "anchor bolt", "embed", "steel embed", "embed plate",
            "nelson stud", "headed stud", "base plate", "connection",
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
            "epoxy coated", "epoxy-coated", "galvanized rebar",
            "ASTM A775", "ASTM A934", "ASTM A767",
            "fusion bonded", "corrosion protection", "stainless steel rebar",
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
            "architectural concrete", "exposed concrete", "form liner",
            "board form", "board-formed", "special finish",
            "Class A finish", "Class B finish", "rubbed finish",
            "bush hammer", "sandblast finish", "concrete mockup", "sample panel",
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
            "concrete pump", "pumping", "boom pump", "line pump",
            "pump mix", "pumpable",
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
        recommendation=(
            "Include pump costs. Estimate number of pump days based on pour volumes and schedule."
        ),
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
            "cold weather", "hot weather", "winter protection",
            "heated enclosure", "thermal blanket", "hoarding",
            "ACI 306", "ACI 305", "curing temperature",
            "minimum temperature", "accelerator", "calcium chloride",
        ],
        title="Weather Protection for Concrete",
        description=(
            "Specs reference cold or hot weather concrete provisions. If the project schedule "
            "includes winter pours (Michigan — likely), budget for heated enclosures, blankets, "
            "ground thaw, accelerators, and extended curing. Hot weather provisions include ice, "
            "retarders, shade structures, and night pours."
        ),
        typical_responsibility="Concrete contractor — often carried as separate line item or allowance",
        cost_impact_description=(
            "Winter: $2–$8/SF enclosure + $500–$2,000/day heating; Hot weather: $1–$3/CY"
        ),
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
            "waterstop", "water stop", "hydrophilic",
            "PVC waterstop", "bentonite", "construction joint",
            "water-tight", "below grade waterproofing",
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
        recommendation=(
            "Add waterstop to scope. Calculate total LF of construction joints in below-grade walls."
        ),
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
            "post-tension", "post tension", "PT slab", "PT strand",
            "unbonded tendon", "bonded tendon", "stressing",
            "PTI", "post-tensioning institute",
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
        recommendation=(
            "Get PT sub quote. Include coordination effort and potential schedule impact in your scope."
        ),
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
            "concrete testing", "compressive strength test", "cylinder", "slump test",
            "air content", "field testing", "special inspection", "third party testing",
            "Section 01 45", "Section 01 40",
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
            "6000 psi", "7000 psi", "8000 psi", "10000 psi",
            "high strength", "high-strength", "high performance",
            "self-consolidating", "SCC", "low heat",
            "supplementary cementitious", "fly ash", "slag cement",
            "silica fume", "GGBFS",
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
            "mechanical splice", "coupler", "mechanical coupler", "cadweld",
            "headed bar", "headed rebar", "ASTM A1034",
            "Type 1 splice", "Type 2 splice",
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
        recommendation=(
            "Count splices on drawings. Get supplier quote for specific coupler type and bar sizes."
        ),
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
            "saw cut", "sawcut", "control joint", "contraction joint",
            "joint spacing", "joint layout", "slab joint",
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
        recommendation=(
            "Calculate total LF of sawcuts based on joint spacing and slab area. Include in scope."
        ),
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
            "wet cure", "wet curing", "7-day cure", "14-day cure",
            "moist cure", "ponding", "burlap", "curing blanket",
            "curing compound", "membrane curing", "extended curing",
            "ASTM C309", "ASTM C171",
        ],
        title="Special Curing Beyond Standard",
        description=(
            "Specs call for extended or special curing methods beyond standard spray-on curing "
            "compound. Wet curing, burlap, ponding, or extended cure periods add significant labor "
            "cost and can impact the schedule. Verify curing requirements for each concrete element."
        ),
        typical_responsibility="Concrete contractor",
        cost_impact_description=(
            "Standard cure: $0.10–$0.20/SF; Wet cure: $0.50–$1.50/SF; Extended: +$/day"
        ),
        cost_impact_low=0.10,
        cost_impact_high=1.50,
        recommendation=(
            "Identify elements requiring special curing. Add labor for daily wet cure maintenance."
        ),
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
            "fiber reinforcement", "steel fiber", "synthetic fiber",
            "macro fiber", "micro fiber", "polypropylene fiber",
            "fiber dosage", "fibers per cubic yard",
        ],
        title="Fiber Reinforcement Required",
        description=(
            "Specs call for fiber reinforcement in concrete, but fiber reinforcement is not in your "
            "scope. Fiber is typically added at the batch plant and is either a ready-mix add charge "
            "or furnished by the contractor. Verify type, dosage, and responsibility."
        ),
        typical_responsibility="Usually specified as ready-mix additive; contractor pays upcharge",
        cost_impact_description=(
            "Micro synthetic: $3–$6/CY; Macro synthetic: $8–$15/CY; Steel: $20–$45/CY"
        ),
        cost_impact_low=3,
        cost_impact_high=45,
        recommendation=(
            "Get ready-mix pricing with fiber dosage. May replace or supplement WWR — verify."
        ),
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
            "reshoring", "reshore", "shoring plan", "stripping time",
            "minimum strip time", "shore removal", "backshore",
            "28-day strength", "75% strength",
        ],
        title="Reshoring & Formwork Stripping Requirements",
        description=(
            "Elevated concrete is in scope. Verify reshoring requirements per the structural "
            "engineer's shoring plan. Multiple levels of reshoring can significantly increase "
            "form/shore material requirements and tie up equipment longer than planned. Extended "
            "strip times affect schedule."
        ),
        typical_responsibility="Concrete contractor per structural engineer's shoring plan",
        cost_impact_description=(
            "Each additional level of reshoring: $1.50–$3.00/SF; Extended strip: schedule impact"
        ),
        cost_impact_low=1.50,
        cost_impact_high=3.00,
        recommendation=(
            "Get or develop shoring plan early. Price reshoring materials and extended rental."
        ),
        affected_csi_codes=["03 11 05"],
    ),
]

# CIV-001 through CIV-010 added after that

CIVIL_GAP_RULES: list[DomainGapRule] = []  # Populated by next spec

ALL_DOMAIN_RULES: list[DomainGapRule] = CONCRETE_GAP_RULES + CIVIL_GAP_RULES
