"""BenchmarkEngine service — aggregates HistoricalLineItems into ProductivityBenchmark records."""

import json
import math
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from apex.backend.models.historical_line_item import HistoricalLineItem
from apex.backend.models.estimate_library import EstimateLibraryEntry
from apex.backend.models.productivity_benchmark import ProductivityBenchmark
from apex.backend.utils.schemas import BenchmarkQuery

# Items older than this many years get a decayed recency factor
_RECENCY_DECAY_YEARS = 2


def _recency_factor(bid_date: Optional[object], now: datetime) -> float:
    """Return a 0.0–1.0 recency weight; items within 2 years score 1.0, older items decay linearly."""
    if bid_date is None:
        return 0.5  # unknown age — neutral weight
    # bid_date may be a date or datetime
    if hasattr(bid_date, "year") and not isinstance(bid_date, datetime):
        bid_dt = datetime(bid_date.year, bid_date.month, bid_date.day, tzinfo=timezone.utc)
    else:
        bid_dt = bid_date.replace(tzinfo=timezone.utc) if bid_date.tzinfo is None else bid_date
    age_years = (now - bid_dt).days / 365.25
    if age_years <= _RECENCY_DECAY_YEARS:
        return 1.0
    # Linear decay: 0.0 at 4 years, 1.0 at 2 years
    return max(0.0, 1.0 - (age_years - _RECENCY_DECAY_YEARS) / _RECENCY_DECAY_YEARS)


def _std_dev(values: List[float]) -> Optional[float]:
    n = len(values)
    if n < 2:
        return None
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    return math.sqrt(variance)


def _safe_avg(values: List[Optional[float]]) -> Optional[float]:
    non_null = [v for v in values if v is not None]
    return sum(non_null) / len(non_null) if non_null else None


def compute_benchmarks(
    db: Session,
    organization_id: int,
    filters: Optional[BenchmarkQuery] = None,
) -> List[ProductivityBenchmark]:
    """
    Aggregate HistoricalLineItems into ProductivityBenchmark records and upsert them.

    Groups by (csi_code, unit_of_measure) and optionally by project_type and region
    when those fields are populated on the line items.
    """
    now = datetime.now(tz=timezone.utc)

    # ── 1. Fetch relevant line items ──────────────────────────────────────────
    q = (
        db.query(HistoricalLineItem)
        .join(EstimateLibraryEntry, HistoricalLineItem.library_entry_id == EstimateLibraryEntry.id)
        .filter(
            EstimateLibraryEntry.organization_id == organization_id,
            HistoricalLineItem.csi_code.isnot(None),
            HistoricalLineItem.unit_of_measure.isnot(None),
            HistoricalLineItem.unit_cost.isnot(None),
            HistoricalLineItem.quantity > 0,
        )
    )
    if filters:
        if filters.csi_division:
            q = q.filter(HistoricalLineItem.csi_division == int(filters.csi_division))
        if filters.csi_code:
            q = q.filter(HistoricalLineItem.csi_code == filters.csi_code)
        if filters.project_type:
            q = q.filter(HistoricalLineItem.project_type == filters.project_type)
        if filters.region:
            q = q.filter(HistoricalLineItem.location_state == filters.region)
        if filters.unit_of_measure:
            q = q.filter(HistoricalLineItem.unit_of_measure == filters.unit_of_measure)

    items: List[HistoricalLineItem] = q.all()

    # ── 2. Group in Python ────────────────────────────────────────────────────
    # Key: (csi_code, unit_of_measure, project_type or None, region or None)
    groups: dict = {}
    for item in items:
        key = (
            item.csi_code,
            item.unit_of_measure,
            item.project_type or None,
            item.location_state or None,
        )
        groups.setdefault(key, []).append(item)

    upserted: List[ProductivityBenchmark] = []

    # ── 3. Compute stats per group ────────────────────────────────────────────
    for (csi_code, uom, project_type, region), group_items in groups.items():
        unit_costs = [i.unit_cost for i in group_items if i.unit_cost is not None]
        if not unit_costs:
            continue

        sample_size = len(unit_costs)
        avg_unit_cost = sum(unit_costs) / sample_size
        min_unit_cost = min(unit_costs)
        max_unit_cost = max(unit_costs)
        std = _std_dev(unit_costs)

        # Per-type cost averages (divide by quantity to get per-unit)
        def _per_unit(cost_attr: str) -> Optional[float]:
            vals = []
            for i in group_items:
                raw = getattr(i, cost_attr)
                if raw is not None and i.quantity and i.quantity > 0:
                    vals.append(raw / i.quantity)
            return _safe_avg(vals)

        avg_labor = _per_unit("labor_cost")
        avg_material = _per_unit("material_cost")
        avg_equipment = _per_unit("equipment_cost")
        avg_sub = _per_unit("subcontractor_cost")
        avg_lh = _per_unit("labor_hours")

        # Confidence score
        recency_weights = [_recency_factor(i.bid_date, now) for i in group_items]
        avg_recency = sum(recency_weights) / len(recency_weights)
        confidence = min(1.0, sample_size / 20) * avg_recency

        if filters and filters.min_confidence and confidence < filters.min_confidence:
            continue
        if filters and filters.min_sample_size and sample_size < filters.min_sample_size:
            continue

        # Collect contributing project IDs
        project_ids = sorted({
            i.project_id for i in group_items if i.project_id is not None
        })

        # Description: use the most-common description in the group
        desc_counts: dict = {}
        for i in group_items:
            desc_counts[i.description] = desc_counts.get(i.description, 0) + 1
        description = max(desc_counts, key=desc_counts.get)

        # CSI division from first two numeric chars of csi_code
        csi_division = csi_code.split(" ")[0][:2] if csi_code else "00"

        # ── 4. Upsert ─────────────────────────────────────────────────────────
        existing: Optional[ProductivityBenchmark] = (
            db.query(ProductivityBenchmark)
            .filter(
                ProductivityBenchmark.organization_id == organization_id,
                ProductivityBenchmark.csi_code == csi_code,
                ProductivityBenchmark.unit_of_measure == uom,
                ProductivityBenchmark.project_type == project_type,
                ProductivityBenchmark.region == region,
                ProductivityBenchmark.is_deleted.is_(False),
            )
            .first()
        )

        if existing:
            record = existing
        else:
            record = ProductivityBenchmark(
                organization_id=organization_id,
                csi_code=csi_code,
                csi_division=csi_division,
                unit_of_measure=uom,
                project_type=project_type,
                region=region,
            )
            db.add(record)

        record.description = description
        record.avg_unit_cost = avg_unit_cost
        record.avg_labor_cost_per_unit = avg_labor
        record.avg_material_cost_per_unit = avg_material
        record.avg_equipment_cost_per_unit = avg_equipment
        record.avg_sub_cost_per_unit = avg_sub
        record.avg_labor_hours_per_unit = avg_lh
        record.min_unit_cost = min_unit_cost
        record.max_unit_cost = max_unit_cost
        record.std_dev = std
        record.sample_size = sample_size
        record.confidence_score = confidence
        record.last_computed_at = now
        record.source_project_ids = json.dumps(project_ids)

        upserted.append(record)

    db.commit()
    for r in upserted:
        db.refresh(r)

    return upserted


def query_benchmarks(
    db: Session,
    organization_id: int,
    csi_code: str,
    unit_of_measure: str,
    project_type: Optional[str] = None,
    region: Optional[str] = None,
) -> Optional[ProductivityBenchmark]:
    """
    Return the most-specific active benchmark for the given parameters,
    falling back through progressively looser matches.
    """
    base = (
        db.query(ProductivityBenchmark)
        .filter(
            ProductivityBenchmark.organization_id == organization_id,
            ProductivityBenchmark.unit_of_measure == unit_of_measure,
            ProductivityBenchmark.is_deleted.is_(False),
        )
    )

    # Level 1: exact match
    match = base.filter(
        ProductivityBenchmark.csi_code == csi_code,
        ProductivityBenchmark.project_type == project_type,
        ProductivityBenchmark.region == region,
    ).first()
    if match:
        return match

    # Level 2: code + UOM + project_type (no region)
    if project_type is not None or region is not None:
        match = base.filter(
            ProductivityBenchmark.csi_code == csi_code,
            ProductivityBenchmark.project_type == project_type,
            ProductivityBenchmark.region.is_(None),
        ).first()
        if match:
            return match

    # Level 3: code + UOM only
    match = base.filter(
        ProductivityBenchmark.csi_code == csi_code,
        ProductivityBenchmark.project_type.is_(None),
        ProductivityBenchmark.region.is_(None),
    ).first()
    if match:
        return match

    # Level 4: division + UOM
    if csi_code:
        division = csi_code.split(" ")[0][:2]
        match = (
            db.query(ProductivityBenchmark)
            .filter(
                ProductivityBenchmark.organization_id == organization_id,
                ProductivityBenchmark.csi_division == division,
                ProductivityBenchmark.unit_of_measure == unit_of_measure,
                ProductivityBenchmark.csi_code.is_(None),
                ProductivityBenchmark.is_deleted.is_(False),
            )
            .first()
        )
        if match:
            return match

    return None


def get_benchmark_summary(db: Session, organization_id: int) -> dict:
    """Return summary stats for all benchmarks belonging to the organization."""
    base_filter = and_(
        ProductivityBenchmark.organization_id == organization_id,
        ProductivityBenchmark.is_deleted.is_(False),
    )

    total = db.query(func.count(ProductivityBenchmark.id)).filter(base_filter).scalar() or 0

    # Coverage by division: {division: count}
    division_rows = (
        db.query(ProductivityBenchmark.csi_division, func.count(ProductivityBenchmark.id))
        .filter(base_filter)
        .group_by(ProductivityBenchmark.csi_division)
        .all()
    )
    coverage_by_division = {div: cnt for div, cnt in division_rows}

    avg_sample = (
        db.query(func.avg(ProductivityBenchmark.sample_size))
        .filter(base_filter)
        .scalar()
    )
    avg_sample_size = round(float(avg_sample), 1) if avg_sample is not None else 0.0

    last_computed = (
        db.query(func.max(ProductivityBenchmark.last_computed_at))
        .filter(base_filter)
        .scalar()
    )

    return {
        "total_benchmarks": total,
        "coverage_by_division": coverage_by_division,
        "avg_sample_size": avg_sample_size,
        "last_computed_at": last_computed.isoformat() if last_computed else None,
    }
