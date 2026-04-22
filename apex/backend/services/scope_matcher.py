"""Scope Matcher — Agent 3.5 (Sprint 18.3.2).

Cross-references a project's takeoff line items against the WorkCategories
published by the CM (parsed in Sprint 18.1 by Agent 2B). Emits GapFinding
rows flagging two classes of risk:

  - estimated_out_of_scope: a takeoff line item does not fall under any WC.
    The estimator is pricing work the CM assigned to a different trade.
  - in_scope_not_estimated: a WC inclusion has no matching takeoff line item.
    The estimator missed scope that belongs in this bid package.
  - partial_coverage: low-confidence LLM match (< 0.75) — flag for review.

Three-tier waterfall per line item:
  Tier 1  csi_exact           WC.referenced_spec_sections (6-digit normalized)
                              vs EstimateLineItem.csi_code normalized. Division
                              prefix OR exact 6-digit match.
  Tier 2  spec_section_fuzzy  SequenceMatcher.ratio() against (WC.title +
                              work_included_items). Threshold 0.6.
  Tier 3  llm_semantic        Single batch call to the Agent-3.5 LLM for
                              everything still unmatched. Skipped when the
                              provider is unreachable — findings for those
                              line items fall through to out_of_scope with
                              source="rule".

The returned list is NOT committed — the caller owns the transaction so
orchestration can roll back alongside the AgentRunLog on failure.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from apex.backend.models.estimate import Estimate, EstimateLineItem
from apex.backend.models.gap_finding import GapFinding
from apex.backend.models.work_category import WorkCategory
from apex.backend.services.work_scope_parser import normalize_csi_code

logger = logging.getLogger(__name__)

FUZZY_THRESHOLD = 0.6
LLM_UNCERTAIN_THRESHOLD = 0.75


# ---------------------------------------------------------------------------
# Internal match records (not persisted — only feed the finding emitter)
# ---------------------------------------------------------------------------


@dataclass
class _MatchRecord:
    line_item_id: int
    work_category_id: int
    tier: str  # "csi_exact" | "spec_section_fuzzy" | "llm_semantic"
    confidence: float
    spec_section_ref: str | None
    source: str  # "rule" | "llm"
    rationale: str


# ---------------------------------------------------------------------------
# Tier 1 — CSI exact match
# ---------------------------------------------------------------------------


def _tier1_csi_match(
    line_item: EstimateLineItem,
    work_categories: list[WorkCategory],
) -> _MatchRecord | None:
    """Match a line item to a WC by CSI code.

    Strategy: normalize line_item.csi_code to 6-digit. For each WC, check
    its referenced_spec_sections:
      - exact 6-digit equality → confidence 1.0
      - first-2-digit (division) prefix equality → confidence 0.9
    The WC is picked by best (highest-confidence) match; ties broken by
    first-encountered order (stable under WC creation order).
    """
    li_code = normalize_csi_code(line_item.csi_code)
    if not li_code:
        return None
    li_division = li_code[:2]

    best: tuple[WorkCategory, float, str] | None = None

    for wc in work_categories:
        refs = wc.referenced_spec_sections or []
        for ref in refs:
            ref_norm = normalize_csi_code(ref)
            if not ref_norm:
                continue
            if ref_norm == li_code:
                return _MatchRecord(
                    line_item_id=line_item.id,
                    work_category_id=wc.id,
                    tier="csi_exact",
                    confidence=1.0,
                    spec_section_ref=ref_norm,
                    source="rule",
                    rationale=(
                        f"Line item CSI {li_code} matches WC {wc.wc_number} "
                        f"referenced spec section {ref_norm}."
                    ),
                )
            if ref_norm[:2] == li_division:
                candidate = (wc, 0.9, ref_norm)
                if best is None or candidate[1] > best[1]:
                    best = candidate

    if best is not None:
        wc, conf, ref_norm = best
        return _MatchRecord(
            line_item_id=line_item.id,
            work_category_id=wc.id,
            tier="csi_exact",
            confidence=conf,
            spec_section_ref=ref_norm,
            source="rule",
            rationale=(
                f"Line item division {li_division} matches WC {wc.wc_number} "
                f"division prefix (referenced section {ref_norm})."
            ),
        )
    return None


# ---------------------------------------------------------------------------
# Tier 2 — Fuzzy string match on WC title + work_included_items
# ---------------------------------------------------------------------------


def _tier2_fuzzy_match(
    line_item: EstimateLineItem,
    work_categories: list[WorkCategory],
) -> _MatchRecord | None:
    """Fuzzy-match line_item.description against each WC's title joined with
    its work_included_items prose. Returns the best match above FUZZY_THRESHOLD.

    Matches against the UNION of title + work_included_items — title catches
    cases where a WC has a clear category name ("Structural Concrete") but no
    populated referenced_spec_sections, and work_included_items catches the
    detailed prose inclusions.
    """
    desc = (line_item.description or "").lower().strip()
    if not desc:
        return None

    best: tuple[WorkCategory, float] | None = None
    for wc in work_categories:
        title = (wc.title or "").lower()
        inclusions = " ".join(wc.work_included_items or []).lower()
        haystack = f"{title} {inclusions}".strip()
        if not haystack:
            continue
        ratio = SequenceMatcher(None, desc, haystack).ratio()
        if ratio >= FUZZY_THRESHOLD and (best is None or ratio > best[1]):
            best = (wc, ratio)

    if best is None:
        return None
    wc, ratio = best
    return _MatchRecord(
        line_item_id=line_item.id,
        work_category_id=wc.id,
        tier="spec_section_fuzzy",
        confidence=ratio,
        spec_section_ref=None,
        source="rule",
        rationale=(
            f"Line item description fuzzy-matched WC {wc.wc_number} "
            f"({wc.title}) at ratio {ratio:.2f}."
        ),
    )


# ---------------------------------------------------------------------------
# Tier 3 — LLM semantic batch match
# ---------------------------------------------------------------------------

_TIER3_SYSTEM_PROMPT = (
    "You are a construction estimating scope matcher. Given a list of takeoff "
    "line items and a list of bid work categories (WC), decide which WC each "
    "line item belongs to based on the WC's title and inclusions.\n\n"
    "Return a JSON array ONLY (no prose, no markdown fences) with one object "
    "per line item:\n"
    '[{"line_item_id": <int>, "work_category_id": <int or null>, '
    '"confidence": <float 0.0-1.0>, "reason": "<brief>"}]\n\n'
    "Rules:\n"
    "- Match only if the line item's work clearly falls under the WC's "
    "inclusions.\n"
    "- Use null for work_category_id if no WC fits.\n"
    "- Confidence reflects how certain you are (0.75+ = strong, "
    "0.5-0.74 = tentative, <0.5 = weak)."
)


def _build_tier3_user_prompt(
    line_items: list[EstimateLineItem],
    work_categories: list[WorkCategory],
) -> str:
    wc_lines = []
    for wc in work_categories:
        inc_preview = "; ".join((wc.work_included_items or [])[:3])
        wc_lines.append(
            f"WC {wc.id} [{wc.wc_number}] {wc.title} :: {inc_preview}"
        )
    li_lines = []
    for li in line_items:
        li_lines.append(
            f"LI {li.id} [{li.csi_code}] {li.description}"
        )
    return (
        "WORK CATEGORIES:\n"
        + "\n".join(wc_lines)
        + "\n\nLINE ITEMS:\n"
        + "\n".join(li_lines)
    )


def _parse_tier3_response(raw: str) -> list[dict]:
    """Extract the JSON array from the LLM response. Tolerant of code fences."""
    if not raw:
        return []
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if not m:
        return []
    try:
        parsed = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _tier3_llm_match(
    line_items: list[EstimateLineItem],
    work_categories: list[WorkCategory],
    llm_provider,
) -> dict[int, _MatchRecord]:
    """Single batch LLM call mapping line_item_id -> _MatchRecord.

    Line items that the LLM maps to work_category_id=null do NOT appear in
    the result dict — they're surfaced as estimated_out_of_scope findings
    by the caller.
    """
    from apex.backend.utils.async_helper import run_async

    if not line_items or not work_categories:
        return {}

    user_prompt = _build_tier3_user_prompt(line_items, work_categories)

    try:
        response = run_async(
            llm_provider.complete(
                system_prompt=_TIER3_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.0,
                max_tokens=2048,
            )
        )
    except Exception as exc:
        logger.warning(f"Agent 3.5 Tier 3 LLM call failed: {exc}")
        return {}

    items = _parse_tier3_response(response.content)
    wc_by_id = {wc.id: wc for wc in work_categories}
    li_by_id = {li.id: li for li in line_items}

    matches: dict[int, _MatchRecord] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        li_id = item.get("line_item_id")
        wc_id = item.get("work_category_id")
        conf = item.get("confidence")
        reason = item.get("reason") or ""
        if not isinstance(li_id, int) or li_id not in li_by_id:
            continue
        if wc_id is None:
            continue
        if not isinstance(wc_id, int) or wc_id not in wc_by_id:
            continue
        try:
            conf_val = float(conf)
        except (TypeError, ValueError):
            continue
        conf_val = max(0.0, min(1.0, conf_val))
        matches[li_id] = _MatchRecord(
            line_item_id=li_id,
            work_category_id=wc_id,
            tier="llm_semantic",
            confidence=conf_val,
            spec_section_ref=None,
            source="llm",
            rationale=(
                f"LLM matched line item to WC {wc_by_id[wc_id].wc_number} "
                f"with confidence {conf_val:.2f}: {reason.strip()[:240]}"
            ),
        )
    return matches


# ---------------------------------------------------------------------------
# Exclusion detection (ERROR findings)
# ---------------------------------------------------------------------------


def _detect_exclusion_conflict(
    line_item: EstimateLineItem,
    work_category: WorkCategory,
) -> str | None:
    """If the line item's description overlaps with one of the WC's
    related_work_by_others entries, return the offending exclusion text.
    Used to raise ERROR-severity findings for scope conflicts.
    """
    exclusions = work_category.related_work_by_others or []
    if not exclusions:
        return None
    desc = (line_item.description or "").lower().strip()
    if not desc:
        return None
    for excl in exclusions:
        if not isinstance(excl, str):
            continue
        excl_norm = excl.lower().strip()
        if not excl_norm:
            continue
        ratio = SequenceMatcher(None, desc, excl_norm).ratio()
        if ratio >= FUZZY_THRESHOLD:
            return excl
    return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def match_scope_to_takeoff(
    project_id: int,
    db: Session,
) -> list[GapFinding]:
    """Cross-reference takeoff line items against published WorkCategories.

    Returns a list of GapFinding rows — NOT yet added to the session. The
    caller commits so orchestration can control the transaction boundary.

    Empty list is returned (not an error) when the project has no line
    items or no WorkCategories — Agent 3.5 has nothing to flag.
    """
    latest_estimate = (
        db.query(Estimate)
        .filter(Estimate.project_id == project_id)
        .order_by(Estimate.version.desc(), Estimate.id.desc())
        .first()
    )
    if latest_estimate is None:
        logger.info(
            f"Agent 3.5: project {project_id} has no estimate — nothing to match"
        )
        return []
    line_items: list[EstimateLineItem] = list(latest_estimate.line_items)

    work_categories: list[WorkCategory] = (
        db.query(WorkCategory)
        .filter(WorkCategory.project_id == project_id)
        .all()
    )
    if not work_categories:
        logger.info(
            f"Agent 3.5: project {project_id} has no WorkCategories — "
            "scope matching skipped"
        )
        return []
    if not line_items:
        logger.info(
            f"Agent 3.5: project {project_id} has no line items — "
            "emitting in_scope_not_estimated for every WC inclusion"
        )

    # ------------------------------------------------------------------
    # Pass 1: deterministic tiers (1 and 2) per line item
    # ------------------------------------------------------------------
    matches: dict[int, _MatchRecord] = {}
    unmatched: list[EstimateLineItem] = []
    for li in line_items:
        tier1 = _tier1_csi_match(li, work_categories)
        if tier1 is not None:
            matches[li.id] = tier1
            continue
        tier2 = _tier2_fuzzy_match(li, work_categories)
        if tier2 is not None:
            matches[li.id] = tier2
            continue
        unmatched.append(li)

    # ------------------------------------------------------------------
    # Pass 2: Tier 3 LLM batch (best-effort — skip silently if unavailable)
    # ------------------------------------------------------------------
    llm_used = False
    if unmatched:
        try:
            from apex.backend.services.llm_provider import get_llm_provider
            from apex.backend.utils.async_helper import run_async

            provider = get_llm_provider(agent_number=35)
            if run_async(provider.health_check()):
                llm_used = True
                tier3_matches = _tier3_llm_match(unmatched, work_categories, provider)
                matches.update(tier3_matches)
            else:
                logger.info(
                    "Agent 3.5: LLM provider unreachable — Tier 3 skipped, "
                    "unmatched line items will surface as out_of_scope findings"
                )
        except Exception as exc:
            logger.warning(
                f"Agent 3.5: Tier 3 LLM setup failed ({exc}) — continuing "
                "with deterministic tiers only"
            )

    # ------------------------------------------------------------------
    # Emit findings
    # ------------------------------------------------------------------
    findings: list[GapFinding] = []
    wc_by_id = {wc.id: wc for wc in work_categories}

    # --- estimated_out_of_scope for line items with no match after 3 tiers
    for li in line_items:
        if li.id in matches:
            continue
        findings.append(
            GapFinding(
                project_id=project_id,
                finding_type="estimated_out_of_scope",
                work_category_id=None,
                estimate_line_id=li.id,
                spec_section_ref=normalize_csi_code(li.csi_code),
                match_tier="llm_semantic" if llm_used else "spec_section_fuzzy",
                confidence=0.0,
                rationale=(
                    f"Line item '{li.description}' (CSI {li.csi_code}) did not "
                    "match any published WorkCategory after CSI, fuzzy, and "
                    "LLM tiers. Estimator may be pricing out-of-scope work."
                ),
                source="llm" if llm_used else "rule",
                severity="WARNING",
            )
        )

    # --- partial_coverage INFO for low-confidence LLM matches
    for li_id, rec in matches.items():
        if rec.tier == "llm_semantic" and rec.confidence < LLM_UNCERTAIN_THRESHOLD:
            findings.append(
                GapFinding(
                    project_id=project_id,
                    finding_type="partial_coverage",
                    work_category_id=rec.work_category_id,
                    estimate_line_id=li_id,
                    spec_section_ref=rec.spec_section_ref,
                    match_tier=rec.tier,
                    confidence=rec.confidence,
                    rationale=(
                        "Low-confidence LLM match — please verify. "
                        + rec.rationale
                    ),
                    source=rec.source,
                    severity="INFO",
                )
            )

    # --- ERROR for exclusion conflicts (matched WC explicitly excludes this work)
    for li in line_items:
        rec = matches.get(li.id)
        if rec is None:
            continue
        wc = wc_by_id.get(rec.work_category_id)
        if wc is None:
            continue
        excl_hit = _detect_exclusion_conflict(li, wc)
        if excl_hit is None:
            continue
        findings.append(
            GapFinding(
                project_id=project_id,
                finding_type="estimated_out_of_scope",
                work_category_id=wc.id,
                estimate_line_id=li.id,
                spec_section_ref=rec.spec_section_ref,
                match_tier=rec.tier,
                confidence=rec.confidence,
                rationale=(
                    f"Line item '{li.description}' matches WC {wc.wc_number} "
                    f"scope, but that WC explicitly excludes: '{excl_hit}'. "
                    "This work is assigned to another trade — remove from estimate."
                ),
                source=rec.source,
                severity="ERROR",
            )
        )

    # --- in_scope_not_estimated for WC inclusions with no matched line items
    matched_wc_ids = {rec.work_category_id for rec in matches.values()}
    for wc in work_categories:
        if wc.id in matched_wc_ids:
            continue
        inclusions = wc.work_included_items or []
        for inclusion in inclusions:
            if not isinstance(inclusion, str) or not inclusion.strip():
                continue
            primary_ref = None
            refs = wc.referenced_spec_sections or []
            if refs:
                primary_ref = normalize_csi_code(refs[0])
            findings.append(
                GapFinding(
                    project_id=project_id,
                    finding_type="in_scope_not_estimated",
                    work_category_id=wc.id,
                    estimate_line_id=None,
                    spec_section_ref=primary_ref,
                    match_tier="csi_exact" if primary_ref else "spec_section_fuzzy",
                    confidence=1.0,
                    rationale=(
                        f"WC {wc.wc_number} ({wc.title}) inclusion "
                        f"'{inclusion.strip()}' has no matching takeoff line "
                        "item. Estimator missed this scope."
                    ),
                    source="rule",
                    severity="WARNING",
                )
            )

    logger.info(
        f"Agent 3.5: project {project_id} — {len(line_items)} line items, "
        f"{len(work_categories)} WCs, {len(matches)} matches, "
        f"{len(findings)} findings emitted"
    )
    return findings
