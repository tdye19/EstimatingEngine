"""Token usage tracking service.

Call log_token_usage() immediately after any successful LLM call to persist
a TokenUsage record with the provider, model, token counts, and estimated cost.
"""

import logging
import os

from sqlalchemy import func
from sqlalchemy.orm import Session

from apex.backend.models.token_usage import TokenUsage, calculate_cost

logger = logging.getLogger("apex.token_tracker")

# Budget constants — configurable via env vars.
# New names (PROJECT_TOKEN_LIMIT / PROJECT_COST_LIMIT) take priority;
# old names (PROJECT_TOKEN_BUDGET / PROJECT_COST_BUDGET) are kept for back-compat.
PROJECT_TOKEN_BUDGET = int(os.getenv("PROJECT_TOKEN_LIMIT") or os.getenv("PROJECT_TOKEN_BUDGET") or str(20_000_000))
PROJECT_COST_BUDGET = float(os.getenv("PROJECT_COST_LIMIT") or os.getenv("PROJECT_COST_BUDGET") or "100.0")

_BUDGET_WARN_THRESHOLD = 0.80  # emit WARNING when usage reaches 80% of either limit


class TokenBudgetExceeded(Exception):
    """Raised when a project exceeds its token or cost budget."""

    def __init__(
        self,
        project_id: int,
        tokens_used: int,
        cost_used: float,
        document_name: str | None = None,
        docs_remaining: int = 0,
    ):
        self.project_id = project_id
        self.tokens_used = tokens_used
        self.cost_used = cost_used
        self.document_name = document_name
        self.docs_remaining = docs_remaining
        doc_info = f" (triggered by: {document_name})" if document_name else ""
        remaining_info = f", {docs_remaining} document(s) unprocessed" if docs_remaining else ""
        super().__init__(
            f"Project {project_id} budget exceeded: "
            f"{tokens_used:,} tokens (limit {PROJECT_TOKEN_BUDGET:,}), "
            f"${cost_used:.2f} cost (limit ${PROJECT_COST_BUDGET:.2f})"
            f"{doc_info}{remaining_info}"
        )


def check_token_budget(db: Session, project_id: int) -> None:
    """Check cumulative token usage for a project and raise if over budget."""
    row = (
        db.query(
            func.coalesce(func.sum(TokenUsage.input_tokens + TokenUsage.output_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(TokenUsage.estimated_cost), 0.0).label("total_cost"),
        )
        .filter(TokenUsage.project_id == project_id)
        .first()
    )

    total_tokens = int(row.total_tokens)
    total_cost = float(row.total_cost)

    token_pct = total_tokens / PROJECT_TOKEN_BUDGET
    cost_pct = total_cost / PROJECT_COST_BUDGET
    if token_pct >= _BUDGET_WARN_THRESHOLD or cost_pct >= _BUDGET_WARN_THRESHOLD:
        logger.warning(
            "Project %d budget at %.0f%% tokens (%s/%s), %.0f%% cost ($%.2f/$%.2f)",
            project_id,
            token_pct * 100,
            f"{total_tokens:,}",
            f"{PROJECT_TOKEN_BUDGET:,}",
            cost_pct * 100,
            total_cost,
            PROJECT_COST_BUDGET,
        )

    if total_tokens >= PROJECT_TOKEN_BUDGET or total_cost >= PROJECT_COST_BUDGET:
        raise TokenBudgetExceeded(project_id, total_tokens, total_cost)


def log_token_usage(
    db: Session,
    project_id: int,
    agent_number: int,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    estimate_id: int | None = None,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> TokenUsage:
    """Create and persist a TokenUsage record for one LLM call.

    Args:
        db:           Active database session.
        project_id:   Project this call belongs to.
        agent_number: Which agent (2-7) made the call.
        provider:     Provider name ("anthropic", "gemini", "ollama").
        model:        Full model ID string from LLMResponse.model.
        input_tokens: Prompt token count from LLMResponse.input_tokens.
        output_tokens: Completion token count from LLMResponse.output_tokens.
        estimate_id:  Optional FK to the estimate being assembled (Agent 6).
        cache_creation_tokens: Tokens written to Anthropic prompt cache.
        cache_read_tokens:     Tokens read from Anthropic prompt cache.

    Returns:
        The persisted TokenUsage record.
    """
    check_token_budget(db, project_id)
    cost = calculate_cost(model, input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens)
    record = TokenUsage(
        project_id=project_id,
        estimate_id=estimate_id,
        agent_number=agent_number,
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_tokens=cache_creation_tokens,
        cache_read_tokens=cache_read_tokens,
        estimated_cost=cost,
    )
    db.add(record)
    db.commit()
    logger.debug(
        "Token usage logged: project=%d agent=%d provider=%s model=%s "
        "in=%d out=%d cache_create=%d cache_read=%d cost=$%.6f",
        project_id,
        agent_number,
        provider,
        model,
        input_tokens,
        output_tokens,
        cache_creation_tokens,
        cache_read_tokens,
        cost,
    )
    return record
