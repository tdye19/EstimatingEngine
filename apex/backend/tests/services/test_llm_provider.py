"""Unit tests for LLM provider billing error detection (Sprint 18 backlog #5)."""

import asyncio
import os

os.environ.setdefault("APEX_DEV_MODE", "true")
os.environ.setdefault("DATABASE_URL", "sqlite://")

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from apex.backend.services.llm_provider import LLMProviderBillingError, OpenRouterProvider


# ---------------------------------------------------------------------------
# Class-level contract
# ---------------------------------------------------------------------------


def test_billing_error_is_runtime_error():
    assert issubclass(LLMProviderBillingError, RuntimeError)


def test_billing_error_message_preserved():
    exc = LLMProviderBillingError("openrouter 402: balance zero")
    assert "402" in str(exc)


# ---------------------------------------------------------------------------
# _check_for_billing_error helper
# ---------------------------------------------------------------------------


def test_check_for_billing_error_raises_on_402():
    mock_resp = MagicMock()
    mock_resp.status_code = 402
    mock_resp.text = '{"error": "Payment Required"}'

    with pytest.raises(LLMProviderBillingError) as exc_info:
        OpenRouterProvider._check_for_billing_error(mock_resp)

    assert "402" in str(exc_info.value)
    assert "openrouter.ai" in str(exc_info.value).lower() or "Payment Required" in str(exc_info.value)


def test_check_for_billing_error_delegates_raise_for_status_on_200():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()

    OpenRouterProvider._check_for_billing_error(mock_resp)

    mock_resp.raise_for_status.assert_called_once()


def test_check_for_billing_error_re_raises_other_http_errors():
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "500 Server Error", request=MagicMock(), response=mock_resp
        )
    )

    with pytest.raises(httpx.HTTPStatusError):
        OpenRouterProvider._check_for_billing_error(mock_resp)

    # Must NOT be wrapped as LLMProviderBillingError
    try:
        OpenRouterProvider._check_for_billing_error(mock_resp)
    except LLMProviderBillingError:
        pytest.fail("500 should not raise LLMProviderBillingError")
    except httpx.HTTPStatusError:
        pass  # expected


# ---------------------------------------------------------------------------
# _complete_messages — 402 propagates through the OpenRouter messages path
# ---------------------------------------------------------------------------


def _make_402_resp():
    mock_resp = MagicMock()
    mock_resp.status_code = 402
    mock_resp.text = '{"error": "Insufficient credits", "code": 402}'
    return mock_resp


def _make_async_client_cm(mock_resp):
    """Return an async context manager mock whose .post() returns mock_resp."""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def test_complete_messages_402_raises_billing_error():
    mock_resp = _make_402_resp()
    provider = OpenRouterProvider(api_key="sk-test", model="anthropic/claude-sonnet-4-6")

    with patch("apex.backend.services.llm_provider.get_http_client", return_value=None):
        with patch("httpx.AsyncClient", return_value=_make_async_client_cm(mock_resp)):
            with pytest.raises(LLMProviderBillingError):
                asyncio.run(provider._complete_messages("sys", "user", 0.0, 1024))


def test_complete_chat_402_raises_billing_error():
    mock_resp = _make_402_resp()
    # Use a non-Claude model so _complete_chat path is taken
    provider = OpenRouterProvider(api_key="sk-test", model="google/gemini-2.5-flash")

    with patch("apex.backend.services.llm_provider.get_http_client", return_value=None):
        with patch("httpx.AsyncClient", return_value=_make_async_client_cm(mock_resp)):
            with pytest.raises(LLMProviderBillingError):
                asyncio.run(provider._complete_chat("sys", "user", 0.0, 1024))


def test_pooled_client_402_raises_billing_error_not_transport_fallback():
    """A 402 from the pooled client must raise, not fall through to fresh-client."""
    mock_resp = _make_402_resp()

    mock_pooled = AsyncMock()
    mock_pooled.post = AsyncMock(return_value=mock_resp)

    provider = OpenRouterProvider(api_key="sk-test", model="anthropic/claude-sonnet-4-6")

    with patch("apex.backend.services.llm_provider.get_http_client", return_value=mock_pooled):
        with pytest.raises(LLMProviderBillingError):
            asyncio.run(provider._complete_messages("sys", "user", 0.0, 1024))

    # Fresh client should NOT have been called
    with patch("apex.backend.services.llm_provider.get_http_client", return_value=mock_pooled):
        with patch("httpx.AsyncClient") as mock_fresh_cls:
            try:
                asyncio.run(provider._complete_messages("sys", "user", 0.0, 1024))
            except LLMProviderBillingError:
                pass
            mock_fresh_cls.assert_not_called()
