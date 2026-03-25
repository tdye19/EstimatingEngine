"""TokenUsage model — records every LLM call made during the agent pipeline."""

from sqlalchemy import Column, Integer, Float, String, ForeignKey
from sqlalchemy.orm import relationship
from apex.backend.db.database import Base
from apex.backend.models.base import TimestampMixin


# ---------------------------------------------------------------------------
# Pricing table: (input_cost_per_1M_tokens, output_cost_per_1M_tokens) in USD
# ---------------------------------------------------------------------------

MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gemini-2.5-flash":            (0.30,  2.50),
    "claude-sonnet-4-6-20260101":  (3.00, 15.00),
    "claude-haiku-4-5-20251001":   (1.00,  5.00),
}


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return estimated USD cost for a single LLM call.

    Matches by checking whether any pricing key appears as a substring of the
    model name (case-insensitive), so minor version suffixes don't break lookup.
    Returns 0.0 for unknown models rather than raising.
    """
    model_lower = model.lower()
    input_price: float = 0.0
    output_price: float = 0.0

    for key, (inp, out) in MODEL_PRICING.items():
        if key in model_lower:
            input_price, output_price = inp, out
            break

    return round(
        (input_tokens / 1_000_000) * input_price
        + (output_tokens / 1_000_000) * output_price,
        8,
    )


# ---------------------------------------------------------------------------
# Agent number → human-readable label (for display / aggregation)
# ---------------------------------------------------------------------------

AGENT_LABELS: dict[int, str] = {
    2: "Spec Parser",
    3: "Gap Analysis",
    4: "Quantity Takeoff",
    5: "Labor Productivity",
    6: "Estimate Assembly",
    7: "IMPROVE Feedback",
}


class TokenUsage(Base, TimestampMixin):
    """Persists one record per LLM call across all pipeline agents."""

    __tablename__ = "token_usage"

    id           = Column(Integer, primary_key=True, index=True)
    project_id   = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    estimate_id  = Column(Integer, ForeignKey("estimates.id"), nullable=True)
    agent_number = Column(Integer, nullable=False)
    provider     = Column(String(50), nullable=False)
    model        = Column(String(100), nullable=False)
    input_tokens  = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    estimated_cost = Column(Float, default=0.0)

    project  = relationship("Project",  back_populates="token_usage_records")
    estimate = relationship("Estimate", back_populates="token_usage_records", foreign_keys=[estimate_id])
