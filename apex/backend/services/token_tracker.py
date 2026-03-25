"""Token usage tracking service.

Call log_token_usage() immediately after any successful LLM call to persist
a TokenUsage record with the provider, model, token counts, and estimated cost.
"""

import logging
from sqlalchemy.orm import Session
from apex.backend.models.token_usage import TokenUsage, calculate_cost

logger = logging.getLogger("apex.token_tracker")


def log_token_usage(
    db: Session,
    project_id: int,
    agent_number: int,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    estimate_id: int | None = None,
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

    Returns:
        The persisted TokenUsage record.
    """
    cost = calculate_cost(model, input_tokens, output_tokens)
    record = TokenUsage(
        project_id=project_id,
        estimate_id=estimate_id,
        agent_number=agent_number,
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost=cost,
    )
    db.add(record)
    db.commit()
    logger.debug(
        "Token usage logged: project=%d agent=%d provider=%s model=%s "
        "in=%d out=%d cost=$%.6f",
        project_id, agent_number, provider, model,
        input_tokens, output_tokens, cost,
    )
    return record
