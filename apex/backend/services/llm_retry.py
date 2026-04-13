"""Retry decorator for LLM provider calls with exponential backoff."""

import asyncio
import functools
import logging

import httpx

logger = logging.getLogger("apex.llm_retry")


def with_llm_retry(max_retries: int = 3, base_delay: float = 1.0):
    """Decorator that retries LLM provider calls on transient errors.

    - HTTP 429: respect Retry-After header if present, else exponential backoff
    - HTTP 5xx: exponential backoff
    - Transport/timeout errors: exponential backoff
    - HTTP 4xx (not 429): raise immediately, don't retry
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except httpx.HTTPStatusError as exc:
                    last_exc = exc
                    status = exc.response.status_code

                    if status == 429:
                        retry_after = exc.response.headers.get("retry-after")
                        if retry_after:
                            try:
                                delay = float(retry_after)
                            except (ValueError, TypeError):
                                delay = base_delay * (2**attempt)
                        else:
                            delay = base_delay * (2**attempt)
                    elif 500 <= status < 600:
                        delay = base_delay * (2**attempt)
                    else:
                        # 4xx (not 429) — don't retry
                        raise

                    if attempt < max_retries:
                        logger.warning(
                            "LLM call failed (HTTP %d), retry %d/%d in %.1fs",
                            status,
                            attempt + 1,
                            max_retries,
                            delay,
                        )
                        await asyncio.sleep(delay)
                    else:
                        raise

                except (httpx.TransportError, httpx.TimeoutException) as exc:
                    last_exc = exc
                    delay = base_delay * (2**attempt)

                    if attempt < max_retries:
                        logger.warning(
                            "LLM call failed (%s), retry %d/%d in %.1fs",
                            type(exc).__name__,
                            attempt + 1,
                            max_retries,
                            delay,
                        )
                        await asyncio.sleep(delay)
                    else:
                        raise

            raise last_exc  # pragma: no cover

        return wrapper

    return decorator
