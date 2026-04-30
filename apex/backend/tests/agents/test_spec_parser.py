"""Regression test: Agent 2 filters non-spec documents from its input.

Ensures work_scope and drawing documents are never passed to the LLM,
even when they exist in the project and have raw text content.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from apex.backend.agents import agent_2_spec_parser as a2
from apex.backend.models.document import Document
from apex.backend.models.project import Project


def _seed_project(db_session) -> tuple[int, list[Document]]:
    suffix = uuid.uuid4().hex[:8]
    p = Project(
        name=f"Filter Test {suffix}",
        project_number=f"FLT-{suffix}",
        project_type="commercial",
    )
    db_session.add(p)
    db_session.flush()

    specs = [
        ("spec", "SECTION 03 30 00 CAST-IN-PLACE CONCRETE\n1.1 SUMMARY\nA. This section includes formwork."),
        ("work_scope", "03A Cast-in-Place Concrete Work Scope\nAll concrete work per drawings."),
        ("drawing", "Drawing A-001 Floor Plan\nScale 1/8 inch = 1 foot."),
    ]
    docs = []
    for classification, text in specs:
        doc = Document(
            project_id=p.id,
            filename=f"{classification}.pdf",
            file_path=f"/fake/{classification}.pdf",
            file_type="pdf",
            classification=classification,
            processing_status="completed",
            raw_text=text,
        )
        db_session.add(doc)
        docs.append(doc)

    db_session.commit()
    return p.id, docs


class _FakeProvider:
    provider_name = "fake"
    model_name = "fake-model"

    async def health_check(self) -> bool:
        return True


def test_agent_2_only_processes_spec_documents(db_session):
    """Only 'spec'-classified docs reach the LLM; work_scope and drawing are silently skipped."""
    project_id, docs = _seed_project(db_session)
    spec_doc = next(d for d in docs if d.classification == "spec")

    captured_texts: list[str] = []

    async def _fake_llm_parse(doc_text: str, prov) -> tuple[list, int, int]:
        captured_texts.append(doc_text)
        return [], 10, 5

    provider = _FakeProvider()

    with (
        patch("apex.backend.services.llm_provider.get_llm_provider", return_value=provider),
        patch(
            "apex.backend.agents.agent_2_spec_parser.llm_parse_spec_sections",
            side_effect=_fake_llm_parse,
        ),
        patch("apex.backend.agents.agent_2_spec_parser.log_token_usage"),
    ):
        result = a2.run_spec_parser_agent(db_session, project_id)

    assert len(captured_texts) == 1, (
        f"Expected LLM called once (spec doc only), got {len(captured_texts)} calls"
    )
    assert spec_doc.raw_text in captured_texts[0]
    assert result["documents_processed"] == 1
