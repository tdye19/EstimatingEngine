"""Decision assembly engine — orchestrates pricing, commercial, and risk engines.

No LLM touches money. All math is Python.
"""

from sqlalchemy.orm import Session

from apex.backend.services.decision_pricing import DecisionPricingEngine
from apex.backend.services.decision_commercial import DecisionCommercialEngine
from apex.backend.services.decision_risk import DecisionRiskEngine


class DecisionAssemblyEngine:
    def __init__(self, db: Session):
        self.db = db
        self._pricing = DecisionPricingEngine(db)
        self._commercial = DecisionCommercialEngine(db)
        self._risk = DecisionRiskEngine(db)

    def run_estimate(self, project, quantities: list) -> dict:
        """Run full estimate: price quantities, structure costs, generate risks.

        Returns:
            line_count, direct_cost, final_bid_value, risk_item_count,
            estimate_lines, cost_breakdown, risk_items
        """
        # 1. Price quantities
        estimate_lines = self._pricing.price_quantities(project, quantities)

        # 2. Get direct cost totals
        totals = self._pricing.recalculate_totals(project.id)
        direct_cost = totals["direct_cost"]

        # 3. Structure GC costs
        cost_breakdown = self._commercial.structure_cost(project.id, direct_cost)

        # 4. Generate risks
        risk_items = self._risk.generate_risks(project, direct_cost)

        # 5. Final bid value = sum of all buckets
        final_bid_value = round(sum(b.amount for b in cost_breakdown), 2)

        self.db.flush()

        return {
            "line_count": len(estimate_lines),
            "direct_cost": direct_cost,
            "final_bid_value": final_bid_value,
            "risk_item_count": len(risk_items),
            "estimate_lines": estimate_lines,
            "cost_breakdown": cost_breakdown,
            "risk_items": risk_items,
            "needs_review_count": totals["needs_review_count"],
            "low_confidence_count": totals["low_confidence_count"],
        }
