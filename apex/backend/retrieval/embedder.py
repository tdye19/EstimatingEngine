"""OpenAI text-embedding-3-small embedder.

Uses httpx (already in requirements) — no openai package needed.
Falls back gracefully when OPENAI_API_KEY is not configured.
"""

import logging
import os

import httpx

logger = logging.getLogger("apex.retrieval.embedder")

EMBEDDING_MODEL = "text-embedding-3-small"
OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"
EMBED_BATCH_SIZE = 100           # OpenAI allows up to 2048 inputs per call
REQUEST_TIMEOUT = 30.0           # seconds


def _api_key() -> str | None:
    return os.getenv("OPENAI_API_KEY") or None


def is_available() -> bool:
    """Return True if an OpenAI API key is configured."""
    return bool(_api_key())


async def embed_texts_async(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts using text-embedding-3-small.

    Args:
        texts: Non-empty list of strings to embed.

    Returns:
        List of embedding vectors in the same order as inputs.

    Raises:
        RuntimeError: If OPENAI_API_KEY is not set.
        httpx.HTTPStatusError: If the API call fails.
    """
    key = _api_key()
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY is not configured. "
            "Set it in your .env file to enable spec retrieval."
        )

    all_embeddings: list[list[float]] = []

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        for i in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[i : i + EMBED_BATCH_SIZE]
            response = await client.post(
                OPENAI_EMBEDDINGS_URL,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={"model": EMBEDDING_MODEL, "input": batch},
            )
            response.raise_for_status()
            data = response.json()
            # OpenAI returns embeddings sorted by their index
            sorted_items = sorted(data["data"], key=lambda x: x["index"])
            all_embeddings.extend(item["embedding"] for item in sorted_items)

    logger.debug(
        f"Embedded {len(texts)} texts with {EMBEDDING_MODEL} "
        f"({len(all_embeddings[0])} dims)"
    )
    return all_embeddings


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Synchronous wrapper around embed_texts_async for use in sync agent code."""
    from apex.backend.utils.async_helper import run_async
    return run_async(embed_texts_async(texts))
