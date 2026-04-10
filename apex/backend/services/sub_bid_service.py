"""Subcontractor bid comparison service.

All math is deterministic Python — no LLM involved.
"""

import logging
import statistics
from typing import Optional

from sqlalchemy.orm import Session

from apex.backend.models.sub_bid import SubBidPackage, SubBid, SubBidLineItem

logger = logging.getLogger("apex.sub_bid")


def _tokenize(text: str) -> set[str]:
    """Simple word tokenizer for fuzzy matching."""
    return set(text.lower().split()) - {"", "the", "a", "an", "and", "or", "of", "for", "to", "in"}


def _token_overlap(a: str, b: str) -> float:
    """Compute Jaccard similarity between two strings' token sets."""
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


class SubBidService:
    def __init__(self, db: Session):
        self.db = db

    # ── CRUD ──────────────────────────────────────────────

    def create_package(
        self,
        project_id: int,
        trade: str,
        csi_division: Optional[str] = None,
        base_scope_items: Optional[list] = None,
    ) -> SubBidPackage:
        pkg = SubBidPackage(
            project_id=project_id,
            trade=trade,
            csi_division=csi_division,
            base_scope_items=base_scope_items,
        )
        self.db.add(pkg)
        self.db.commit()
        self.db.refresh(pkg)
        return pkg

    def add_bid(
        self,
        package_id: int,
        subcontractor_name: str,
        total_bid_amount: Optional[float] = None,
        line_items: Optional[list[dict]] = None,
    ) -> SubBid:
        bid = SubBid(
            package_id=package_id,
            subcontractor_name=subcontractor_name,
            total_bid_amount=total_bid_amount,
        )
        self.db.add(bid)
        self.db.flush()

        if line_items:
            for li in line_items:
                item = SubBidLineItem(
                    bid_id=bid.id,
                    description=li.get("description", ""),
                    quantity=li.get("quantity"),
                    unit=li.get("unit"),
                    unit_cost=li.get("unit_cost"),
                    total_cost=li.get("total_cost"),
                    csi_code=li.get("csi_code"),
                )
                self.db.add(item)

        self.db.commit()
        self.db.refresh(bid)
        return bid

    # ── Normalization ─────────────────────────────────────

    def normalize_bids(self, package_id: int) -> dict:
        """Fuzzy token-overlap matching of line items to base scope."""
        pkg = self.db.query(SubBidPackage).filter(SubBidPackage.id == package_id).first()
        if not pkg:
            return {"error": "Package not found"}

        base_items = pkg.base_scope_items or []
        bids = self.db.query(SubBid).filter(SubBid.package_id == package_id).all()
        matched_count = 0

        for bid in bids:
            items = self.db.query(SubBidLineItem).filter(SubBidLineItem.bid_id == bid.id).all()
            for item in items:
                best_match = None
                best_score = 0.0
                for base in base_items:
                    base_desc = base if isinstance(base, str) else base.get("description", "")
                    score = _token_overlap(item.description, base_desc)
                    if score > best_score:
                        best_score = score
                        best_match = base_desc

                if best_score >= 0.3:
                    item.matched_scope_item = best_match
                    item.match_confidence = round(best_score, 3)
                    matched_count += 1

            bid.normalized = True

        self.db.commit()
        return {"package_id": package_id, "bids_normalized": len(bids), "items_matched": matched_count}

    # ── Comparison ────────────────────────────────────────

    def compare_bids(self, package_id: int) -> dict:
        """IQR outlier detection, suspiciously-low flagging, missing item detection, price matrix."""
        bids = self.db.query(SubBid).filter(SubBid.package_id == package_id).all()
        if len(bids) < 2:
            return {"error": "Need at least 2 bids to compare"}

        # Build price matrix: {description: {sub_name: total_cost}}
        price_matrix: dict[str, dict[str, Optional[float]]] = {}
        all_descriptions: set[str] = set()

        for bid in bids:
            items = self.db.query(SubBidLineItem).filter(SubBidLineItem.bid_id == bid.id).all()
            for item in items:
                desc = item.matched_scope_item or item.description
                all_descriptions.add(desc)
                price_matrix.setdefault(desc, {})[bid.subcontractor_name] = item.total_cost

        # Missing items per bid
        missing_items: dict[str, list[str]] = {}
        for bid in bids:
            items = self.db.query(SubBidLineItem).filter(SubBidLineItem.bid_id == bid.id).all()
            bid_descs = {it.matched_scope_item or it.description for it in items}
            missing = all_descriptions - bid_descs
            if missing:
                missing_items[bid.subcontractor_name] = sorted(missing)

        # Outlier detection using IQR on total bid amounts
        totals = [b.total_bid_amount for b in bids if b.total_bid_amount is not None]
        outlier_bids: list[str] = []
        low_bids: list[str] = []

        if len(totals) >= 3:
            sorted_totals = sorted(totals)
            q1 = sorted_totals[len(sorted_totals) // 4]
            q3 = sorted_totals[3 * len(sorted_totals) // 4]
            iqr = q3 - q1
            lower_fence = q1 - 1.5 * iqr
            upper_fence = q3 + 1.5 * iqr
            median = statistics.median(totals)

            for bid in bids:
                if bid.total_bid_amount is not None:
                    if bid.total_bid_amount < lower_fence or bid.total_bid_amount > upper_fence:
                        outlier_bids.append(bid.subcontractor_name)
                    if bid.total_bid_amount < median * 0.6:
                        low_bids.append(bid.subcontractor_name)

        # Flag line-item outliers
        for desc, prices in price_matrix.items():
            values = [v for v in prices.values() if v is not None]
            if len(values) < 2:
                continue
            median_val = statistics.median(values)
            for bid in bids:
                items = (
                    self.db.query(SubBidLineItem)
                    .filter(SubBidLineItem.bid_id == bid.id)
                    .all()
                )
                for item in items:
                    item_desc = item.matched_scope_item or item.description
                    if item_desc == desc and item.total_cost is not None:
                        if median_val > 0 and item.total_cost < median_val * 0.6:
                            item.is_suspiciously_low = True
                        if len(values) >= 3:
                            sv = sorted(values)
                            q1 = sv[len(sv) // 4]
                            q3 = sv[3 * len(sv) // 4]
                            iqr = q3 - q1
                            if item.total_cost < q1 - 1.5 * iqr or item.total_cost > q3 + 1.5 * iqr:
                                item.is_outlier = True

        self.db.commit()

        return {
            "package_id": package_id,
            "bid_count": len(bids),
            "bid_summary": [
                {
                    "subcontractor": b.subcontractor_name,
                    "total_bid_amount": b.total_bid_amount,
                    "is_outlier": b.subcontractor_name in outlier_bids,
                    "is_suspiciously_low": b.subcontractor_name in low_bids,
                }
                for b in bids
            ],
            "missing_items": missing_items,
            "price_matrix": price_matrix,
            "outlier_bids": outlier_bids,
            "suspiciously_low_bids": low_bids,
        }
