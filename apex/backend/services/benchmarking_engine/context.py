"""Project context model and similarity scoring.

Architecture §10: Historical pricing should never be retrieved without
filtering by context. Context filtering is the difference between
'historical noise' and 'decision-grade signal.'
"""

from dataclasses import dataclass, field
from typing import List, Optional
import json


@dataclass
class ProjectContext:
    """Mandatory context for benchmark retrieval. §10"""
    project_type: str                       # data_center, healthcare, education, warehouse, ...
    region: str                             # midwest, southeast, northeast, southwest, west
    market_sector: Optional[str] = None     # mission_critical, k12, higher_ed, ...
    size_sf: Optional[float] = None
    contract_type: Optional[str] = None     # self_perform, subcontract, mixed
    delivery_method: Optional[str] = None   # cmar, design_build, hard_bid, gmp
    scope_types: List[str] = field(default_factory=list)  # ["sitework", "concrete", ...]
    complexity_level: Optional[str] = None  # low | medium | high | very_high
    schedule_pressure: Optional[str] = None # low | medium | high | extreme

    def to_json(self) -> str:
        return json.dumps({
            "project_type": self.project_type,
            "region": self.region,
            "market_sector": self.market_sector,
            "size_sf": self.size_sf,
            "contract_type": self.contract_type,
            "delivery_method": self.delivery_method,
            "scope_types": self.scope_types,
            "complexity_level": self.complexity_level,
            "schedule_pressure": self.schedule_pressure,
        })

    @classmethod
    def from_project(cls, project) -> "ProjectContext":
        """Build context from a Project ORM object."""
        scope_types = []
        if project.scope_types:
            try:
                scope_types = json.loads(project.scope_types)
            except (ValueError, TypeError):
                scope_types = []
        return cls(
            project_type=project.project_type or "unknown",
            region=project.location or "unknown",
            market_sector=getattr(project, "market_sector", None),
            size_sf=project.square_footage,
            contract_type=getattr(project, "contract_type", None),
            delivery_method=getattr(project, "delivery_method", None),
            scope_types=scope_types,
            complexity_level=getattr(project, "complexity_level", None),
            schedule_pressure=getattr(project, "schedule_pressure", None),
        )


# ── Similarity scoring ───────────────────────────────────────────────────────

_COMPLEXITY_ORDER = {"low": 0, "medium": 1, "high": 2, "very_high": 3}
_SCHEDULE_ORDER = {"low": 0, "medium": 1, "high": 2, "extreme": 3}

# Size buckets (sf) — penalize comparables outside adjacent bucket
_SIZE_BUCKETS = [
    (0,       50_000),
    (50_000,  150_000),
    (150_000, 400_000),
    (400_000, 800_000),
    (800_000, float("inf")),
]


def _size_bucket(sf: float) -> int:
    for i, (lo, hi) in enumerate(_SIZE_BUCKETS):
        if lo <= sf < hi:
            return i
    return len(_SIZE_BUCKETS) - 1


def _scope_overlap(a: List[str], b: List[str]) -> float:
    if not a or not b:
        return 0.5  # unknown overlap → neutral
    sa, sb = set(a), set(b)
    intersection = sa & sb
    union = sa | sb
    return len(intersection) / len(union)  # Jaccard


def context_similarity_score(ctx: ProjectContext, comparable) -> float:
    """Compute 0–1 similarity between query context and a ComparableProject row.

    Weights (sum = 1.0):
      project_type   0.30  — most important: a hospital ≠ a warehouse
      region         0.20  — local labor and material markets
      scope_overlap  0.15  — shared work families
      market_sector  0.10
      size_bucket    0.10
      complexity     0.08
      schedule_press 0.07
    """
    score = 0.0

    # project_type (0.30)
    if comparable.project_type:
        score += 0.30 if comparable.project_type == ctx.project_type else 0.0

    # region (0.20)
    if comparable.region:
        score += 0.20 if comparable.region == ctx.region else 0.0

    # scope overlap (0.15)
    comp_scope = []
    if comparable.scope_types:
        try:
            comp_scope = json.loads(comparable.scope_types)
        except (ValueError, TypeError):
            comp_scope = []
    score += 0.15 * _scope_overlap(ctx.scope_types, comp_scope)

    # market_sector (0.10)
    if ctx.market_sector and comparable.market_sector:
        score += 0.10 if comparable.market_sector == ctx.market_sector else 0.0
    else:
        score += 0.05  # partial credit when either is unknown

    # size bucket (0.10)
    if ctx.size_sf and comparable.size_sf:
        qa = _size_bucket(ctx.size_sf)
        qb = _size_bucket(comparable.size_sf)
        diff = abs(qa - qb)
        score += 0.10 if diff == 0 else (0.05 if diff == 1 else 0.0)
    else:
        score += 0.05

    # complexity (0.08)
    if ctx.complexity_level and comparable.complexity_level:
        a = _COMPLEXITY_ORDER.get(ctx.complexity_level, 1)
        b = _COMPLEXITY_ORDER.get(comparable.complexity_level, 1)
        score += 0.08 if a == b else (0.04 if abs(a - b) == 1 else 0.0)
    else:
        score += 0.04

    # schedule_pressure (0.07)
    if ctx.schedule_pressure and getattr(comparable, "schedule_pressure", None):
        a = _SCHEDULE_ORDER.get(ctx.schedule_pressure, 1)
        b = _SCHEDULE_ORDER.get(comparable.schedule_pressure, 1)
        score += 0.07 if a == b else (0.035 if abs(a - b) == 1 else 0.0)
    else:
        score += 0.035

    return round(min(score, 1.0), 4)
