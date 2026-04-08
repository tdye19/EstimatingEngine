"""Pricing Engine — deterministic math only. No LLM touches money."""

from sqlalchemy.orm import Session

from apex.backend.engines.benchmarking import BenchmarkingEngine
from apex.backend.models.decision_models import EstimateLine


class PricingEngine:
    def __init__(self, db: Session):
        self.db = db
        self._benchmarking = BenchmarkingEngine(db)

    def price_quantities(self, project, quantities: list[dict]) -> list[EstimateLine]:
        """Take estimator quantities, retrieve benchmarks, create priced EstimateLine rows.

        quantities: [{description, quantity, unit, division_code, source?}]
        Returns list of EstimateLine ORM objects added to the session.
        """
        benchmarks = self._benchmarking.benchmark_all_quantities(project, quantities)
        lines = []

        for qty_dict, bm in zip(quantities, benchmarks):
            quantity = float(qty_dict.get("quantity") or 0)
            description = str(qty_dict.get("description", "")).strip()
            unit = qty_dict.get("unit") or None
            division_code = qty_dict.get("division_code") or None

            has_data = bm["sample_size"] > 0 and bm["p50"] is not None

            if has_data:
                p50 = bm["p50"]
                total = round(quantity * p50, 2)
                sim_pct = round((bm["context_similarity"] or 0) * 100, 1)
                conf_label = bm["confidence_label"]
                explanation = (
                    f"Based on {bm['sample_size']} historical observations. "
                    f"Range: ${bm['p25']} (p25) \u2192 ${bm['p75']} (p75). "
                    f"Context similarity: {sim_pct}%. "
                    f"Confidence: {conf_label}."
                )
                line = EstimateLine(
                    project_id=project.id,
                    description=description,
                    division_code=division_code,
                    quantity=quantity,
                    unit=unit,
                    recommended_unit_cost=round(p50, 2),
                    recommended_total_cost=total,
                    pricing_basis="contextual_benchmark_p50",
                    benchmark_sample_size=bm["sample_size"],
                    benchmark_p25=bm["p25"],
                    benchmark_p50=bm["p50"],
                    benchmark_p75=bm["p75"],
                    benchmark_p90=bm["p90"],
                    benchmark_mean=bm["mean"],
                    benchmark_std_dev=bm["std_dev"],
                    benchmark_context_similarity=bm["context_similarity"],
                    confidence_score=bm["confidence_score"],
                    confidence_level=conf_label,
                    needs_review=conf_label != "high",
                    explanation=explanation,
                )
            else:
                line = EstimateLine(
                    project_id=project.id,
                    description=description,
                    division_code=division_code,
                    quantity=quantity,
                    unit=unit,
                    recommended_unit_cost=None,
                    recommended_total_cost=None,
                    pricing_basis="manual_input_required",
                    benchmark_sample_size=0,
                    confidence_level="very_low",
                    confidence_score=0.0,
                    needs_review=True,
                    explanation="No comparable historical data found. Manual pricing required.",
                )

            self.db.add(line)
            lines.append(line)

        self.db.commit()
        # Refresh to populate IDs
        for line in lines:
            self.db.refresh(line)
        return lines

    def recalculate_totals(self, project_id: int) -> dict:
        """Sum all EstimateLine costs for a project."""
        lines = (
            self.db.query(EstimateLine)
            .filter(EstimateLine.project_id == project_id)
            .all()
        )
        direct_cost = round(
            sum(l.recommended_total_cost or 0.0 for l in lines), 2
        )
        needs_review_count = sum(1 for l in lines if l.needs_review)
        low_confidence_count = sum(
            1 for l in lines if l.confidence_level in ("low", "very_low")
        )
        return {
            "direct_cost": direct_cost,
            "line_count": len(lines),
            "needs_review_count": needs_review_count,
            "low_confidence_count": low_confidence_count,
        }
