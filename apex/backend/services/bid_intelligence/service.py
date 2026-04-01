"""Business logic layer for Bid Intelligence (Estimation History)."""

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from apex.backend.services.bid_intelligence.models import BIEstimate
from apex.backend.services.bid_intelligence.parser import parse_estimation_history


class BidIntelligenceService:
    def __init__(self, db: Session):
        self.db = db

    # ── Ingestion ──

    def ingest_file(self, filepath: str, filename: str) -> dict:
        """Parse xlsx and upsert by estimate_number."""
        rows = parse_estimation_history(filepath)

        inserted = 0
        updated = 0
        errors = []

        for row in rows:
            est_num = row.get("estimate_number")
            if not est_num:
                errors.append(f"Row missing estimate_number: {row.get('name', '?')}")
                continue

            existing = self.db.query(BIEstimate).filter_by(estimate_number=est_num).first()
            if existing:
                for k, v in row.items():
                    if k != "estimate_number":
                        setattr(existing, k, v)
                updated += 1
            else:
                self.db.add(BIEstimate(**row))
                inserted += 1

        self.db.commit()

        return {
            "filename": filename,
            "total": len(rows),
            "inserted": inserted,
            "updated": updated,
            "errors": errors,
        }

    # ── Analytics ──

    def get_stats(self) -> dict:
        """Summary statistics across all estimates."""
        total = self.db.query(func.count(BIEstimate.id)).scalar() or 0

        by_status = dict(
            self.db.query(BIEstimate.status, func.count(BIEstimate.id))
            .filter(BIEstimate.status.isnot(None))
            .group_by(BIEstimate.status)
            .all()
        )

        awarded = by_status.get("Awarded", 0)
        closed = by_status.get("Closed", 0)
        bids_decided = awarded + closed
        hit_rate = round((awarded / bids_decided) * 100, 1) if bids_decided > 0 else 0.0

        avg_bid = self.db.query(func.avg(BIEstimate.bid_amount)).filter(
            BIEstimate.bid_amount.isnot(None)
        ).scalar()
        avg_contract = self.db.query(func.avg(BIEstimate.contract_amount)).filter(
            BIEstimate.contract_amount.isnot(None)
        ).scalar()

        return {
            "total_estimates": total,
            "by_status": by_status,
            "hit_rate": hit_rate,
            "avg_bid_amount": round(avg_bid, 2) if avg_bid else None,
            "avg_contract_amount": round(avg_contract, 2) if avg_contract else None,
        }

    def get_benchmarks(
        self,
        market_sector: str | None = None,
        region: str | None = None,
        estimator: str | None = None,
    ) -> dict:
        """Benchmark metrics, optionally filtered. All math is deterministic Python."""
        q = self.db.query(BIEstimate)

        if market_sector:
            q = q.filter(BIEstimate.market_sector == market_sector)
        if region:
            q = q.filter(BIEstimate.region == region)
        if estimator:
            q = q.filter(BIEstimate.estimator == estimator)

        rows = q.all()
        if not rows:
            return {
                "count": 0,
                "avg_cost_per_cy": None,
                "avg_cost_per_sf": None,
                "hit_rate": None,
            }

        # Compute $/CY and $/SF from rows with valid data
        cy_vals = [r.cost_per_cy for r in rows if r.cost_per_cy is not None]
        sf_vals = [r.cost_per_sf for r in rows if r.cost_per_sf is not None]

        awarded = sum(1 for r in rows if r.status == "Awarded")
        decided = sum(1 for r in rows if r.status in ("Awarded", "Closed"))
        hit_rate = round((awarded / decided) * 100, 1) if decided > 0 else None

        return {
            "count": len(rows),
            "avg_cost_per_cy": round(sum(cy_vals) / len(cy_vals), 2) if cy_vals else None,
            "avg_cost_per_sf": round(sum(sf_vals) / len(sf_vals), 2) if sf_vals else None,
            "hit_rate": hit_rate,
        }

    def get_comparable_projects(
        self,
        conc_vol_cy: float | None = None,
        building_sf: float | None = None,
        market_sector: str | None = None,
        limit: int = 5,
    ) -> list[dict]:
        """Find projects with similar volume/SF/sector, ordered by similarity.

        Similarity is a simple normalized distance across available dimensions.
        All math is deterministic Python.
        """
        q = self.db.query(BIEstimate).filter(BIEstimate.status == "Awarded")

        if market_sector:
            q = q.filter(BIEstimate.market_sector == market_sector)

        candidates = q.all()
        if not candidates:
            return []

        scored = []
        for r in candidates:
            dist = 0.0
            dims = 0

            if conc_vol_cy and r.conc_vol_cy and r.conc_vol_cy > 0:
                dist += abs(conc_vol_cy - r.conc_vol_cy) / max(conc_vol_cy, r.conc_vol_cy)
                dims += 1
            if building_sf and r.building_sf and r.building_sf > 0:
                dist += abs(building_sf - r.building_sf) / max(building_sf, r.building_sf)
                dims += 1

            similarity = 1.0 - (dist / dims) if dims > 0 else 0.0
            scored.append((similarity, r))

        scored.sort(key=lambda x: x[0], reverse=True)

        return [
            {
                "id": r.id,
                "name": r.name,
                "market_sector": r.market_sector,
                "bid_amount": r.bid_amount,
                "contract_amount": r.contract_amount,
                "conc_vol_cy": r.conc_vol_cy,
                "building_sf": r.building_sf,
                "cost_per_cy": r.cost_per_cy,
                "cost_per_sf": r.cost_per_sf,
                "similarity": round(sim, 3),
            }
            for sim, r in scored[:limit]
        ]

    def get_estimator_performance(self, estimator: str | None = None) -> list[dict]:
        """Hit rate, avg bid delta, total bids per estimator. Deterministic Python math."""
        q = self.db.query(BIEstimate).filter(BIEstimate.estimator.isnot(None))
        if estimator:
            q = q.filter(BIEstimate.estimator == estimator)

        rows = q.all()

        # Group by estimator in Python for precise control
        by_est: dict[str, list[BIEstimate]] = {}
        for r in rows:
            by_est.setdefault(r.estimator, []).append(r)

        results = []
        for est_name, est_rows in sorted(by_est.items()):
            total = len(est_rows)
            awarded = sum(1 for r in est_rows if r.status == "Awarded")
            decided = sum(1 for r in est_rows if r.status in ("Awarded", "Closed"))
            hit_rate = round((awarded / decided) * 100, 1) if decided > 0 else None

            deltas = [r.bid_delta_pct for r in est_rows if r.bid_delta_pct is not None]
            avg_delta = round(sum(deltas) / len(deltas), 1) if deltas else None

            results.append({
                "estimator": est_name,
                "total_bids": total,
                "awarded": awarded,
                "hit_rate": hit_rate,
                "avg_bid_delta_pct": avg_delta,
            })

        return results

    def get_hit_rate_by(self, group_by: str) -> list[dict]:
        """Hit rate grouped by market_sector, region, estimator, or delivery_method."""
        valid_fields = {
            "market_sector": BIEstimate.market_sector,
            "region": BIEstimate.region,
            "estimator": BIEstimate.estimator,
            "delivery_method": BIEstimate.delivery_method,
        }

        col = valid_fields.get(group_by)
        if col is None:
            return []

        rows = (
            self.db.query(
                col.label("group_value"),
                func.count(BIEstimate.id).label("total"),
                func.sum(case((BIEstimate.status == "Awarded", 1), else_=0)).label("awarded"),
                func.sum(
                    case((BIEstimate.status.in_(["Awarded", "Closed"]), 1), else_=0)
                ).label("decided"),
            )
            .filter(col.isnot(None))
            .group_by(col)
            .order_by(col)
            .all()
        )

        return [
            {
                "group": r.group_value,
                "total_bids": r.total,
                "awarded": r.awarded,
                "hit_rate": round((r.awarded / r.decided) * 100, 1) if r.decided > 0 else None,
            }
            for r in rows
        ]
