"""HF-26 regression tests — Agent 2 clean-slate + no self-promotion.

Two independent bugs accumulated pollution across Agent 2 runs on
project 21:

1. SpecSection rows from earlier code paths (and from previously-
   misclassified docs) were never dropped. _upsert_spec_section
   dedupes on (project_id, section_number) but never deletes orphans,
   so re-triggers grew the count but never shrank it. Result: 74 rows
   in DB while latest run reported 16 sections_parsed.

2. Agent 2 self-promoted any document to classification="spec" once it
   parsed any section from it. Created a feedback loop where a non-spec
   doc (e.g. winest.xlsx) that yielded one section-shaped fragment
   would land in the spec pool permanently.

HF-26 fixes both: clean-slate delete at start of Agent 2 run, and
removal of the self-promotion code path.
"""

from __future__ import annotations

import logging
import uuid
from unittest.mock import patch

from sqlalchemy.orm import Session

from apex.backend.agents.agent_2_spec_parser import run_spec_parser_agent
from apex.backend.models.document import Document
from apex.backend.models.project import Project
from apex.backend.models.spec_section import SpecSection


def _make_project(db_session: Session, tag: str) -> Project:
    suffix = uuid.uuid4().hex[:8]
    p = Project(
        name=f"HF26 {tag} {suffix}",
        project_number=f"HF26-{tag}-{suffix}",
        project_type="commercial",
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


# ---------------------------------------------------------------------------
# Edit 1 — Clean-slate per project on Agent 2 run
# ---------------------------------------------------------------------------


def test_agent_2_clean_slate_drops_stale_sections(db_session: Session):
    """Stale SpecSection rows from earlier runs must be wiped at the
    start of each Agent 2 run. Pin: project starts with 5 stale sections
    + zero parseable docs; after Agent 2 runs, 0 sections remain.

    (On project 21 the real stale rows had document_id=None from a now-
    superseded code path, but the current schema requires NOT NULL, so
    this test seeds with a real doc_id. The clean-slate delete is keyed
    on project_id and wipes everything regardless of doc_id origin.)"""
    project = _make_project(db_session, "cleanslate")

    # A document is required to satisfy the NOT NULL FK on SpecSection.
    # Classification is "drawing" so Agent 2 won't touch it (no spec/general
    # match) — the only thing that should fire is the clean-slate delete.
    doc = Document(
        project_id=project.id,
        filename="not_a_spec.pdf",
        file_path="/fake/not_a_spec.pdf",
        file_type="pdf",
        classification="drawing",
        raw_text=None,
        processing_status="completed",
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    for i in range(5):
        db_session.add(
            SpecSection(
                project_id=project.id,
                document_id=doc.id,
                section_number=f"00 1{i} 00",
                division_number="00",
                title=f"Stale section {i}",
                work_description="leftover from earlier code path",
            )
        )
    db_session.commit()

    # Sanity: stale rows are present before the run.
    pre_count = (
        db_session.query(SpecSection)
        .filter(SpecSection.project_id == project.id)
        .count()
    )
    assert pre_count == 5

    # No documents present → Agent 2 finds nothing to parse, but the
    # clean-slate delete must still fire at the start of the run.
    # Provider must be mocked — Agent 2 now hard-fails without a reachable LLM.
    class _FakeProvider:
        provider_name = "fake"
        model_name = "fake-model"
        async def health_check(self) -> bool:
            return True

    with (
        patch("apex.backend.services.llm_provider.get_llm_provider", return_value=_FakeProvider()),
        patch("apex.backend.agents.agent_2_spec_parser._enrich_division_03_parameters",
              return_value={"division_03_count": 0, "enriched": 0, "extraction_methods": {},
                            "warnings": [], "duration_ms": 0.0}),
    ):
        run_spec_parser_agent(db_session, project.id)

    # Refresh the session view so we see what Agent 2 committed.
    db_session.expire_all()
    post_count = (
        db_session.query(SpecSection)
        .filter(SpecSection.project_id == project.id)
        .count()
    )
    assert post_count == 0, (
        f"clean-slate delete failed: {post_count} stale sections survived"
    )


# ---------------------------------------------------------------------------
# Edit 2 — Documents are NOT self-promoted to classification="spec"
# ---------------------------------------------------------------------------


def test_agent_2_filters_non_spec_docs_before_parsing(db_session: Session, caplog):
    """HF-28 invariant: Agent 2 rejects non-spec documents at the
    classification filter layer, before _parse_document is ever invoked.

    HF-26 verified Agent 2 wouldn't self-promote docs it DID parse.
    HF-28 enforces the strictly stronger guarantee: non-spec docs are
    never passed to the parser at all. _parse_document is patched to
    raise AssertionError so any invocation is an immediate test failure."""
    project = _make_project(db_session, "filterspec")

    for classification, filename in [
        ("general", "general_doc.txt"),
        ("work_scope", "scope.txt"),
        (None, "unclassified.txt"),
    ]:
        db_session.add(Document(
            project_id=project.id,
            filename=filename,
            file_path=f"/fake/{filename}",
            file_type="txt",
            classification=classification,
            raw_text="text that must never reach the parser",
            processing_status="completed",
        ))
    db_session.commit()

    # Snapshot seeded classifications before the run.
    db_session.expire_all()
    seeded = {
        d.id: d.classification
        for d in db_session.query(Document).filter_by(project_id=project.id).all()
    }

    def _must_not_parse(*args, **kwargs):
        raise AssertionError("_parse_document called on a non-spec document")

    class _FakeProvider:
        provider_name = "fake"
        model_name = "fake-model"
        async def health_check(self) -> bool:
            return True

    with caplog.at_level(logging.INFO, logger="apex.agent.spec_parser"):
        with (
            patch("apex.backend.services.llm_provider.get_llm_provider", return_value=_FakeProvider()),
            patch(
                "apex.backend.agents.agent_2_spec_parser._parse_document",
                side_effect=_must_not_parse,
            ),
            patch("apex.backend.agents.agent_2_spec_parser._enrich_division_03_parameters",
                  return_value={"division_03_count": 0, "enriched": 0, "extraction_methods": {},
                                "warnings": [], "duration_ms": 0.0}),
        ):
            result = run_spec_parser_agent(db_session, project.id)

    # d. Zero sections parsed.
    assert result["sections_parsed"] == 0

    # e. No SpecSection rows created for this project.
    db_session.expire_all()
    section_count = (
        db_session.query(SpecSection)
        .filter(SpecSection.project_id == project.id)
        .count()
    )
    assert section_count == 0, f"Expected 0 SpecSection rows, got {section_count}"

    # f. No document had its classification mutated.
    for doc in db_session.query(Document).filter_by(project_id=project.id).all():
        assert doc.classification == seeded[doc.id], (
            f"{doc.filename!r} classification changed from "
            f"{seeded[doc.id]!r} to {doc.classification!r}"
        )

    # g. Filter log line accounts for all three skipped classifications.
    # Counter sorts alphabetically: general, unclassified, work_scope.
    expected_log = (
        "Agent 2: filtered input — 0 spec docs accepted, "
        "1 general skipped, 1 unclassified skipped, 1 work_scope skipped"
    )
    messages = [r.getMessage() for r in caplog.records]
    assert any(expected_log in m for m in messages), (
        f"Expected log fragment not found: {expected_log!r}\n"
        "Captured messages:\n" + "\n".join(f"  {m!r}" for m in messages)
    )
