"""Contextual Benchmarking Engine — retrieves historical rates filtered by project
context similarity and computes percentile distributions with confidence scoring.

No LLM calls — all math is deterministic Python.
"""

import statistics
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from apex.backend.models.decision_models import (
    ComparableProject,
    HistoricalRateObservation,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONTEXT_WEIGHTS = {
    "project_type":    0.25,
    "market_sector":   0.15,
    "region":          0.20,
    "delivery_method": 0.10,
    "contract_type":   0.10,
    "complexity_level":0.10,
    "size_bucket":     0.10,
}

_STOP_WORDS = {
    "the", "and", "for", "with", "per", "each", "all", "new", "in", "of",
    "to", "at", "on", "by", "an", "a",
}


# ---------------------------------------------------------------------------
# Helper: size bucket
# ---------------------------------------------------------------------------

def _size_bucket(size_sf: Optional[float]) -> Optional[str]:
    if size_sf is None:
        return None
    if size_sf < 10_000:
        return "small"
    if size_sf < 50_000:
        return "medium"
    if size_sf < 200_000:
        return "large"
    return "very_large"


# ---------------------------------------------------------------------------
# Context similarity scoring
# ---------------------------------------------------------------------------

def score_context_similarity(project, comparable: ComparableProject) -> float:
    """Return 0-1 similarity score between a project and a comparable project."""
    score = 0.0

    def _dim(proj_val, comp_val, weight: float) -> float:
        pv = (proj_val or "").strip().lower() if proj_val else None
        cv = (comp_val or "").strip().lower() if comp_val else None
        if pv and cv:
            return weight * 1.0 if pv == cv else 0.0
        # Both unknown/None
        if not pv and not cv:
            return weight * 0.3
        return 0.0

    score += _dim(
        getattr(project, "project_type", None),
        comparable.project_type,
        CONTEXT_WEIGHTS["project_type"],
    )
    score += _dim(
        getattr(project, "market_sector", None),
        comparable.market_sector,
        CONTEXT_WEIGHTS["market_sector"],
    )
    score += _dim(
        getattr(project, "region", None),
        comparable.region,
        CONTEXT_WEIGHTS["region"],
    )
    score += _dim(
        getattr(project, "delivery_method", None),
        comparable.delivery_method,
        CONTEXT_WEIGHTS["delivery_method"],
    )
    score += _dim(
        getattr(project, "contract_type", None),
        comparable.contract_type,
        CONTEXT_WEIGHTS["contract_type"],
    )
    score += _dim(
        getattr(project, "complexity_level", None),
        comparable.complexity_level,
        CONTEXT_WEIGHTS["complexity_level"],
    )

    # Size bucket comparison
    proj_bucket = _size_bucket(getattr(project, "size_sf", None))
    comp_bucket = _size_bucket(comparable.size_sf)
    score += _dim(proj_bucket, comp_bucket, CONTEXT_WEIGHTS["size_bucket"])

    return min(score, 1.0)


def _recency_score(comparable: ComparableProject) -> float:
    """Score 0-1 based on how recently a comparable project was completed."""
    if comparable.completed_date is None:
        return 0.3
    now = datetime.now(timezone.utc)
    cd = comparable.completed_date
    if cd.tzinfo is None:
        cd = cd.replace(tzinfo=timezone.utc)
    years = (now - cd).days / 365.25
    if years < 1:
        return 1.0
    if years < 2:
        return 0.8
    if years < 4:
        return 0.6
    return 0.3


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------

def compute_confidence(
    sample_size: int,
    std_dev: float,
    mean: float,
    avg_context_sim: float,
    avg_recency: float,
    avg_data_quality: float,
) -> tuple[float, str]:
    """Return (confidence_score 0-1, confidence_label)."""
    # CoV component — lower spread = higher confidence
    if mean and mean > 0:
        cov_component = max(0.0, 1.0 - min(std_dev / mean, 1.0))
    else:
        cov_component = 0.0

    score = (
        0.30 * min(sample_size / 10.0, 1.0)
        + 0.25 * cov_component
        + 0.20 * avg_context_sim
        + 0.15 * avg_recency
        + 0.10 * avg_data_quality
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
# Benchmarking Engine
# ---------------------------------------------------------------------------

class BenchmarkingEngine:
    def __init__(self, db: Session):
        self.db = db

    def get_comparable_projects(
        self,
        project,
        min_similarity: float = 0.0,
    ) -> list[tuple[ComparableProject, float]]:
        """Return [(comparable_project, similarity_score)] sorted descending."""
        comparables = self.db.query(ComparableProject).all()
        scored = []
        for c in comparables:
            sim = score_context_similarity(project, c)
            if sim >= min_similarity:
                scored.append((c, sim))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def benchmark_activity(
        self,
        project,
        activity_name: str,
        division_code: Optional[str] = None,
        comparable_projects: Optional[list] = None,
    ) -> dict:
        """Retrieve and analyse historical rates for one activity."""
        if comparable_projects is None:
            comparable_projects = self.get_comparable_projects(project, min_similarity=0.0)

        if not comparable_projects:
            return self._empty_benchmark(activity_name, division_code)

        comp_ids = [c.id for c, _ in comparable_projects]
        sim_by_id = {c.id: sim for c, sim in comparable_projects}

        # Base query — unit_cost must be present
        base_q = (
            self.db.query(HistoricalRateObservation)
            .filter(
                HistoricalRateObservation.comparable_project_id.in_(comp_ids),
                HistoricalRateObservation.unit_cost.isnot(None),
            )
        )

        # Matching strategy: try each in order, stop at first with results
        observations = self._match_strategy_1(base_q, activity_name)
        if not observations:
            observations = self._match_strategy_2(base_q, activity_name)
        if not observations and division_code:
            observations = self._match_strategy_3(base_q, activity_name, division_code)

        if not observations:
            return self._empty_benchmark(activity_name, division_code)

        costs = sorted([o.unit_cost for o in observations])
        n = len(costs)

        mean_val = statistics.mean(costs)
        std_dev = statistics.stdev(costs) if n > 1 else 0.0
        p25 = costs[max(0, int(n * 0.25) - 1)] if n > 1 else costs[0]
        p50 = statistics.median(costs)
        p75 = costs[min(n - 1, int(n * 0.75))]
        p90 = costs[min(n - 1, int(n * 0.90))]

        obs_sim = [sim_by_id.get(o.comparable_project_id, 0.0) for o in observations]
        obs_recency = []
        obs_quality = []
        for o in observations:
            comp = next((c for c, _ in comparable_projects if c.id == o.comparable_project_id), None)
            if comp:
                obs_recency.append(_recency_score(comp))
                obs_quality.append(comp.data_quality_score or 0.5)
            else:
                obs_recency.append(0.3)
                obs_quality.append(0.5)

        avg_sim = statistics.mean(obs_sim) if obs_sim else 0.0
        avg_recency = statistics.mean(obs_recency) if obs_recency else 0.3
        avg_quality = statistics.mean(obs_quality) if obs_quality else 0.5

        conf_score, conf_label = compute_confidence(
            n, std_dev, mean_val, avg_sim, avg_recency, avg_quality
        )

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
            "confidence_score": conf_score,
            "confidence_label": conf_label,
            "observations": [
                {
                    "id": o.id,
                    "comparable_project_id": o.comparable_project_id,
                    "raw_activity_name": o.raw_activity_name,
                    "unit_cost": o.unit_cost,
                    "unit": o.unit,
                    "production_rate": o.production_rate,
                    "context_similarity": round(sim_by_id.get(o.comparable_project_id, 0.0), 4),
                }
                for o in observations
            ],
        }

    def benchmark_all_quantities(self, project, quantities_list: list) -> list[dict]:
        """Benchmark a list of quantity dicts, reusing comparable projects query."""
        comparable_projects = self.get_comparable_projects(project, min_similarity=0.0)
        results = []
        for qty in quantities_list:
            result = self.benchmark_activity(
                project,
                activity_name=qty.get("description", ""),
                division_code=qty.get("division_code"),
                comparable_projects=comparable_projects,
            )
            results.append(result)
        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _match_strategy_1(self, base_q, activity_name: str):
        """Full name substring match (case-insensitive)."""
        return (
            base_q.filter(
                HistoricalRateObservation.raw_activity_name.ilike(f"%{activity_name}%")
            ).all()
        )

    def _match_strategy_2(self, base_q, activity_name: str):
        """Top 3 longest keyword tokens all matching."""
        tokens = self._keyword_tokens(activity_name, top_n=3)
        if not tokens:
            return []
        q = base_q
        for token in tokens:
            q = q.filter(
                HistoricalRateObservation.raw_activity_name.ilike(f"%{token}%")
            )
        return q.all()

    def _match_strategy_3(self, base_q, activity_name: str, division_code: str):
        """Top 2 keywords + division_code filter."""
        tokens = self._keyword_tokens(activity_name, top_n=2)
        if not tokens:
            return []
        q = base_q.filter(
            HistoricalRateObservation.division_code == division_code
        )
        for token in tokens:
            q = q.filter(
                HistoricalRateObservation.raw_activity_name.ilike(f"%{token}%")
            )
        return q.all()

    def _keyword_tokens(self, text: str, top_n: int) -> list[str]:
        """Return top N longest meaningful tokens from text."""
        words = text.lower().replace("—", " ").replace("-", " ").split()
        filtered = [w for w in words if w not in _STOP_WORDS and len(w) > 2]
        # Sort by length descending to get most specific terms first
        filtered.sort(key=len, reverse=True)
        return filtered[:top_n]

    def _empty_benchmark(self, activity_name: str, division_code: Optional[str]) -> dict:
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
            "observations": [],
        }
