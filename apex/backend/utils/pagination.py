"""Reusable pagination utility for collection endpoints."""

from sqlalchemy.orm import Query

MAX_LIMIT = 500


def paginate_query(query: Query, offset: int = 0, limit: int = 100) -> dict:
    """Apply offset/limit to a SQLAlchemy query and return paginated envelope.

    Returns ``{"items": [...], "total": N, "offset": offset, "limit": limit}``.
    """
    limit = min(max(limit, 1), MAX_LIMIT)
    offset = max(offset, 0)

    total = query.count()
    items = query.offset(offset).limit(limit).all()

    return {
        "items": items,
        "total": total,
        "offset": offset,
        "limit": limit,
    }
