"""Decision commercial engine — deterministic GC cost structuring.

No LLM touches money. All math is Python.
"""

from sqlalchemy.orm import Session

from apex.backend.models.decision_models import CostBreakdownBucket


class DecisionCommercialEngine:
    DEFAULT_RULES = {
        "general_conditions":    0.08,
        "supervision":           0.04,
        "temporary_facilities":  0.02,
        "logistics":             0.015,
        "permits":               0.005,
        "testing":               0.005,
        "contingency":           0.05,
        "overhead":              0.04,
        "fee":                   0.05,
    }

    def __init__(self, db: Session):
        self.db = db

    def structure_cost(self, project_id: int, direct_cost: float) -> list:
        """Delete existing buckets for project, create fresh set, return all."""
        # Delete existing
        self.db.query(CostBreakdownBucket).filter(
            CostBreakdownBucket.project_id == project_id
        ).delete(synchronize_session=False)

        buckets = []

        # Direct cost bucket
        direct_bucket = CostBreakdownBucket(
            project_id=project_id,
            bucket_type="direct_cost",
            amount=round(direct_cost, 2),
            method="sum_of_estimate_lines",
        )
        self.db.add(direct_bucket)
        buckets.append(direct_bucket)

        # One bucket per rule
        for bucket_type, pct in self.DEFAULT_RULES.items():
            amount = round(direct_cost * pct, 2)
            bucket = CostBreakdownBucket(
                project_id=project_id,
                bucket_type=bucket_type,
                amount=amount,
                method=f"{pct:.1%}_of_direct_cost",
            )
            self.db.add(bucket)
            buckets.append(bucket)

        self.db.flush()
        return buckets
