"""BenchmarkingEngine — context-aware historical rate retrieval and percentile computation.

Architecture §12.4:
  - Filter comparable projects by context
  - Score context similarity
  - Retrieve activity-level observations
  - Compute percentiles and dispersion
  - Return benchmark confidence

Architecture §16: Confidence formula
  confidence = w1 * norm_sample + w2 * (1-norm_variance) + w3 * context_sim
             + w4 * recency + w5 * data_quality
"""

import json
import statistics
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from apex.backend.services.benchmarking_engine.context import (
    ProjectContext,
    context_similarity_score,
)

# ── Confidence ───────────────────────────────────────────────────────────────

_CONFIDENCE_WEIGHTS = (0.25, 0.25, 0.20, 0.15, 0.15)
_MIN_CONTEXT_SIM = 0.30  # below this, observations are excluded


def _confidence_label(score: float) -> str:
    if score >= 0.80:
        return "high"
    if score >= 0.60:
        return "medium"
    if score >= 0.40:
        return "low"
    return "very_low"


def _recency_score(obs_date: date | None, today: date | None = None) -> float:
    """Decay observations linearly over 5 years. Missing date → 0.5."""
    if obs_date is None:
        return 0.5
    reference = today or date.today()
    days_old = (reference - obs_date).days
    years_old = days_old / 365.25
    return max(0.0, 1.0 - years_old / 5.0)


def compute_confidence(
    sample_size: int,
    unit_costs: list[float],
    context_sim: float,
    recency: float,
    data_quality: float,
    weights=_CONFIDENCE_WEIGHTS,
) -> float:
    """§16 confidence formula."""
    w1, w2, w3, w4, w5 = weights
    norm_n = min(sample_size / 20.0, 1.0)
    if len(unit_costs) >= 2:
        cv = statistics.stdev(unit_costs) / statistics.mean(unit_costs) if statistics.mean(unit_costs) else 1.0
        norm_variance = min(cv, 1.0)
    else:
        norm_variance = 1.0
    score = w1 * norm_n + w2 * (1 - norm_variance) + w3 * context_sim + w4 * recency + w5 * data_quality
    return round(min(score, 1.0), 4)


# ── Result object ─────────────────────────────────────────────────────────────


@dataclass
class BenchmarkOutput:
    canonical_activity_name: str
    sample_size: int
    p10: float | None
    p25: float | None
    p50: float | None
    p75: float | None
    p90: float | None
    mean: float | None
    std_dev: float | None
    context_similarity_score: float
    benchmark_confidence: float
    confidence_label: str
    comparable_filter_json: str
    observations_used: int = 0

    def as_dict(self) -> dict:
        return {
            "canonical_activity_name": self.canonical_activity_name,
            "sample_size": self.sample_size,
            "p10": self.p10,
            "p25": self.p25,
            "p50": self.p50,
            "p75": self.p75,
            "p90": self.p90,
            "mean": self.mean,
            "std_dev": self.std_dev,
            "context_similarity_score": self.context_similarity_score,
            "benchmark_confidence": self.benchmark_confidence,
            "confidence_label": self.confidence_label,
        }


# ── Engine ────────────────────────────────────────────────────────────────────


class BenchmarkingEngine:
    """Context-aware benchmark retrieval and percentile computation.

    Usage:
        engine = BenchmarkingEngine(db_session)
        result = engine.benchmark(
            ctx=ProjectContext(project_type="data_center", region="midwest", ...),
            canonical_activity_name="CIP Concrete Slab",
        )
    """

    def __init__(self, db: Session):
        self.db = db

    def benchmark(
        self,
        ctx: ProjectContext,
        canonical_activity_name: str,
        min_context_sim: float = _MIN_CONTEXT_SIM,
    ) -> BenchmarkOutput:
        """Retrieve comparable observations and compute percentile distribution.

        Steps (§12.4):
          1. Load comparable projects
          2. Score context similarity; exclude below min_context_sim
          3. Retrieve HistoricalRateObservation rows for matching comparables
          4. Weight observations by recency × quality × context_sim
          5. Compute percentiles on unit_cost
          6. Score confidence per §16
        """
        from apex.backend.models.decision_models import (
            ComparableProject,
            HistoricalRateObservation,
        )

        # 1. Load all comparable projects
        all_comparables = self.db.query(ComparableProject).all()

        # 2. Score and filter by context similarity
        scored = []
        for cp in all_comparables:
            sim = context_similarity_score(ctx, cp)
            if sim >= min_context_sim:
                scored.append((cp, sim))

        comparable_ids = [cp.id for cp, _ in scored]
        sim_by_id = {cp.id: sim for cp, sim in scored}

        filter_snapshot = json.dumps(
            {
                "project_type": ctx.project_type,
                "region": ctx.region,
                "market_sector": ctx.market_sector,
                "min_context_sim": min_context_sim,
                "comparable_count": len(comparable_ids),
            }
        )

        if not comparable_ids:
            return self._empty_result(canonical_activity_name, filter_snapshot)

        # 3. Retrieve rate observations for matching comparables
        #    Match by canonical_activity_id (preferred) or raw_activity_name (fuzzy fallback)
        from apex.backend.models.decision_models import CanonicalActivity

        canonical = self.db.query(CanonicalActivity).filter(CanonicalActivity.name == canonical_activity_name).first()

        obs_query = self.db.query(HistoricalRateObservation).filter(
            HistoricalRateObservation.comparable_project_id.in_(comparable_ids)
        )
        if canonical:
            obs_query = obs_query.filter(HistoricalRateObservation.canonical_activity_id == canonical.id)
        else:
            # Fuzzy match on raw_activity_name (case-insensitive contains)
            obs_query = obs_query.filter(
                HistoricalRateObservation.raw_activity_name.ilike(f"%{canonical_activity_name}%")
            )

        observations = obs_query.all()

        if not observations:
            return self._empty_result(canonical_activity_name, filter_snapshot)

        # 4. Build weighted unit_cost list
        #    weight = context_sim × recency_weight × quality_weight
        weighted_costs: list[float] = []
        raw_costs: list[float] = []
        mean_sim = 0.0
        mean_recency = 0.0
        mean_quality = 0.0

        for obs in observations:
            if obs.unit_cost is None:
                continue
            sim = sim_by_id.get(obs.comparable_project_id, 0.5)
            rec = _recency_score(obs.observation_date)
            qual = obs.quality_weight if obs.quality_weight else obs.data_quality_score

            weight = sim * rec * qual
            # Expand into weighted list by repeating (simple integer weight)
            repeat = max(1, round(weight * 10))
            weighted_costs.extend([obs.unit_cost] * repeat)
            raw_costs.append(obs.unit_cost)
            mean_sim += sim
            mean_recency += rec
            mean_quality += qual

        if not weighted_costs:
            return self._empty_result(canonical_activity_name, filter_snapshot)

        n = len(raw_costs)
        mean_sim /= n
        mean_recency /= n
        mean_quality /= n

        weighted_costs.sort()

        # 5. Percentiles
        def _pct(data: list[float], p: float) -> float:
            if not data:
                return 0.0
            idx = (len(data) - 1) * p / 100
            lo, hi = int(idx), min(int(idx) + 1, len(data) - 1)
            return round(data[lo] + (data[hi] - data[lo]) * (idx - lo), 2)

        p10 = _pct(weighted_costs, 10)
        p25 = _pct(weighted_costs, 25)
        p50 = _pct(weighted_costs, 50)
        p75 = _pct(weighted_costs, 75)
        p90 = _pct(weighted_costs, 90)
        mean_val = round(statistics.mean(raw_costs), 2)
        std_dev = round(statistics.stdev(raw_costs), 2) if n > 1 else 0.0

        # 6. Confidence
        conf = compute_confidence(
            sample_size=n,
            unit_costs=raw_costs,
            context_sim=mean_sim,
            recency=mean_recency,
            data_quality=mean_quality,
        )

        return BenchmarkOutput(
            canonical_activity_name=canonical_activity_name,
            sample_size=n,
            p10=p10,
            p25=p25,
            p50=p50,
            p75=p75,
            p90=p90,
            mean=mean_val,
            std_dev=std_dev,
            context_similarity_score=round(mean_sim, 4),
            benchmark_confidence=conf,
            confidence_label=_confidence_label(conf),
            comparable_filter_json=filter_snapshot,
            observations_used=len(weighted_costs),
        )

    def _empty_result(self, activity: str, filter_json: str) -> BenchmarkOutput:
        return BenchmarkOutput(
            canonical_activity_name=activity,
            sample_size=0,
            p10=None,
            p25=None,
            p50=None,
            p75=None,
            p90=None,
            mean=None,
            std_dev=None,
            context_similarity_score=0.0,
            benchmark_confidence=0.0,
            confidence_label="very_low",
            comparable_filter_json=filter_json,
            observations_used=0,
        )
