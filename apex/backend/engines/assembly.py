"""Assembly Engine — orchestrates pricing, commercial, and risk engines."""

from sqlalchemy.orm import Session

from apex.backend.engines.pricing import PricingEngine
from apex.backend.engines.commercial import CommercialEngine
from apex.backend.engines.risk import RiskEngine
from apex.backend.models.decision_models import CostBreakdownBucket


class AssemblyEngine:
    def __init__(self, db: Session):
        self.db = db
        self._pricing = PricingEngine(db)
        self._commercial = CommercialEngine(db)
        self._risk = RiskEngine(db)

    def run_estimate(self, project, quantities: list[dict]) -> dict:
        """Run full estimate pipeline: price → structure → risk.

        Returns summary dict with lines, cost breakdown, and risk items.
        """
        # 1. Price quantities
        lines = self._pricing.price_quantities(project, quantities)

        # 2. Totals
        totals = self._pricing.recalculate_totals(project.id)
        direct_cost = totals["direct_cost"]

        # 3. Commercial cost structure
        cost_buckets = self._commercial.structure_cost(project.id, direct_cost)

        # 4. Risk register
        risk_items = self._risk.generate_risks(project, direct_cost)

        # Derive final bid value from buckets
        final_bid = round(
            sum(b.amount for b in cost_buckets), 2
        )

        return {
            "line_count": totals["line_count"],
            "direct_cost": direct_cost,
            "needs_review_count": totals["needs_review_count"],
            "low_confidence_count": totals["low_confidence_count"],
            "final_bid_value": final_bid,
            "risk_item_count": len(risk_items),
            "lines": lines,
            "cost_breakdown": cost_buckets,
            "risk_items": risk_items,
        }
