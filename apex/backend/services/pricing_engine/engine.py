"""PricingEngine — deterministic quantity × rate → EstimateLine.

Architecture §12.5:
  Produce first-pass line-item pricing once quantities are available.

Pricing hierarchy (§12.5):
  1. Contextual historical benchmark
  2. Company assembly / rule
  3. Manual estimator input required
  4. Temporary allowance

Rules (§24):
  - Do not let LLMs output final money without deterministic validation.
  - Every recommendation must store explanation metadata.
  - Low-confidence outputs must force visible review.
  - Do not bury contingencies in line-item rates.
  - Separate extraction confidence from pricing confidence.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from apex.backend.services.benchmarking_engine.context import ProjectContext
from apex.backend.services.benchmarking_engine.engine import BenchmarkingEngine, BenchmarkOutput

# ── Output ────────────────────────────────────────────────────────────────────


@dataclass
class PricedLine:
    """All fields needed to create an EstimateLine record."""

    description: str
    division_code: str | None
    quantity: float
    unit: str | None
    recommended_unit_cost: float | None
    recommended_total_cost: float | None
    pricing_basis: str  # contextual_benchmark_p50 | allowance | no_data
    benchmark_sample_size: int
    benchmark_p10: float | None
    benchmark_p25: float | None
    benchmark_p50: float | None
    benchmark_p75: float | None
    benchmark_p90: float | None
    benchmark_mean: float | None
    benchmark_std_dev: float | None
    benchmark_context_similarity: float
    confidence_score: float
    confidence_level: str
    missing_quantity: bool
    line_status: str  # needs_review | accepted | overridden | excluded
    explanation: str


# ── Engine ────────────────────────────────────────────────────────────────────

# Allowance rates — used when there is no benchmark data but the item is required.
# These are conservative fallbacks; they must be reviewed by an estimator.
_ALLOWANCES: dict[str, float] = {
    "Mobilization": 15_000.0,  # LS
    "Traffic Control": 8_000.0,  # LS
    "Temporary Facilities": 25_000.0,  # LS
    "Testing / Inspection": 12_000.0,  # LS
    "Cleanup / Closeout": 5_000.0,  # LS
}


class PricingEngine:
    """Combines QuantityItems + BenchmarkResults to produce EstimateLines.

    Deterministic math only — no LLM involved in pricing.
    """

    def __init__(self, db: Session, ctx: ProjectContext):
        self.db = db
        self.ctx = ctx
        self._benchmarker = BenchmarkingEngine(db)

    def price_scope_item(
        self,
        canonical_name: str,
        division_code: str | None,
        quantity: float | None,
        unit: str | None,
    ) -> PricedLine:
        """Price a single scope item.

        Args:
            canonical_name: Canonical activity name (matches ontology)
            division_code:  CSI division code (e.g. "03 30 00")
            quantity:       Estimator-provided quantity; None = missing
            unit:           Unit of measure (CY, SF, LF, LS, ...)

        Returns:
            PricedLine with recommended costs, benchmark data, and confidence.
        """
        missing_quantity = quantity is None or quantity <= 0.0

        # Always pull the benchmark regardless of quantity — it informs confidence
        bm: BenchmarkOutput = self._benchmarker.benchmark(
            ctx=self.ctx,
            canonical_activity_name=canonical_name,
        )

        # Determine pricing basis and recommended cost
        if missing_quantity:
            return self._no_quantity_line(canonical_name, division_code, unit, bm)

        if bm.sample_size >= 1 and bm.p50 is not None:
            return self._benchmark_line(canonical_name, division_code, quantity, unit, bm)

        if canonical_name in _ALLOWANCES:
            return self._allowance_line(canonical_name, division_code, quantity, unit, bm)

        return self._no_data_line(canonical_name, division_code, quantity, unit, bm)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _benchmark_line(
        self,
        name: str,
        division_code: str | None,
        quantity: float,
        unit: str | None,
        bm: BenchmarkOutput,
    ) -> PricedLine:
        unit_cost = bm.p50
        total = round(unit_cost * quantity, 2)
        explanation = (
            f"Priced at benchmark p50 (${unit_cost:,.2f}/{unit or '?'}) "
            f"from {bm.sample_size} comparable observations "
            f"(context similarity {bm.context_similarity_score:.2f}). "
            f"p25=${bm.p25:,.2f}, p75=${bm.p75:,.2f}."
        )
        return PricedLine(
            description=name,
            division_code=division_code,
            quantity=quantity,
            unit=unit,
            recommended_unit_cost=unit_cost,
            recommended_total_cost=total,
            pricing_basis="contextual_benchmark_p50",
            benchmark_sample_size=bm.sample_size,
            benchmark_p10=bm.p10,
            benchmark_p25=bm.p25,
            benchmark_p50=bm.p50,
            benchmark_p75=bm.p75,
            benchmark_p90=bm.p90,
            benchmark_mean=bm.mean,
            benchmark_std_dev=bm.std_dev,
            benchmark_context_similarity=bm.context_similarity_score,
            confidence_score=bm.benchmark_confidence,
            confidence_level=bm.confidence_label,
            missing_quantity=False,
            line_status="needs_review",
            explanation=explanation,
        )

    def _allowance_line(
        self,
        name: str,
        division_code: str | None,
        quantity: float,
        unit: str | None,
        bm: BenchmarkOutput,
    ) -> PricedLine:
        allowance = _ALLOWANCES[name]
        explanation = (
            f"No historical benchmark available for '{name}'. "
            f"Conservative allowance of ${allowance:,.0f} applied. "
            f"Estimator review required."
        )
        return PricedLine(
            description=name,
            division_code=division_code,
            quantity=quantity,
            unit=unit,
            recommended_unit_cost=None,
            recommended_total_cost=allowance,
            pricing_basis="allowance",
            benchmark_sample_size=0,
            benchmark_p10=None,
            benchmark_p25=None,
            benchmark_p50=None,
            benchmark_p75=None,
            benchmark_p90=None,
            benchmark_mean=None,
            benchmark_std_dev=None,
            benchmark_context_similarity=0.0,
            confidence_score=0.15,
            confidence_level="very_low",
            missing_quantity=False,
            line_status="needs_review",
            explanation=explanation,
        )

    def _no_data_line(
        self,
        name: str,
        division_code: str | None,
        quantity: float,
        unit: str | None,
        bm: BenchmarkOutput,
    ) -> PricedLine:
        explanation = f"No historical data or allowance rule for '{name}'. Estimator must provide unit cost."
        return PricedLine(
            description=name,
            division_code=division_code,
            quantity=quantity,
            unit=unit,
            recommended_unit_cost=None,
            recommended_total_cost=None,
            pricing_basis="no_data",
            benchmark_sample_size=0,
            benchmark_p10=None,
            benchmark_p25=None,
            benchmark_p50=None,
            benchmark_p75=None,
            benchmark_p90=None,
            benchmark_mean=None,
            benchmark_std_dev=None,
            benchmark_context_similarity=0.0,
            confidence_score=0.0,
            confidence_level="very_low",
            missing_quantity=False,
            line_status="needs_review",
            explanation=explanation,
        )

    def _no_quantity_line(
        self,
        name: str,
        division_code: str | None,
        unit: str | None,
        bm: BenchmarkOutput,
    ) -> PricedLine:
        explanation = f"Quantity missing for '{name}'. Cannot compute total cost. " + (
            f"Benchmark p50=${bm.p50:,.2f}/{unit or '?'} available when quantity is provided."
            if bm.p50
            else "No benchmark data found."
        )
        return PricedLine(
            description=name,
            division_code=division_code,
            quantity=0.0,
            unit=unit,
            recommended_unit_cost=bm.p50,
            recommended_total_cost=None,
            pricing_basis="no_data",
            benchmark_sample_size=bm.sample_size,
            benchmark_p10=bm.p10,
            benchmark_p25=bm.p25,
            benchmark_p50=bm.p50,
            benchmark_p75=bm.p75,
            benchmark_p90=bm.p90,
            benchmark_mean=bm.mean,
            benchmark_std_dev=bm.std_dev,
            benchmark_context_similarity=bm.context_similarity_score,
            confidence_score=0.0,
            confidence_level="very_low",
            missing_quantity=True,
            line_status="needs_review",
            explanation=explanation,
        )

    def persist_estimate_line(
        self,
        db: Session,
        estimate_run_id: str,
        scope_item_id: str | None,
        benchmark_result_id: str | None,
        priced: PricedLine,
    ):
        """Write a PricedLine into the decision_estimate_lines table."""
        from apex.backend.models.decision_models import EstimateLine

        line = EstimateLine(
            estimate_run_id=estimate_run_id,
            scope_item_id=scope_item_id,
            benchmark_result_id=benchmark_result_id,
            description=priced.description,
            division_code=priced.division_code,
            quantity=priced.quantity,
            unit=priced.unit,
            recommended_unit_cost=priced.recommended_unit_cost,
            recommended_total_cost=priced.recommended_total_cost,
            pricing_basis=priced.pricing_basis,
            benchmark_sample_size=priced.benchmark_sample_size,
            benchmark_p25=priced.benchmark_p25,
            benchmark_p50=priced.benchmark_p50,
            benchmark_p75=priced.benchmark_p75,
            benchmark_p90=priced.benchmark_p90,
            benchmark_mean=priced.benchmark_mean,
            benchmark_std_dev=priced.benchmark_std_dev,
            benchmark_context_similarity=priced.benchmark_context_similarity,
            confidence_score=priced.confidence_score,
            confidence_level=priced.confidence_level,
            missing_quantity=priced.missing_quantity,
            line_status=priced.line_status,
            explanation=priced.explanation,
        )
        db.add(line)
        return line
