"""Decision benchmarking engine — context-aware historical rate retrieval.

Sits alongside the existing benchmark_engine.py (which uses HistoricalLineItem).
This engine works with ComparableProject + HistoricalRateObservation.
"""

import statistics
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from apex.backend.models.decision_models import ComparableProject, HistoricalRateObservation

# ---------------------------------------------------------------------------
# Context similarity weights
# ---------------------------------------------------------------------------
CONTEXT_WEIGHTS = {
    "project_type": 0.25,
    "market_sector": 0.15,
    "region": 0.20,
    "delivery_method": 0.10,
    "contract_type": 0.10,
    "complexity_level": 0.10,
    "size_bucket": 0.10,
}

_STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "into",
    "over",
    "per",
    "by",
    "of",
    "a",
    "an",
    "in",
    "on",
    "at",
    "to",
    "is",
}


def _size_bucket(size_sf: float | None) -> str | None:
    if size_sf is None:
        return None
    if size_sf < 10_000:
        return "small"
    if size_sf < 50_000:
        return "medium"
    if size_sf < 200_000:
        return "large"
    return "very_large"


def score_context_similarity(project, comparable_project: ComparableProject) -> float:
    """Compare project context dimensions, return 0-1 similarity score."""
    total = 0.0

    def _dim(proj_val, comp_val, weight):
        if proj_val and comp_val:
            return weight * (1.0 if proj_val == comp_val else 0.0)
        if proj_val is None and comp_val is None:
            return weight * 0.3
        return 0.0

    total += _dim(
        getattr(project, "project_type", None),
        comparable_project.project_type,
        CONTEXT_WEIGHTS["project_type"],
    )
    total += _dim(
        getattr(project, "market_sector", None),
        comparable_project.market_sector,
        CONTEXT_WEIGHTS["market_sector"],
    )
    total += _dim(
        getattr(project, "region", None),
        comparable_project.region,
        CONTEXT_WEIGHTS["region"],
    )
    total += _dim(
        getattr(project, "delivery_method", None),
        comparable_project.delivery_method,
        CONTEXT_WEIGHTS["delivery_method"],
    )
    total += _dim(
        getattr(project, "contract_type", None),
        comparable_project.contract_type,
        CONTEXT_WEIGHTS["contract_type"],
    )
    total += _dim(
        getattr(project, "complexity_level", None),
        comparable_project.complexity_level,
        CONTEXT_WEIGHTS["complexity_level"],
    )

    # Size bucket
    proj_bucket = _size_bucket(getattr(project, "size_sf", None))
    comp_bucket = _size_bucket(comparable_project.size_sf)
    total += _dim(proj_bucket, comp_bucket, CONTEXT_WEIGHTS["size_bucket"])

    # Normalize: max possible = sum of all weights = 1.0
    return min(max(total, 0.0), 1.0)


def _recency_score(comp: ComparableProject) -> float:
    """Return 0-1 recency score based on completed_date."""
    if comp.completed_date is None:
        return 0.3
    now = datetime.now(UTC)
    cd = comp.completed_date
    if cd.tzinfo is None:
        cd = cd.replace(tzinfo=UTC)
    age_years = (now - cd).days / 365.25
    if age_years < 1:
        return 1.0
    if age_years < 2:
        return 0.8
    if age_years < 4:
        return 0.6
    return 0.3


def compute_confidence(
    sample_size: int,
    std_dev: float,
    mean: float,
    avg_sim: float,
    avg_recency: float,
    avg_dq: float,
) -> tuple[float, str]:
    """Return (confidence_score, confidence_label)."""
    cov = (std_dev / mean) if (mean and mean != 0) else 1.0
    score = (
        0.30 * min(sample_size / 10, 1.0)
        + 0.25 * max(0.0, 1.0 - min(cov, 1.0))
        + 0.20 * avg_sim
        + 0.15 * avg_recency
        + 0.10 * avg_dq
    )
    score = min(max(score, 0.0), 1.0)
    if score >= 0.80:
        label = "high"
    elif score >= 0.60:
        label = "medium"
    elif score >= 0.40:
        label = "low"
    else:
        label = "very_low"
    return round(score, 4), label


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------


class DecisionBenchmarkEngine:
    def __init__(self, db: Session):
        self.db = db

    def get_comparable_projects(
        self,
        project,
        min_similarity: float = 0.0,
    ) -> list[tuple[ComparableProject, float]]:
        """Return all ComparableProjects with similarity >= min_similarity, sorted desc."""
        comps = self.db.query(ComparableProject).all()
        scored = []
        for comp in comps:
            sim = score_context_similarity(project, comp)
            if sim >= min_similarity:
                scored.append((comp, sim))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def benchmark_activity(
        self,
        project,
        activity_name: str,
        division_code: str = None,
        comparable_projects: list[tuple[ComparableProject, float]] = None,
    ) -> dict:
        """Retrieve historical rates for an activity and compute percentile distribution."""
        if comparable_projects is None:
            comparable_projects = self.get_comparable_projects(project)

        if not comparable_projects:
            return self._empty_result(activity_name, division_code)

        comp_ids = [c.id for c, _ in comparable_projects]
        sim_by_id = {c.id: s for c, s in comparable_projects}

        # Base query: unit_cost IS NOT NULL, within our comparable set
        base_q = self.db.query(HistoricalRateObservation).filter(
            HistoricalRateObservation.comparable_project_id.in_(comp_ids),
            HistoricalRateObservation.unit_cost.isnot(None),
        )

        # MATCHING STRATEGY — stop at first strategy with results
        observations = []

        # Strategy 1: full activity_name ILIKE substring
        obs1 = base_q.filter(HistoricalRateObservation.raw_activity_name.ilike(f"%{activity_name}%")).all()
        if obs1:
            observations = obs1
        else:
            # Strategy 2: top 3 keyword tokens ALL matching
            tokens = [t for t in activity_name.lower().split() if len(t) > 2 and t not in _STOP_WORDS]
            tokens.sort(key=len, reverse=True)
            top_tokens = tokens[:3]

            if top_tokens:
                q2 = base_q
                for tok in top_tokens:
                    q2 = q2.filter(HistoricalRateObservation.raw_activity_name.ilike(f"%{tok}%"))
                obs2 = q2.all()
                if obs2:
                    observations = obs2
                else:
                    # Strategy 3: top 2 keywords + division_code filter
                    top2 = top_tokens[:2]
                    if top2:
                        q3 = base_q
                        for tok in top2:
                            q3 = q3.filter(HistoricalRateObservation.raw_activity_name.ilike(f"%{tok}%"))
                        if division_code:
                            q3 = q3.filter(HistoricalRateObservation.division_code == division_code)
                        observations = q3.all()

        if not observations:
            return self._empty_result(activity_name, division_code)

        costs = sorted([o.unit_cost for o in observations])
        n = len(costs)

        mean_val = sum(costs) / n
        std_dev = statistics.stdev(costs) if n >= 2 else 0.0

        p25 = costs[int(n * 0.25)]
        p50 = statistics.median(costs)
        p75 = costs[int(n * 0.75)]
        p90 = costs[int(n * 0.90)]

        # Context quality metrics
        sims = [sim_by_id.get(o.comparable_project_id, 0.0) for o in observations]
        rec = [
            _recency_score(
                next((c for c, _ in comparable_projects if c.id == o.comparable_project_id), comparable_projects[0][0])
            )
            for o in observations
        ]
        dqs = [o.data_quality_score or 0.5 for o in observations]

        avg_sim = sum(sims) / len(sims)
        avg_rec = sum(rec) / len(rec)
        avg_dq = sum(dqs) / len(dqs)

        confidence_score, confidence_label = compute_confidence(n, std_dev, mean_val, avg_sim, avg_rec, avg_dq)

        return {
            "activity_name": activity_name,
            "division_code": division_code,
            "sample_size": n,
            "p25": round(p25, 2),
            "p50": round(p50, 2),
            "p75": round(p75, 2),
            "p90": round(p90, 2),
            "mean": round(mean_val, 2),
            "std_dev": round(std_dev, 2),
            "context_similarity": round(avg_sim, 4),
            "confidence_score": confidence_score,
            "confidence_label": confidence_label,
            "observations": n,
        }

    def benchmark_all_quantities(self, project, quantities: list) -> list:
        """Benchmark a list of quantity dicts. Fetches comparables once."""
        comparable_projects = self.get_comparable_projects(project)
        results = []
        for qty in quantities:
            result = self.benchmark_activity(
                project,
                qty.get("description", ""),
                division_code=qty.get("division_code"),
                comparable_projects=comparable_projects,
            )
            result["_qty"] = qty
            results.append(result)
        return results

    def _empty_result(self, activity_name: str, division_code: str) -> dict:
        return {
            "activity_name": activity_name,
            "division_code": division_code,
            "sample_size": 0,
            "p25": None,
            "p50": None,
            "p75": None,
            "p90": None,
            "mean": None,
            "std_dev": None,
            "context_similarity": 0.0,
            "confidence_score": 0.0,
            "confidence_label": "very_low",
            "observations": 0,
        }
