"""LLM Provider abstraction layer.

Supports Ollama (local), Anthropic Claude API, and Google Gemini API via a
unified interface.  Provider selection uses a three-level fallback chain:

  1. Per-agent env vars  → AGENT_{N}_PROVIDER / AGENT_{N}_MODEL
     (or AGENT_{N}_{SUFFIX}_PROVIDER for sub-roles like AGENT_6_SUMMARY)
  2. Default env vars    → DEFAULT_LLM_PROVIDER / DEFAULT_LLM_MODEL
  3. Legacy env var      → LLM_PROVIDER (backwards-compatible)
"""

import os
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger("apex.llm_provider")

# ---------------------------------------------------------------------------
# Response dataclass
# ---------------------------------------------------------------------------

@dataclass
class LLMResponse:
    content: str            # The text response
    model: str              # Which model was used
    provider: str           # "ollama", "anthropic", or "gemini"
    input_tokens: int       # Token usage (0 if unavailable)
    output_tokens: int      # Token usage (0 if unavailable)
    duration_ms: float      # Wall clock time for the call
    cache_creation_input_tokens: int = 0  # Anthropic: tokens written to cache
    cache_read_input_tokens: int = 0      # Anthropic: tokens read from cache


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class LLMProvider(ABC):
    @abstractmethod
    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Send a prompt and get a text response."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the provider is available."""
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        pass


# ---------------------------------------------------------------------------
# Ollama (local)
# ---------------------------------------------------------------------------

class OllamaProvider(LLMProvider):
    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self._base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self._model = model or os.getenv("OLLAMA_MODEL", "llama3.2")

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        url = f"{self._base_url}/api/chat"
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        start = time.monotonic()
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=payload)
            data = resp.json()

        duration_ms = (time.monotonic() - start) * 1000
        content = data.get("message", {}).get("content", "")
        eval_count = data.get("eval_count", 0)
        prompt_eval_count = data.get("prompt_eval_count", 0)

        return LLMResponse(
            content=content,
            model=self._model,
            provider="ollama",
            input_tokens=prompt_eval_count,
            output_tokens=eval_count,
            duration_ms=duration_ms,
        )

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Anthropic Claude
# ---------------------------------------------------------------------------

class AnthropicProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        model: Optional[str] = None,
    ):
        self._api_key = api_key
        self._model = model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6-20260101")
        self._base_url = "https://api.anthropic.com/v1"

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def model_name(self) -> str:
        return self._model

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        url = f"{self._base_url}/messages"
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "prompt-caching-2024-07-31",
            "content-type": "application/json",
        }
        payload = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [
                {"role": "user", "content": user_prompt},
            ],
        }
        start = time.monotonic()
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        duration_ms = (time.monotonic() - start) * 1000
        content = data["content"][0]["text"]
        usage = data.get("usage", {})

        cache_creation = usage.get("cache_creation_input_tokens", 0)
        cache_read = usage.get("cache_read_input_tokens", 0)

        if cache_read > 0:
            logger.info("Cache HIT: %d tokens read from cache", cache_read)
        if cache_creation > 0:
            logger.info("Cache CREATED: %d tokens cached", cache_creation)

        return LLMResponse(
            content=content,
            model=self._model,
            provider="anthropic",
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            duration_ms=duration_ms,
            cache_creation_input_tokens=cache_creation,
            cache_read_input_tokens=cache_read,
        )

    async def health_check(self) -> bool:
        """Check if Anthropic API is reachable with the configured key."""
        try:
            url = f"{self._base_url}/messages"
            headers = {
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            payload = {
                "model": self._model,
                "max_tokens": 5,
                "messages": [{"role": "user", "content": "Hi"}],
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                return resp.status_code == 200
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Google Gemini
# ---------------------------------------------------------------------------

class GeminiProvider(LLMProvider):
    """Google Gemini via REST API (generateContent endpoint).

    Docs: https://ai.google.dev/api/generate-content
    Auth: API key passed as query param ?key={GEMINI_API_KEY}
    """

    _BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(
        self,
        api_key: str,
        model: Optional[str] = None,
    ):
        self._api_key = api_key
        self._model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        url = f"{self._BASE_URL}/{self._model}:generateContent"
        params = {"key": self._api_key}
        payload = {
            "system_instruction": {
                "parts": [{"text": system_prompt}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}],
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        start = time.monotonic()
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=payload, params=params)
            resp.raise_for_status()
            data = resp.json()

        duration_ms = (time.monotonic() - start) * 1000

        # Extract text from first candidate
        candidates = data.get("candidates", [])
        if not candidates:
            raise ValueError(f"Gemini returned no candidates: {data}")
        content = candidates[0]["content"]["parts"][0]["text"]

        # Token usage
        usage = data.get("usageMetadata", {})
        input_tokens = usage.get("promptTokenCount", 0)
        output_tokens = usage.get("candidatesTokenCount", 0)

        return LLMResponse(
            content=content,
            model=self._model,
            provider="gemini",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
        )

    async def health_check(self) -> bool:
        """Ping the model list endpoint to verify key validity."""
        try:
            url = f"{self._BASE_URL}/{self._model}:generateContent"
            params = {"key": self._api_key}
            payload = {
                "contents": [{"role": "user", "parts": [{"text": "Hi"}]}],
                "generationConfig": {"maxOutputTokens": 5},
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload, params=params)
                return resp.status_code == 200
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Internal builder
# ---------------------------------------------------------------------------

def _build_provider(provider_name: str, model: Optional[str]) -> LLMProvider:
    """Instantiate a provider by name, injecting the correct API key."""
    name = provider_name.lower()
    if name == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is required when provider=anthropic")
        return AnthropicProvider(api_key=api_key, model=model)
    elif name == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required when provider=gemini")
        return GeminiProvider(api_key=api_key, model=model)
    elif name == "ollama":
        return OllamaProvider(model=model)
    else:
        raise ValueError(f"Unknown LLM provider: '{provider_name}'. Valid: anthropic, gemini, ollama")


# ---------------------------------------------------------------------------
# Public factory — three-level fallback chain
# ---------------------------------------------------------------------------

def get_llm_provider(
    agent_number: Optional[int] = None,
    suffix: Optional[str] = None,
) -> LLMProvider:
    """Return the configured LLM provider using a three-level fallback chain.

    Level 1 — Per-agent config (most specific):
        AGENT_{N}_PROVIDER / AGENT_{N}_MODEL
        or AGENT_{N}_{SUFFIX}_PROVIDER / AGENT_{N}_{SUFFIX}_MODEL
        when suffix is provided (e.g. suffix="SUMMARY" for Agent 6).

    Level 2 — Default config:
        DEFAULT_LLM_PROVIDER / DEFAULT_LLM_MODEL

    Level 3 — Legacy backwards-compatible config:
        LLM_PROVIDER  (defaults to "ollama" if unset)

    Args:
        agent_number: Optional agent number (1-7). When provided, checks for
                      per-agent env vars before falling back.
        suffix:       Optional sub-role suffix, e.g. "SUMMARY" for the
                      AGENT_6_SUMMARY_PROVIDER / AGENT_6_SUMMARY_MODEL pair.
    """

    # --- Level 1: per-agent ---
    if agent_number is not None:
        if suffix:
            env_prefix = f"AGENT_{agent_number}_{suffix.upper()}"
        else:
            env_prefix = f"AGENT_{agent_number}"

        agent_provider = os.getenv(f"{env_prefix}_PROVIDER")
        agent_model = os.getenv(f"{env_prefix}_MODEL")

        if agent_provider:
            logger.debug(
                "Agent %d%s → provider=%s model=%s (per-agent config)",
                agent_number,
                f"/{suffix}" if suffix else "",
                agent_provider,
                agent_model or "(default for provider)",
            )
            return _build_provider(agent_provider, agent_model)

    # --- Level 2: default ---
    default_provider = os.getenv("DEFAULT_LLM_PROVIDER")
    default_model = os.getenv("DEFAULT_LLM_MODEL")
    if default_provider:
        logger.debug(
            "Agent %s → provider=%s model=%s (DEFAULT_LLM_PROVIDER)",
            agent_number or "?",
            default_provider,
            default_model or "(default for provider)",
        )
        return _build_provider(default_provider, default_model)

    # --- Level 3: legacy ---
    legacy_provider = os.getenv("LLM_PROVIDER", "ollama")
    logger.debug(
        "Agent %s → provider=%s (LLM_PROVIDER legacy fallback)",
        agent_number or "?",
        legacy_provider,
    )
    return _build_provider(legacy_provider, None)


# ---------------------------------------------------------------------------
# Introspection helpers (used by /api/health/llm)
# ---------------------------------------------------------------------------

# Canonical agent roster for health reporting.
# Each entry: (agent_number, suffix_or_None, label, description)
AGENT_PROVIDER_ROSTER = [
    (1,  None,      "agent_1_ingestion",       "Document Ingestion (Python only — no LLM)"),
    (2,  None,      "agent_2_spec_parser",      "Spec Parser"),
    (3,  None,      "agent_3_gap_analysis",     "Gap Analysis"),
    (4,  None,      "agent_4_quantity_takeoff",  "Quantity Takeoff"),
    (5,  None,      "agent_5_labor_productivity","Labor Productivity"),
    (6,  "SUMMARY", "agent_6_estimate_summary", "Estimate Assembly — Executive Summary"),
    (7,  None,      "agent_7_improve",           "IMPROVE Feedback"),
]


def get_agent_provider_config() -> dict:
    """Return a dict describing each agent's resolved provider config.

    Does NOT instantiate providers or make network calls — purely reads env vars.
    Used by the /api/health/llm endpoint.
    """
    result = {}

    for agent_number, suffix, label, description in AGENT_PROVIDER_ROSTER:
        # Agent 1 is always pure Python
        if agent_number == 1:
            result[label] = {
                "description": description,
                "provider": "python",
                "model": None,
                "source": "hardcoded",
                "api_key_configured": True,
            }
            continue

        if suffix:
            env_prefix = f"AGENT_{agent_number}_{suffix}"
        else:
            env_prefix = f"AGENT_{agent_number}"

        agent_provider = os.getenv(f"{env_prefix}_PROVIDER")
        agent_model = os.getenv(f"{env_prefix}_MODEL")

        if agent_provider:
            source = f"{env_prefix}_PROVIDER"
            provider = agent_provider.lower()
            model = agent_model
        else:
            default_provider = os.getenv("DEFAULT_LLM_PROVIDER")
            if default_provider:
                source = "DEFAULT_LLM_PROVIDER"
                provider = default_provider.lower()
                model = os.getenv("DEFAULT_LLM_MODEL")
            else:
                source = "LLM_PROVIDER (legacy)"
                provider = os.getenv("LLM_PROVIDER", "ollama").lower()
                model = None

        # Determine if the required API key is present
        api_key_configured = _api_key_is_set(provider)

        result[label] = {
            "description": description,
            "provider": provider,
            "model": model or _default_model_for(provider),
            "source": source,
            "api_key_configured": api_key_configured,
        }

    return result


def _api_key_is_set(provider: str) -> bool:
    if provider == "anthropic":
        return bool(os.getenv("ANTHROPIC_API_KEY"))
    elif provider == "gemini":
        return bool(os.getenv("GEMINI_API_KEY"))
    else:  # ollama / python
        return True


def _default_model_for(provider: str) -> str:
    defaults = {
        "anthropic": "claude-sonnet-4-6-20260101",
        "gemini": "gemini-2.5-flash",
        "ollama": "llama3.2",
    }
    return defaults.get(provider, "unknown")
