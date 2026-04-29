"""Business logic layer for Bid Intelligence (Estimation History)."""

import logging

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from apex.backend.services.library.bid_intelligence.models import BIEstimate
from apex.backend.services.library.bid_intelligence.parser import parse_estimation_history

logger = logging.getLogger("apex.library.bid_intelligence")

_CHUNK_SIZE = 250


class BidIntelligenceService:
    def __init__(self, db: Session):
        self.db = db

    # ── Ingestion ──

    def _truncate_existing(self) -> int:
        """DELETE all rows from bi_estimates and commit. Returns count deleted."""
        deleted = self.db.query(BIEstimate).delete()
        self.db.commit()
        logger.info(f"BI ingest: truncated bi_estimates (deleted {deleted} rows)")
        return deleted

    def ingest_file(self, filepath: str, filename: str) -> dict:
        """Parse xlsx and replace bi_estimates with the file's unique rows.

        Pre-flight order (nothing is written to DB until all checks pass):
          1. parse_estimation_history() — raises ValueError(422) on missing required cols
          2. Internal-duplicate detection — keeps first occurrence, logs skips
          3. _truncate_existing() — DELETE + commit (only reached after clean pre-flight)
          4. Chunked INSERT (250 rows per commit)

        A bad file will never wipe good data.
        """
        logger.info(f"BI ingest: received file='{filename}' path={filepath}")

        # Step 1: Parse — raises ValueError on missing required columns (→ 422).
        records, row_errors, found_headers = parse_estimation_history(filepath)

        # Step 2: Internal-duplicate detection (pre-flight, no DB writes yet).
        unique_records: list[dict] = []
        internal_duplicates: list[dict] = []
        seen: dict[str, int] = {}  # estimate_number → row_num of first occurrence

        for rec in records:
            row_num = rec.pop("_row_num", None)
            est_num = rec.get("estimate_number")

            if not est_num:
                # Null estimate_number rows flow through without dedup check.
                unique_records.append(rec)
                continue

            if est_num in seen:
                internal_duplicates.append({
                    "row": row_num,
                    "estimate_number": est_num,
                    "first_seen_row": seen[est_num],
                })
            else:
                seen[est_num] = row_num
                unique_records.append(rec)

        logger.info(
            f"BI ingest: pre-flight complete. parsed_rows={len(records)} "
            f"unique_rows={len(unique_records)} internal_duplicates={len(internal_duplicates)}"
        )

        # Step 3: Truncate AFTER successful pre-flight.
        previous_row_count = self._truncate_existing()

        # Step 4: Chunked insert — pure inserts (table is empty after truncate).
        loaded = 0
        commit_count = 0
        pending: list[BIEstimate] = []

        def _flush(chunk: list, start: int) -> None:
            nonlocal commit_count
            self.db.add_all(chunk)
            self.db.commit()
            commit_count += 1
            logger.info(
                f"BI ingest: committed chunk {commit_count}: "
                f"rows {start}..{start + len(chunk) - 1}"
            )

        try:
            chunk_start = 1
            for rec in unique_records:
                pending.append(BIEstimate(**rec))
                loaded += 1
                if len(pending) >= _CHUNK_SIZE:
                    _flush(pending, chunk_start)
                    chunk_start += len(pending)
                    pending = []
            if pending:
                _flush(pending, chunk_start)
        except Exception as exc:
            remaining = len(unique_records) - loaded
            logger.error(
                f"BI ingest: chunk commit failed after {loaded} rows "
                f"(~{remaining} remaining). Table in partial state. File: '{filename}'",
                exc_info=True,
            )
            return {
                "ok": False,
                "error": "partial_load_failure",
                "loaded_before_failure": loaded,
                "remaining": remaining,
                "message": (
                    "The bid intelligence table is in a partial state. "
                    "Please re-upload the file to retry."
                ),
            }

        skipped = len(row_errors)
        logger.info(
            f"BI ingest complete: file='{filename}' loaded={loaded} skipped={skipped} "
            f"internal_duplicates={len(internal_duplicates)} commits={commit_count}"
        )

        return {
            "ok": True,
            "loaded": loaded,
            "skipped": skipped,
            "internal_duplicates": internal_duplicates,
            "errors": row_errors[:50],
            "commits": commit_count,
            "replaced_existing": True,
            "previous_row_count": previous_row_count,
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

        avg_bid = self.db.query(func.avg(BIEstimate.bid_amount)).filter(BIEstimate.bid_amount.isnot(None)).scalar()
        avg_contract = (
            self.db.query(func.avg(BIEstimate.contract_amount)).filter(BIEstimate.contract_amount.isnot(None)).scalar()
        )

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

            results.append(
                {
                    "estimator": est_name,
                    "total_bids": total,
                    "awarded": awarded,
                    "hit_rate": hit_rate,
                    "avg_bid_delta_pct": avg_delta,
                }
            )

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
                func.sum(case((BIEstimate.status.in_(["Awarded", "Closed"]), 1), else_=0)).label("decided"),
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
