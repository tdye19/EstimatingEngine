"""Rate matching engine — matches estimator takeoff items against
Productivity Brain historical data.

ALL MATH IS DETERMINISTIC PYTHON. No LLM touches rate data or dollar amounts.

Matching strategy (in priority order):
1. CSI code exact match (if takeoff item has csi_code)
2. Activity description fuzzy match (normalized Levenshtein similarity)
3. Unit + crew type as tiebreaker when multiple candidates match

Deviation thresholds:
- OK: abs(delta) < 5%
- REVIEW: 5% <= abs(delta) < 20%
- UPDATE: abs(delta) >= 20%
- NO_DATA: no PB match found

Confidence levels (based on sample count):
- high: n >= 10
- medium: 5 <= n < 10
- low: 1 <= n < 5
- none: n == 0
"""

import math
from difflib import SequenceMatcher

from sqlalchemy import func
from sqlalchemy.orm import Session

from apex.backend.agents.pipeline_contracts import RateRecommendation, TakeoffLineItem
from apex.backend.services.library.productivity_brain.models import PBLineItem


class RateMatchingEngine:
    """Deterministic rate matching — no LLM calls."""

    def __init__(self, db: Session):
        self.db = db
        self._pb_summary: list[dict] = self._load_pb_summary()

    # ── Data loading ─────────────────────────────────────────────────────

    def _load_pb_summary(self) -> list[dict]:
        """Query PBLineItem: GROUP BY activity, unit to build summary stats.

        Computes AVG, MIN, MAX, manual STDDEV (spread), COUNT, and collects
        DISTINCT source_project names per activity+unit group.
        """
        rows = (
            self.db.query(
                PBLineItem.activity,
                PBLineItem.unit,
                PBLineItem.crew_trade,
                PBLineItem.csi_code,
                func.avg(PBLineItem.production_rate).label("avg_rate"),
                func.min(PBLineItem.production_rate).label("min_rate"),
                func.max(PBLineItem.production_rate).label("max_rate"),
                func.count(PBLineItem.id).label("sample_count"),
                # For manual stddev: sqrt(avg(x^2) - avg(x)^2)
                func.avg(PBLineItem.production_rate * PBLineItem.production_rate).label("avg_sq"),
                func.avg(PBLineItem.labor_cost_per_unit).label("avg_labor_cost"),
                func.avg(PBLineItem.material_cost_per_unit).label("avg_mat_cost"),
            )
            .filter(
                PBLineItem.production_rate.isnot(None),
            )
            .group_by(
                PBLineItem.activity,
                PBLineItem.unit,
            )
            .all()
        )

        summaries = []
        for r in rows:
            avg = r.avg_rate or 0.0
            avg_sq = r.avg_sq or 0.0
            variance = max(avg_sq - avg * avg, 0.0)
            spread = math.sqrt(variance)

            # Collect distinct project names for this activity+unit
            projects_q = (
                self.db.query(func.distinct(PBLineItem.source_project))
                .filter(
                    PBLineItem.activity == r.activity,
                    PBLineItem.unit == r.unit,
                    PBLineItem.production_rate.isnot(None),
                    PBLineItem.source_project.isnot(None),
                )
                .all()
            )
            project_names = [p[0] for p in projects_q if p[0] and p[0] != "_averaged"]

            summaries.append(
                {
                    "activity": r.activity,
                    "unit": r.unit,
                    "crew_trade": r.crew_trade,
                    "csi_code": r.csi_code,
                    "avg_rate": round(avg, 4),
                    "min_rate": round(r.min_rate, 4) if r.min_rate is not None else None,
                    "max_rate": round(r.max_rate, 4) if r.max_rate is not None else None,
                    "spread": round(spread, 4),
                    "sample_count": r.sample_count,
                    "projects": project_names,
                    "avg_labor_cost": round(r.avg_labor_cost, 2) if r.avg_labor_cost else None,
                    "avg_mat_cost": round(r.avg_mat_cost, 2) if r.avg_mat_cost else None,
                }
            )

        return summaries

    # ── Text normalization & fuzzy matching ───────────────────────────────

    @staticmethod
    def _normalize(text: str) -> str:
        """Lowercase, strip, remove underscores/hyphens, collapse spaces."""
        t = text.lower().strip()
        t = t.replace("_", " ").replace("-", " ")
        return " ".join(t.split())

    @staticmethod
    def _fuzzy_score(a: str, b: str) -> float:
        """Similarity ratio via stdlib SequenceMatcher (0.0–1.0)."""
        return SequenceMatcher(None, a, b).ratio()

    # ── Matching logic ───────────────────────────────────────────────────

    def _find_best_match(self, item: TakeoffLineItem) -> dict | None:
        """Find the best PB summary match for a takeoff line item.

        Priority:
        1. CSI code exact match
        2. Fuzzy activity description match (>= 0.6 threshold)
        3. Unit + crew tiebreakers
        """
        # Strategy 1: CSI exact match
        if item.csi_code:
            csi_matches = [s for s in self._pb_summary if s["csi_code"] and s["csi_code"] == item.csi_code]
            if len(csi_matches) == 1:
                return csi_matches[0]
            if len(csi_matches) > 1:
                # Pick the one with best fuzzy score on activity
                norm_item = self._normalize(item.activity)
                best = max(
                    csi_matches,
                    key=lambda s: self._fuzzy_score(norm_item, self._normalize(s["activity"])),
                )
                return best

        # Strategy 2: Fuzzy activity match
        norm_item = self._normalize(item.activity)
        candidates: list[tuple[float, dict]] = []

        for s in self._pb_summary:
            score = self._fuzzy_score(norm_item, self._normalize(s["activity"]))
            if score < 0.6:
                continue

            # Boost for matching unit
            if item.unit and s["unit"] and item.unit.lower().strip() == s["unit"].lower().strip():
                score += 0.1

            # Boost for matching crew
            if item.crew and s["crew_trade"] and item.crew.lower().strip() == s["crew_trade"].lower().strip():
                score += 0.05

            candidates.append((score, s))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    # ── Public API ───────────────────────────────────────────────────────

    def match_all(self, items: list[TakeoffLineItem]) -> list[RateRecommendation]:
        """Match every takeoff line item against PB history.

        Returns a RateRecommendation per item with historical stats,
        delta calculation, flag, and confidence — all deterministic Python.
        """
        recommendations: list[RateRecommendation] = []

        for item in items:
            match = self._find_best_match(item)

            if match and match["sample_count"] > 0:
                sample_count = match["sample_count"]
                confidence = self._confidence_level(sample_count)

                if item.production_rate and match["avg_rate"]:
                    # Delta: positive = estimator more optimistic (higher rate) than history
                    delta_pct = round(
                        ((item.production_rate - match["avg_rate"]) / match["avg_rate"]) * 100,
                        2,
                    )
                    flag = self._flag_from_delta(delta_pct)
                elif not item.production_rate and match["avg_rate"]:
                    # PB match exists but estimator has no rate (e.g. .est file)
                    delta_pct = None
                    flag = "NEEDS_RATE"
                else:
                    # Match found but no usable rates on either side
                    delta_pct = None
                    flag = "NO_DATA"

                # HF-29: prefer the estimator's rate from the takeoff file
                # over the PB historical average. The proposal_form needs the
                # bid total (estimator's actual rates), and the historical
                # avg is preserved separately as historical_avg_rate. PB avg
                # is used only as a fallback when the parser couldn't extract
                # a per-line rate from the file.
                recommendations.append(
                    RateRecommendation(
                        line_item_row=item.row_number,
                        activity=item.activity,
                        unit=item.unit,
                        crew=item.crew,
                        quantity=item.quantity,  # HF-29b: pass through file qty
                        estimator_rate=item.production_rate,
                        historical_avg_rate=match["avg_rate"],
                        historical_min_rate=match["min_rate"],
                        historical_max_rate=match["max_rate"],
                        historical_spread=match["spread"],
                        sample_count=sample_count,
                        confidence=confidence,
                        delta_pct=delta_pct,
                        flag=flag,
                        matching_projects=match["projects"],
                        labor_cost_per_unit=(
                            item.labor_cost_per_unit
                            if item.labor_cost_per_unit is not None
                            else match["avg_labor_cost"]
                        ),
                        material_cost_per_unit=(
                            item.material_cost_per_unit
                            if item.material_cost_per_unit is not None
                            else match["avg_mat_cost"]
                        ),
                        wbs_area=item.wbs_area,
                    )
                )
            else:
                # No match found — surface estimator's parsed rates anyway
                # (HF-29) so proposal_form / takeoff_total_labor reflect the
                # actual bid even when the project has no PB coverage.
                recommendations.append(
                    RateRecommendation(
                        line_item_row=item.row_number,
                        activity=item.activity,
                        unit=item.unit,
                        crew=item.crew,
                        quantity=item.quantity,  # HF-29b: pass through file qty
                        estimator_rate=item.production_rate,
                        sample_count=0,
                        confidence="none",
                        flag="NO_DATA",
                        wbs_area=item.wbs_area,
                        labor_cost_per_unit=item.labor_cost_per_unit,
                        material_cost_per_unit=item.material_cost_per_unit,
                    )
                )

        return recommendations

    def compute_optimism_score(self, recommendations: list[RateRecommendation]) -> float | None:
        """Average delta_pct across matched items.

        Positive = estimator is more optimistic than history.
        Returns None if no items have a delta.
        """
        deltas = [r.delta_pct for r in recommendations if r.delta_pct is not None]
        if not deltas:
            return None
        return round(sum(deltas) / len(deltas), 2)

    @staticmethod
    def flags_summary(recommendations: list[RateRecommendation]) -> dict:
        """Count of each flag type."""
        summary = {"OK": 0, "REVIEW": 0, "UPDATE": 0, "NO_DATA": 0, "NEEDS_RATE": 0}
        for r in recommendations:
            if r.flag in summary:
                summary[r.flag] += 1
        return summary

    # ── Private helpers ──────────────────────────────────────────────────

    @staticmethod
    def _confidence_level(sample_count: int) -> str:
        if sample_count >= 10:
            return "high"
        if sample_count >= 5:
            return "medium"
        if sample_count >= 1:
            return "low"
        return "none"

    @staticmethod
    def _flag_from_delta(delta_pct: float) -> str:
        abs_delta = abs(delta_pct)
        if abs_delta < 5:
            return "OK"
        if abs_delta < 20:
            return "REVIEW"
        return "UPDATE"


# ── Quick smoke test ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    from apex.backend.agents.pipeline_contracts import TakeoffLineItem

    # Mock item — no DB session, so we demonstrate the matching logic
    test_item = TakeoffLineItem(
        row_number=1,
        activity="Footing Forms",
        unit="sqft",
        production_rate=10.0,
    )

    print("=== Rate Matching Engine — Smoke Test ===")
    print(f"Test item: {test_item.activity} | unit={test_item.unit} | rate={test_item.production_rate}")
    print()
    print("To run with real PB data, instantiate RateMatchingEngine(db=session)")
    print("and call engine.match_all([test_item])")
    print()

    # Demonstrate deterministic math with mock PB data
    mock_avg_rate = 8.5
    delta_pct = round(((test_item.production_rate - mock_avg_rate) / mock_avg_rate) * 100, 2)
    flag = RateMatchingEngine._flag_from_delta(delta_pct)
    confidence = RateMatchingEngine._confidence_level(12)

    print(f"Mock PB avg_rate: {mock_avg_rate}")
    print(f"Delta: {delta_pct}% → flag={flag}")
    print(f"Sample count 12 → confidence={confidence}")
    print()

    # Demonstrate fuzzy matching
    score = RateMatchingEngine._fuzzy_score(
        RateMatchingEngine._normalize("Footing Forms"),
        RateMatchingEngine._normalize("Ftg Forms - Strip"),
    )
    print(f"Fuzzy score 'Footing Forms' vs 'Ftg Forms - Strip': {score:.3f}")

    score2 = RateMatchingEngine._fuzzy_score(
        RateMatchingEngine._normalize("Footing Forms"),
        RateMatchingEngine._normalize("Footing Formwork"),
    )
    print(f"Fuzzy score 'Footing Forms' vs 'Footing Formwork': {score2:.3f}")
