"""ProposalForm builder — Sprint 18.4.2.

Deterministic Python module that assembles the JSON representation of a
Christman Constructors Trade Contract Proposal Form from existing DB
state. NO LLM calls. NO external IO. All dollar arithmetic in Python —
the trust boundary documented in TCA-Project-Memory.md ("LLMs handle
language; deterministic Python handles all math") must not be violated.

Inputs (per project):
  - WorkCategory rows (Agent 2B)        — alternates, allowances, unit_prices, specific_notes
  - LineItemWCAttribution rows (3.5)    — which TakeoffItemV2 attributes to which WC
  - TakeoffItemV2 rows (Agent 4)        — quantity, labor_cost_per_unit, material_cost_per_unit

Output:
  ProposalForm dict matching apex.backend.agents.pipeline_contracts.ProposalForm,
  or None when there's not enough data to produce a meaningful proposal
  (no WCs OR no takeoff items).

Sections produced (mirrors the CCI template):
  - base_bid                  by_work_category + unattributed bucket + total
  - alternates                from WorkCategory.add_alternates
  - allowances                from WorkCategory.allowances
  - unit_prices               from WorkCategory.unit_prices
  - breakout_notes            regex scan of WorkCategory.specific_notes
  - warnings                  data-quality flags with stable uppercase prefixes
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from apex.backend.models.line_item_wc_attribution import LineItemWCAttribution
from apex.backend.models.project import Project
from apex.backend.models.takeoff_v2 import TakeoffItemV2
from apex.backend.models.work_category import WorkCategory

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stable warning prefixes (UPPERCASE + colon — greppable for downstream
# tooling: 18.4.3 Excel render, future UI, log analysis).
# ---------------------------------------------------------------------------
WARN_UNATTRIBUTED_ITEMS = "UNATTRIBUTED_ITEMS"
WARN_ALTERNATES_NO_PRICE = "ALTERNATES_NO_PRICE"
WARN_UNIT_PRICES_PLACEHOLDER = "UNIT_PRICES_PLACEHOLDER"
WARN_ALLOWANCES_NO_AMOUNT = "ALLOWANCES_NO_AMOUNT"
WARN_WC_EMPTY = "WC_EMPTY"

WARNING_PREFIXES = frozenset(
    {
        WARN_UNATTRIBUTED_ITEMS,
        WARN_ALTERNATES_NO_PRICE,
        WARN_UNIT_PRICES_PLACEHOLDER,
        WARN_ALLOWANCES_NO_AMOUNT,
        WARN_WC_EMPTY,
    }
)

# Breakout / NTE language patterns scanned in WorkCategory.specific_notes.
# Compiled once. Case-insensitive. Examples that match:
#   "Breakout cost on proposal form", "NTE budget $5000",
#   "not-to-exceed amount", "not to exceed", "Breakout on proposal form".
_BREAKOUT_PATTERNS = re.compile(
    r"breakout\s+cost"
    r"|nte\s+budget"
    r"|not[-\s]to[-\s]exceed"
    r"|breakout\s+on\s+proposal\s+form",
    re.IGNORECASE,
)

UNATTRIBUTED_NOTE = (
    "Takeoff items with no matching WorkCategory — review before submission"
)


# ---------------------------------------------------------------------------
# Per-line cost arithmetic — None-safe.
# ---------------------------------------------------------------------------
def _line_costs(item: TakeoffItemV2) -> tuple[float, float]:
    """Return (labor_cost, material_cost) for a single takeoff item.
    Treats None on quantity or per-unit cost as 0.0."""
    qty = item.quantity or 0.0
    labor = qty * (item.labor_cost_per_unit or 0.0)
    material = qty * (item.material_cost_per_unit or 0.0)
    return labor, material


def _money(value: float) -> float:
    """Round to 2dp at the JSON boundary."""
    return round(value, 2)


def _avg_confidence(confidences: list[float]) -> float | None:
    """Mean of *confidences* rounded to 4dp; None when list is empty
    (Refinement 3: WCs with no attributions emit None instead of 0.0)."""
    if not confidences:
        return None
    return round(sum(confidences) / len(confidences), 4)


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------
def build_proposal_form(db: Session, project_id: int) -> dict | None:
    """Assemble the ProposalForm JSON from DB state.

    Returns None when:
      - project doesn't exist
      - project has no WorkCategory rows
      - project has no TakeoffItemV2 rows

    Caller (Agent 6) omits the proposal_form key entirely on None so
    the response stays lean when the form isn't producible.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        logger.info(
            "ProposalForm: project_id=%d not found — returning None", project_id
        )
        return None

    wcs = (
        db.query(WorkCategory)
        .filter(WorkCategory.project_id == project_id)
        .order_by(WorkCategory.wc_number)
        .all()
    )
    if not wcs:
        logger.info(
            "ProposalForm: project_id=%d has no WorkCategories — returning None",
            project_id,
        )
        return None

    takeoff_count = (
        db.query(func.count(TakeoffItemV2.id))
        .filter(TakeoffItemV2.project_id == project_id)
        .scalar()
        or 0
    )
    if takeoff_count == 0:
        logger.info(
            "ProposalForm: project_id=%d has no TakeoffItemV2 rows — returning None",
            project_id,
        )
        return None

    # Pull all takeoff items + attributions once; group in Python.
    takeoff_items = (
        db.query(TakeoffItemV2)
        .filter(TakeoffItemV2.project_id == project_id)
        .all()
    )
    takeoff_by_id: dict[int, TakeoffItemV2] = {t.id: t for t in takeoff_items}

    attributions = (
        db.query(LineItemWCAttribution)
        .filter(LineItemWCAttribution.project_id == project_id)
        .all()
    )

    # (item, confidence) tuples, grouped per attribution target.
    items_per_wc: dict[int, list[tuple[TakeoffItemV2, float]]] = defaultdict(list)
    unattributed: list[tuple[TakeoffItemV2, float]] = []
    for a in attributions:
        item = takeoff_by_id.get(a.takeoff_item_id)
        if item is None:
            # FK-cascade should make this unreachable; defensive skip if it happens.
            continue
        if a.work_category_id is None:
            unattributed.append((item, a.confidence))
        else:
            items_per_wc[a.work_category_id].append((item, a.confidence))

    # by_work_category — iterate WCs in wc_number order, include empties.
    by_wc: list[dict] = []
    for wc in wcs:
        items = items_per_wc.get(wc.id, [])
        labor_total = 0.0
        material_total = 0.0
        confidences: list[float] = []
        for item, conf in items:
            labor, material = _line_costs(item)
            labor_total += labor
            material_total += material
            if conf is not None:
                confidences.append(conf)
        by_wc.append(
            {
                "wc_number": wc.wc_number,
                "wc_title": wc.title,
                "line_items_count": len(items),
                "labor_cost": _money(labor_total),
                "material_cost": _money(material_total),
                "subtotal": _money(labor_total + material_total),
                "attribution_confidence_avg": _avg_confidence(confidences),
            }
        )

    # unattributed bucket — None when no unattributed items exist.
    unattributed_dict: dict | None = None
    if unattributed:
        labor_total = 0.0
        material_total = 0.0
        for item, _ in unattributed:
            labor, material = _line_costs(item)
            labor_total += labor
            material_total += material
        unattributed_dict = {
            "line_items_count": len(unattributed),
            "labor_cost": _money(labor_total),
            "material_cost": _money(material_total),
            "subtotal": _money(labor_total + material_total),
            "note": UNATTRIBUTED_NOTE,
        }

    # base_bid.total — explicit null-safe formula (Refinement 1).
    total = sum(wc["subtotal"] for wc in by_wc)
    if unattributed_dict is not None:
        total += unattributed_dict["subtotal"]
    base_bid = {
        "total": _money(total),
        "by_work_category": by_wc,
        "unattributed": unattributed_dict,
    }

    # alternates — WC.add_alternates has no amount field today, so amount
    # is always None. Each is surfaced as a warning.
    alternates: list[dict] = []
    for wc in wcs:
        for alt in wc.add_alternates or []:
            alternates.append(
                {
                    "wc_number": wc.wc_number,
                    "description": alt.get("description", ""),
                    "price_type": alt.get("price_type", "unknown"),
                    "amount": None,
                    "source": "work_category.add_alternates",
                }
            )

    # allowances — Refinement 2: 0.0 is treated as "not set" → null.
    allowances: list[dict] = []
    for wc in wcs:
        for allow in wc.allowances or []:
            amt = allow.get("amount_dollars")
            amount = amt if (amt is not None and amt != 0.0) else None
            allowances.append(
                {
                    "wc_number": wc.wc_number,
                    "description": allow.get("description", ""),
                    "amount": amount,
                    "source": "work_category.allowances",
                }
            )

    # unit_prices — same 0.0 == "not set" rule applied to .rate.
    unit_prices: list[dict] = []
    for wc in wcs:
        for up in wc.unit_prices or []:
            rate = up.get("rate")
            rate_val = rate if (rate is not None and rate != 0.0) else None
            unit_prices.append(
                {
                    "wc_number": wc.wc_number,
                    "description": up.get("description", ""),
                    "unit": up.get("unit", ""),
                    "rate": rate_val,
                    "source": "work_category.unit_prices",
                }
            )

    # breakout_notes — regex scan of WC.specific_notes for breakout/NTE
    # language. Mirrors what the CCI template surfaces under "Breakout / NTE".
    breakout_notes: list[dict] = []
    for wc in wcs:
        for note in wc.specific_notes or []:
            if not isinstance(note, str):
                continue
            if _BREAKOUT_PATTERNS.search(note):
                breakout_notes.append(
                    {
                        "wc_number": wc.wc_number,
                        "description": note,
                        "source": "work_category.specific_notes",
                    }
                )

    # warnings — uppercase-prefixed for downstream grep.
    warnings: list[str] = []

    n_unattr = len(unattributed)
    if n_unattr > 0:
        pct = (n_unattr / takeoff_count) * 100
        warnings.append(
            f"{WARN_UNATTRIBUTED_ITEMS}: {n_unattr}/{takeoff_count} "
            f"takeoff items unattributed ({pct:.1f}%)"
        )

    n_alts_no_price = sum(1 for a in alternates if a["amount"] is None)
    if n_alts_no_price > 0:
        s = "" if n_alts_no_price == 1 else "s"
        warnings.append(
            f"{WARN_ALTERNATES_NO_PRICE}: {n_alts_no_price} alternate{s} "
            f"have no price set"
        )

    n_up_placeholder = sum(1 for u in unit_prices if u["rate"] is None)
    if n_up_placeholder > 0:
        s = "" if n_up_placeholder == 1 else "s"
        warnings.append(
            f"{WARN_UNIT_PRICES_PLACEHOLDER}: {n_up_placeholder} unit price{s} "
            f"have placeholder rate (0.0)"
        )

    n_allow_no_amt = sum(1 for a in allowances if a["amount"] is None)
    if n_allow_no_amt > 0:
        s = "" if n_allow_no_amt == 1 else "s"
        warnings.append(
            f"{WARN_ALLOWANCES_NO_AMOUNT}: {n_allow_no_amt} allowance{s} "
            f"have no amount set"
        )

    for wc_entry in by_wc:
        if wc_entry["line_items_count"] == 0:
            warnings.append(
                f"{WARN_WC_EMPTY}: {wc_entry['wc_number']} has no attributed "
                "takeoff items"
            )

    proposal_dict = {
        "project_id": project_id,
        "project_name": project.name,
        "generated_at": datetime.now(UTC).isoformat(),
        "base_bid": base_bid,
        "alternates": alternates,
        "allowances": allowances,
        "unit_prices": unit_prices,
        "breakout_notes": breakout_notes,
        "warnings": warnings,
    }

    # Pydantic round-trip for shape validation. Imported lazily to avoid
    # circular import (pipeline_contracts isn't expected to import from
    # this module today, but the lazy form makes us robust to that).
    from apex.backend.agents.pipeline_contracts import ProposalForm

    validated = ProposalForm.model_validate(proposal_dict)
    return validated.model_dump(mode="json")
