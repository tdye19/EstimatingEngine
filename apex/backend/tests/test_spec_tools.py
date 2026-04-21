"""Tests for apex.backend.agents.tools.spec_tools."""

import asyncio

import apex.backend.agents.tools.spec_prompts as spec_prompts
import apex.backend.agents.tools.spec_tools as spec_tools


class _FakeResponse:
    def __init__(self, content="[]"):
        self.content = content
        self.input_tokens = 10
        self.output_tokens = 5
        self.finish_reason = "stop"


class _FakeProvider:
    # provider_name not in ("anthropic", "gemini", "openrouter") forces the
    # small-context chunking branch in llm_parse_spec_sections.
    provider_name = "ollama"

    async def complete(self, *, system_prompt, user_prompt, temperature, max_tokens):
        return _FakeResponse("[]")


def test_llm_parse_spec_sections_keeps_longest_content_on_duplicate(monkeypatch):
    """When two chunks emit the same section_number, dedup should keep the
    one with the longer content (the rich body), not the thin TOC stub."""

    # Build >3000 words so chunk_document returns multiple chunks (ollama path
    # uses max_words=3000).
    paragraph = ("word " * 1600).strip()
    document_text = paragraph + "\n\n" + paragraph

    thin_content = "SECTION 03 30 00\nrequirements: "
    rich_content = (
        "PART 1 - GENERAL\n"
        + "detailed requirements " * 40
        + "\nPART 2 - PRODUCTS\n"
        + "material specifications " * 40
        + "\nPART 3 - EXECUTION\n"
        + "installation procedures " * 40
    )
    assert len(rich_content) >= 500
    assert len(thin_content) < len(rich_content)

    thin_section = {
        "section_number": "03 30 00",
        "section_title": "Cast-in-Place Concrete",
        "division": "03",
        "in_scope": True,
        "material_specs": {},
        "quality_requirements": [],
        "submittals_required": [],
        "referenced_standards": [],
        "content": thin_content,
    }
    rich_section = {
        **thin_section,
        "content": rich_content,
        "material_specs": {"f_c_psi": 4000},
        "referenced_standards": ["ACI 301", "ASTM C94"],
    }

    call_count = {"n": 0}

    def _fake_parse(_raw):
        call_count["n"] += 1
        # Chunk 1 returns the thin TOC stub; later chunks return the rich body.
        if call_count["n"] == 1:
            return [dict(thin_section)]
        return [dict(rich_section)]

    monkeypatch.setattr(spec_prompts, "parse_and_validate_llm_sections", _fake_parse)

    result, _in_tok, _out_tok = asyncio.run(spec_tools.llm_parse_spec_sections(document_text, _FakeProvider()))

    assert call_count["n"] >= 2, "expected chunking to produce at least two LLM calls"
    assert len(result) == 1, f"expected dedup to collapse to one section, got {len(result)}"

    section = result[0]
    assert section["section_number"] == "03 30 00"
    # Fields unique to the rich version must survive dedup, proving the rich
    # section (longer content) replaced the thin stub rather than the other way around.
    assert section["material_specs"] == {"f_c_psi": 4000}
    assert section["referenced_standards"] == ["ACI 301", "ASTM C94"]


def test_llm_parse_spec_sections_handles_missing_content_field(monkeypatch):
    """Dedup must not crash when sections have no 'content' key or content is None."""
    paragraph = ("word " * 1600).strip()
    document_text = paragraph + "\n\n" + paragraph

    base = {
        "section_number": "03 30 00",
        "section_title": "Cast-in-Place Concrete",
        "division": "03",
        "in_scope": True,
        "material_specs": {},
        "quality_requirements": [],
        "submittals_required": [],
        "referenced_standards": [],
    }
    # First call: no content key at all. Second call: content is None.
    first = dict(base)
    second = {**base, "content": None}

    calls = {"n": 0}

    def _fake_parse(_raw):
        calls["n"] += 1
        return [dict(first)] if calls["n"] == 1 else [dict(second)]

    monkeypatch.setattr(spec_prompts, "parse_and_validate_llm_sections", _fake_parse)

    result, _in_tok, _out_tok = asyncio.run(spec_tools.llm_parse_spec_sections(document_text, _FakeProvider()))

    assert len(result) == 1
    assert result[0]["section_number"] == "03 30 00"
