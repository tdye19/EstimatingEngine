"""Sprint 18.4.2 — ProposalForm builder tests.

Covers:
- None-return when input data is insufficient (no WCs / no takeoff)
- base_bid arithmetic (exact dollar totals from seeded data)
- Grouping by WorkCategory via LineItemWCAttribution
- Unattributed bucket population (work_category_id IS NULL)
- alternates / allowances / unit_prices / breakout_notes population
- 0.0 treated as null in allowances.amount and unit_prices.rate (Refinement 2)
- Warning generation with stable uppercase prefixes (greppability invariant)
- End-to-end through run_assembly_agent: proposal_form_json on IntelligenceReportModel
"""

from __future__ import annotations

import json
import uuid

from sqlalchemy.orm import Session

from apex.backend.agents.agent_6_assembly import run_assembly_agent
from apex.backend.agents.proposal_form_builder import (
    WARN_ALLOWANCES_NO_AMOUNT,
    WARN_ALTERNATES_NO_PRICE,
    WARN_UNATTRIBUTED_ITEMS,
    WARN_UNIT_PRICES_PLACEHOLDER,
    WARN_WC_EMPTY,
    WARNING_PREFIXES,
    build_proposal_form,
)
from apex.backend.models.intelligence_report import IntelligenceReportModel
from apex.backend.models.line_item_wc_attribution import LineItemWCAttribution
from apex.backend.models.project import Project
from apex.backend.models.takeoff_v2 import TakeoffItemV2
from apex.backend.models.work_category import WorkCategory

# ---------------------------------------------------------------------------
# Scaffolding
# ---------------------------------------------------------------------------


def _project(db: Session, tag: str = "x") -> Project:
    suffix = uuid.uuid4().hex[:8]
    p = Project(
        name=f"S1842 {tag}",
        project_number=f"S1842-{tag}-{suffix}",
        project_type="commercial",
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _wc(
    db: Session,
    project: Project,
    *,
    wc_number: str,
    title: str,
    alternates: list[dict] | None = None,
    allowances: list[dict] | None = None,
    unit_prices: list[dict] | None = None,
    specific_notes: list[str] | None = None,
) -> WorkCategory:
    wc = WorkCategory(
        project_id=project.id,
        wc_number=wc_number,
        title=title,
        work_included_items=[],
        specific_notes=specific_notes or [],
        related_work_by_others=[],
        add_alternates=alternates or [],
        allowances=allowances or [],
        unit_prices=unit_prices or [],
        referenced_spec_sections=[],
    )
    db.add(wc)
    db.commit()
    db.refresh(wc)
    return wc


def _takeoff(
    db: Session,
    project: Project,
    *,
    row_number: int,
    activity: str,
    quantity: float,
    labor: float,
    material: float,
) -> TakeoffItemV2:
    t = TakeoffItemV2(
        project_id=project.id,
        row_number=row_number,
        activity=activity,
        quantity=quantity,
        unit="EA",
        labor_cost_per_unit=labor,
        material_cost_per_unit=material,
        csi_code="03 30 00",
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _attribute(
    db: Session,
    project: Project,
    takeoff_item: TakeoffItemV2,
    *,
    work_category: WorkCategory | None = None,
    confidence: float = 1.0,
) -> LineItemWCAttribution:
    a = LineItemWCAttribution(
        project_id=project.id,
        takeoff_item_id=takeoff_item.id,
        work_category_id=work_category.id if work_category else None,
        match_tier="csi_exact" if work_category else "unmatched",
        confidence=confidence if work_category else 0.0,
        source="rule",
        rationale="test",
    )
    db.add(a)
    db.commit()
    return a


# ---------------------------------------------------------------------------
# 1. None-return paths
# ---------------------------------------------------------------------------


def test_proposal_form_empty_when_no_work_categories(db_session: Session):
    project = _project(db_session, "no-wcs")
    # Seed takeoff so the no-takeoff branch isn't what we're testing.
    _takeoff(db_session, project, row_number=1, activity="x", quantity=1, labor=1.0, material=1.0)

    assert build_proposal_form(db_session, project.id) is None


def test_proposal_form_empty_when_no_takeoff_items(db_session: Session):
    project = _project(db_session, "no-takeoff")
    _wc(db_session, project, wc_number="WC 05", title="Site Concrete")

    assert build_proposal_form(db_session, project.id) is None


# ---------------------------------------------------------------------------
# 2. base_bid arithmetic — exact dollar totals
# ---------------------------------------------------------------------------


def test_proposal_form_base_bid_arithmetic(db_session: Session):
    project = _project(db_session, "arith")
    wc_a = _wc(db_session, project, wc_number="WC 05", title="Site Concrete")
    wc_b = _wc(db_session, project, wc_number="WC 09", title="Finishes")

    # WC A items: subtotals 35 + 30 + 30 = 95 (labor 65 / material 30)
    items_a = [
        _takeoff(db_session, project, row_number=1, activity="a1", quantity=10, labor=2.50, material=1.00),
        _takeoff(db_session, project, row_number=2, activity="a2", quantity=5, labor=4.00, material=2.00),
        _takeoff(db_session, project, row_number=3, activity="a3", quantity=2, labor=10.00, material=5.00),
    ]
    for t in items_a:
        _attribute(db_session, project, t, work_category=wc_a)

    # WC B items: subtotals 150 + 90 = 240 (labor 160 / material 80)
    items_b = [
        _takeoff(db_session, project, row_number=4, activity="b1", quantity=1, labor=100.00, material=50.00),
        _takeoff(db_session, project, row_number=5, activity="b2", quantity=4, labor=15.00, material=7.50),
    ]
    for t in items_b:
        _attribute(db_session, project, t, work_category=wc_b)

    pf = build_proposal_form(db_session, project.id)
    assert pf is not None
    by_wc = {row["wc_number"]: row for row in pf["base_bid"]["by_work_category"]}

    assert by_wc["WC 05"]["labor_cost"] == 65.00
    assert by_wc["WC 05"]["material_cost"] == 30.00
    assert by_wc["WC 05"]["subtotal"] == 95.00
    assert by_wc["WC 05"]["line_items_count"] == 3
    assert by_wc["WC 05"]["attribution_confidence_avg"] == 1.0

    assert by_wc["WC 09"]["labor_cost"] == 160.00
    assert by_wc["WC 09"]["material_cost"] == 80.00
    assert by_wc["WC 09"]["subtotal"] == 240.00

    # No unattributed bucket (all attributed) and total = 95 + 240 = 335.
    assert pf["base_bid"]["unattributed"] is None
    assert pf["base_bid"]["total"] == 335.00


# ---------------------------------------------------------------------------
# 3. Grouping verifies WC ordering + presence of empties
# ---------------------------------------------------------------------------


def test_proposal_form_groups_by_wc_via_attribution(db_session: Session):
    """Every WorkCategory appears in by_work_category — including ones with
    no attributed items (Refinement 3). Ordering follows wc_number sort."""
    project = _project(db_session, "group")
    wc_05 = _wc(db_session, project, wc_number="WC 05", title="Site Concrete")
    # WC 06 is seeded but intentionally left empty — it must still appear
    # in by_work_category with zero subtotal and confidence=None.
    _wc(db_session, project, wc_number="WC 06", title="Empty Category")
    wc_09 = _wc(db_session, project, wc_number="WC 09", title="Finishes")

    t1 = _takeoff(db_session, project, row_number=1, activity="a", quantity=1, labor=10, material=5)
    t2 = _takeoff(db_session, project, row_number=2, activity="b", quantity=2, labor=20, material=10)
    _attribute(db_session, project, t1, work_category=wc_05, confidence=0.85)
    _attribute(db_session, project, t2, work_category=wc_09, confidence=0.95)

    pf = build_proposal_form(db_session, project.id)
    assert pf is not None
    by_wc = pf["base_bid"]["by_work_category"]

    # All 3 WCs appear, in wc_number order. Empty WC 06 has zero subtotal
    # and attribution_confidence_avg=None (Refinement 3).
    assert [row["wc_number"] for row in by_wc] == ["WC 05", "WC 06", "WC 09"]
    empty_row = next(row for row in by_wc if row["wc_number"] == "WC 06")
    assert empty_row["line_items_count"] == 0
    assert empty_row["subtotal"] == 0.0
    assert empty_row["attribution_confidence_avg"] is None

    # Confidence average for non-empty WCs reflects only their own items.
    wc05_row = next(row for row in by_wc if row["wc_number"] == "WC 05")
    assert wc05_row["attribution_confidence_avg"] == 0.85


# ---------------------------------------------------------------------------
# 4. Unattributed bucket
# ---------------------------------------------------------------------------


def test_proposal_form_captures_unattributed_items(db_session: Session):
    project = _project(db_session, "unattr")
    wc = _wc(db_session, project, wc_number="WC 05", title="Site Concrete")

    matched = _takeoff(db_session, project, row_number=1, activity="m", quantity=1, labor=10, material=5)
    _attribute(db_session, project, matched, work_category=wc)

    unmatched_1 = _takeoff(db_session, project, row_number=2, activity="u1", quantity=2, labor=20, material=10)
    unmatched_2 = _takeoff(db_session, project, row_number=3, activity="u2", quantity=2, labor=20, material=10)
    _attribute(db_session, project, unmatched_1, work_category=None)
    _attribute(db_session, project, unmatched_2, work_category=None)

    pf = build_proposal_form(db_session, project.id)
    assert pf is not None

    unattr = pf["base_bid"]["unattributed"]
    assert unattr is not None
    assert unattr["line_items_count"] == 2
    # Each unmatched item: 2 * 20 + 2 * 10 = 60. Two of them = 120.
    assert unattr["subtotal"] == 120.0
    assert unattr["labor_cost"] == 80.0
    assert unattr["material_cost"] == 40.0
    assert "no matching WorkCategory" in unattr["note"]

    # Total = matched (15) + unattributed (120) = 135.
    assert pf["base_bid"]["total"] == 135.0


# ---------------------------------------------------------------------------
# 5. Alternates / allowances / unit_prices / breakout_notes from WC data
# ---------------------------------------------------------------------------


def test_proposal_form_surfaces_alternates_allowances_unit_prices(db_session: Session):
    project = _project(db_session, "wc-extras")
    wc = _wc(
        db_session,
        project,
        wc_number="WC 02",
        title="Earthwork",
        alternates=[
            {"description": "Add colored concrete", "price_type": "add"},
            {"description": "Deduct entry walkway", "price_type": "deduct"},
        ],
        allowances=[
            {"description": "CM allowance", "amount_dollars": 40000.0},
            {"description": "Placeholder allowance", "amount_dollars": 0.0},  # treated as null
            {"description": "Missing allowance", "amount_dollars": None},
        ],
        unit_prices=[
            {"description": "Concrete pour", "unit": "CY", "rate": 15.50},
            {"description": "Placeholder unit price", "unit": "various", "rate": 0.0},
        ],
        specific_notes=[
            "Breakout cost on proposal form for any additional unforeseen excavation",
            "General specific note that should be ignored by the breakout regex",
            "Provide NTE budget of $5000 for testing",
        ],
    )
    # Need at least one takeoff item so build_proposal_form doesn't return None.
    t = _takeoff(db_session, project, row_number=1, activity="a", quantity=1, labor=10, material=5)
    _attribute(db_session, project, t, work_category=wc)

    pf = build_proposal_form(db_session, project.id)
    assert pf is not None

    # Alternates: 2 entries, both amount=None (model has no amount field).
    assert len(pf["alternates"]) == 2
    assert all(alt["amount"] is None for alt in pf["alternates"])
    assert pf["alternates"][0]["price_type"] == "add"
    assert pf["alternates"][1]["price_type"] == "deduct"

    # Allowances: real 40000, placeholder 0.0 → null, missing → null.
    by_desc = {a["description"]: a for a in pf["allowances"]}
    assert by_desc["CM allowance"]["amount"] == 40000.0
    assert by_desc["Placeholder allowance"]["amount"] is None
    assert by_desc["Missing allowance"]["amount"] is None

    # Unit prices: real 15.50, placeholder 0.0 → null.
    up_by_desc = {u["description"]: u for u in pf["unit_prices"]}
    assert up_by_desc["Concrete pour"]["rate"] == 15.50
    assert up_by_desc["Concrete pour"]["unit"] == "CY"
    assert up_by_desc["Placeholder unit price"]["rate"] is None

    # breakout_notes: regex catches "Breakout cost on proposal form" and "NTE budget".
    descs = [b["description"] for b in pf["breakout_notes"]]
    assert any("Breakout cost on proposal form" in d for d in descs)
    assert any("NTE budget" in d for d in descs)
    assert all("ignored by the breakout regex" not in d for d in descs)
    assert len(pf["breakout_notes"]) == 2


# ---------------------------------------------------------------------------
# 6. Warnings generation
# ---------------------------------------------------------------------------


def test_proposal_form_warnings_flag_data_quality_issues(db_session: Session):
    project = _project(db_session, "warns")
    # Two WCs: one will have items, one will be empty (→ WC_EMPTY).
    wc_a = _wc(
        db_session,
        project,
        wc_number="WC 05",
        title="Site Concrete",
        alternates=[{"description": "alt 1", "price_type": "add"}],
        allowances=[{"description": "missing $$", "amount_dollars": None}],
        unit_prices=[{"description": "placeholder", "unit": "EA", "rate": 0.0}],
    )
    _wc(db_session, project, wc_number="WC 06", title="Empty Category")

    # Two takeoff items: one attributed, one unattributed.
    t_attr = _takeoff(db_session, project, row_number=1, activity="a", quantity=1, labor=10, material=5)
    _attribute(db_session, project, t_attr, work_category=wc_a)
    t_unattr = _takeoff(db_session, project, row_number=2, activity="u", quantity=1, labor=20, material=10)
    _attribute(db_session, project, t_unattr, work_category=None)

    pf = build_proposal_form(db_session, project.id)
    assert pf is not None
    warnings = pf["warnings"]

    # Each warning category must surface exactly once for this scenario.
    assert any(WARN_UNATTRIBUTED_ITEMS in w and "1/2" in w for w in warnings)
    assert any(WARN_ALTERNATES_NO_PRICE in w and "1 alternate" in w for w in warnings)
    assert any(WARN_UNIT_PRICES_PLACEHOLDER in w and "1 unit price" in w for w in warnings)
    assert any(WARN_ALLOWANCES_NO_AMOUNT in w and "1 allowance" in w for w in warnings)
    assert any(WARN_WC_EMPTY in w and "WC 06" in w for w in warnings)


# ---------------------------------------------------------------------------
# 7. Stable warning prefixes (Tucker amendment)
# ---------------------------------------------------------------------------


def test_proposal_form_warnings_use_stable_prefixes(db_session: Session):
    """Every emitted warning must begin with one of the WARNING_PREFIXES
    tokens followed by ": ". Pins the greppable-prefix invariant so
    downstream tools (18.4.3 Excel render, future UI, log analysis) can
    parse warnings without regex churn."""
    project = _project(db_session, "prefix")
    wc = _wc(
        db_session,
        project,
        wc_number="WC 05",
        title="Site Concrete",
        alternates=[{"description": "alt", "price_type": "add"}],
        allowances=[{"description": "x", "amount_dollars": None}],
        unit_prices=[{"description": "y", "unit": "EA", "rate": 0.0}],
    )
    _wc(db_session, project, wc_number="WC 06", title="Empty")
    t = _takeoff(db_session, project, row_number=1, activity="a", quantity=1, labor=10, material=5)
    _attribute(db_session, project, t, work_category=wc)
    t_unattr = _takeoff(db_session, project, row_number=2, activity="u", quantity=1, labor=20, material=10)
    _attribute(db_session, project, t_unattr, work_category=None)

    pf = build_proposal_form(db_session, project.id)
    assert pf is not None
    warnings = pf["warnings"]
    assert warnings, "expected at least one warning for this scenario"

    for w in warnings:
        prefix, _, _ = w.partition(":")
        assert prefix in WARNING_PREFIXES, (
            f"warning {w!r} starts with {prefix!r}, "
            f"not one of the stable prefixes {sorted(WARNING_PREFIXES)}"
        )


# ---------------------------------------------------------------------------
# 8. End-to-end via Agent 6 — proposal_form_json persisted on the report
# ---------------------------------------------------------------------------


def test_agent_6_intelligence_report_includes_proposal_form(db_session: Session):
    project = _project(db_session, "e2e")
    wc = _wc(db_session, project, wc_number="WC 05", title="Site Concrete")
    t = _takeoff(db_session, project, row_number=1, activity="a", quantity=2, labor=10, material=5)
    _attribute(db_session, project, t, work_category=wc)

    result = run_assembly_agent(db_session, project.id, use_llm=False)

    report = (
        db_session.query(IntelligenceReportModel).filter_by(id=result["report_id"]).one()
    )
    assert report.proposal_form_json is not None, (
        "Agent 6 did not persist proposal_form_json"
    )
    payload = json.loads(report.proposal_form_json)
    assert payload["project_id"] == project.id
    assert payload["base_bid"]["total"] == 30.0  # 2 * 10 + 2 * 5
    assert any(
        row["wc_number"] == "WC 05" and row["subtotal"] == 30.0
        for row in payload["base_bid"]["by_work_category"]
    )
