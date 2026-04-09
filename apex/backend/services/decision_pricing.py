"""Decision pricing engine — deterministic unit-cost pricing from historical benchmarks.

No LLM touches money. All math is Python.
"""

from sqlalchemy.orm import Session

from apex.backend.models.decision_models import EstimateLine
from apex.backend.services.decision_benchmark import DecisionBenchmarkEngine


class DecisionPricingEngine:
    def __init__(self, db: Session):
        self.db = db
        self._benchmark_engine = DecisionBenchmarkEngine(db)

    def price_quantities(self, project, quantities: list) -> list:
        """Price a list of quantity dicts using contextual historical benchmarks.

        quantities = [{description, quantity, unit, division_code}]
        Returns list of EstimateLine objects (added to session, not yet committed).
        """
        benchmark_results = self._benchmark_engine.benchmark_all_quantities(
            project, quantities
        )

        lines = []
        for bm in benchmark_results:
            qty_dict = bm.pop("_qty", {})
            description = qty_dict.get("description", bm.get("activity_name", ""))
            quantity = float(qty_dict.get("quantity", 0))
            unit = qty_dict.get("unit")
            division_code = qty_dict.get("division_code") or bm.get("division_code")

            n = bm.get("sample_size", 0)
            p50 = bm.get("p50")

            if n > 0 and p50 is not None:
                recommended_unit_cost = p50
                recommended_total_cost = round(quantity * p50, 2)
                pricing_basis = "contextual_benchmark_p50"
                p25 = bm.get("p25")
                p75 = bm.get("p75")
                label = bm.get("confidence_label", "very_low")
                sim = bm.get("context_similarity", 0.0)
                explanation = (
                    f"Based on {n} historical observations. "
                    f"Range: ${p25} (p25) \u2192 ${p75} (p75). "
                    f"Context similarity: {sim:.0%}. "
                    f"Confidence: {label}."
                )
                needs_review = label != "high"
            else:
                recommended_unit_cost = None
                recommended_total_cost = None
                pricing_basis = "manual_input_required"
                explanation = "No comparable historical data found. Manual pricing required."
                needs_review = True
                label = "very_low"

            line = EstimateLine(
                project_id=project.id,
                description=description,
                division_code=division_code,
                quantity=quantity,
                unit=unit,
                recommended_unit_cost=recommended_unit_cost,
                recommended_total_cost=recommended_total_cost,
                pricing_basis=pricing_basis,
                benchmark_sample_size=n or None,
                benchmark_p25=bm.get("p25"),
                benchmark_p50=bm.get("p50"),
                benchmark_p75=bm.get("p75"),
                benchmark_p90=bm.get("p90"),
                benchmark_mean=bm.get("mean"),
                benchmark_std_dev=bm.get("std_dev"),
                benchmark_context_similarity=bm.get("context_similarity"),
                confidence_score=bm.get("confidence_score"),
                confidence_level=label,
                needs_review=needs_review,
                explanation=explanation,
            )
            self.db.add(line)
            lines.append(line)

        self.db.flush()
        return lines

    def recalculate_totals(self, project_id: int) -> dict:
        """Sum EstimateLine costs for a project."""
        lines = (
            self.db.query(EstimateLine)
            .filter(EstimateLine.project_id == project_id)
            .all()
        )
        direct_cost = round(
            sum(ln.recommended_total_cost or 0.0 for ln in lines), 2
        )
        needs_review_count = sum(1 for ln in lines if ln.needs_review)
        low_confidence_count = sum(
            1 for ln in lines if ln.confidence_level in ("low", "very_low")
        )
        return {
            "direct_cost": direct_cost,
            "line_count": len(lines),
            "needs_review_count": needs_review_count,
            "low_confidence_count": low_confidence_count,
        }
