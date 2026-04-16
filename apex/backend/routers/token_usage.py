"""Token usage and cost tracking API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apex.backend.db.database import get_db
from apex.backend.models.token_usage import AGENT_LABELS, TokenUsage, calculate_cost
from apex.backend.utils.auth import require_auth
from apex.backend.utils.feature_flags import feature_visible
from apex.backend.utils.schemas import APIResponse

router = APIRouter(prefix="/api", tags=["token-usage"], dependencies=[Depends(require_auth)])


@router.get("/projects/{project_id}/token-usage", response_model=APIResponse)
def get_project_token_usage(
    project_id: int,
    db: Session = Depends(get_db),
):
    """Return all TokenUsage records for a project, newest first."""
    if not feature_visible("cost_tracking"):
        raise HTTPException(404, detail="Feature not available in demo mode")
    records = (
        db.query(TokenUsage)
        .filter(
            TokenUsage.project_id == project_id,
            TokenUsage.is_deleted == False,  # noqa: E712
        )
        .order_by(TokenUsage.created_at.desc())
        .all()
    )

    data = [
        {
            "id": r.id,
            "agent_number": r.agent_number,
            "agent_name": AGENT_LABELS.get(r.agent_number, f"Agent {r.agent_number}"),
            "provider": r.provider,
            "model": r.model,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "total_tokens": r.input_tokens + r.output_tokens,
            "cache_creation_tokens": r.cache_creation_tokens or 0,
            "cache_read_tokens": r.cache_read_tokens or 0,
            "estimated_cost": r.estimated_cost,
            "estimate_id": r.estimate_id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in records
    ]

    return APIResponse(
        success=True,
        message=f"Found {len(data)} token usage records",
        data=data,
    )


@router.get("/token-usage/summary", response_model=APIResponse)
def get_token_usage_summary(
    project_id: int | None = None,
    db: Session = Depends(get_db),
):
    """Return aggregate token usage stats.

    Optional query param ?project_id=N filters to a single project.
    """
    if not feature_visible("cost_tracking"):
        raise HTTPException(404, detail="Feature not available in demo mode")
    base_q = db.query(TokenUsage).filter(TokenUsage.is_deleted == False)  # noqa: E712
    if project_id is not None:
        base_q = base_q.filter(TokenUsage.project_id == project_id)

    records = base_q.all()

    total_cost = sum(r.estimated_cost for r in records)
    total_input = sum(r.input_tokens for r in records)
    total_output = sum(r.output_tokens for r in records)
    total_cache_creation = sum(r.cache_creation_tokens or 0 for r in records)
    total_cache_read = sum(r.cache_read_tokens or 0 for r in records)

    # Cost by agent
    agent_agg: dict[int, dict] = {}
    for r in records:
        entry = agent_agg.setdefault(
            r.agent_number,
            {
                "agent_number": r.agent_number,
                "agent_name": AGENT_LABELS.get(r.agent_number, f"Agent {r.agent_number}"),
                "total_cost": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
                "call_count": 0,
            },
        )
        entry["total_cost"] = round(entry["total_cost"] + r.estimated_cost, 8)
        entry["input_tokens"] += r.input_tokens
        entry["output_tokens"] += r.output_tokens
        entry["call_count"] += 1

    # Cost by provider
    provider_agg: dict[str, dict] = {}
    for r in records:
        entry = provider_agg.setdefault(
            r.provider,
            {
                "provider": r.provider,
                "total_cost": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
                "call_count": 0,
            },
        )
        entry["total_cost"] = round(entry["total_cost"] + r.estimated_cost, 8)
        entry["input_tokens"] += r.input_tokens
        entry["output_tokens"] += r.output_tokens
        entry["call_count"] += 1

    # Cache savings = what you would have paid at full price for cache_read tokens
    # minus what you actually paid (0.1x). Savings = 0.9x full price of cache_read tokens.
    cache_savings = sum(
        calculate_cost(r.model, r.cache_read_tokens or 0, 0) * 0.9 for r in records if (r.cache_read_tokens or 0) > 0
    )

    return APIResponse(
        success=True,
        message="Token usage summary",
        data={
            "total_cost": round(total_cost, 6),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_cache_creation_tokens": total_cache_creation,
            "total_cache_read_tokens": total_cache_read,
            "cache_savings": round(cache_savings, 6),
            "total_calls": len(records),
            "by_agent": sorted(agent_agg.values(), key=lambda x: x["agent_number"]),
            "by_provider": sorted(provider_agg.values(), key=lambda x: x["total_cost"], reverse=True),
        },
    )
