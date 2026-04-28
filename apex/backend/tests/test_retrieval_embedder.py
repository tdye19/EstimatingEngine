"""Tests for the retrieval embedder fallback behavior."""

import pytest

from apex.backend.retrieval import embedder


def test_embedder_unavailable_without_openai_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert embedder.is_available() is False

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is not configured"):
        embedder.embed_texts(["test query"])
