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


def test_agent_2_does_not_self_promote_unclassified_docs(db_session: Session):
    """Pre-HF-26, Agent 2 promoted any document to classification="spec"
    if it parsed at least one section from it. This created a feedback
    loop where mis-parsed non-spec docs (winest.xlsx producing a single
    section-shaped fragment) became permanent spec targets.

    Post-HF-26: documents retain their Agent 1 classification regardless
    of how many sections Agent 2 parses from them."""
    project = _make_project(db_session, "nopromote")

    # Doc starts as "general" — caught by Agent 2's secondary filter.
    # Pre-HF-26, parsing any section from it would flip classification
    # to "spec" forever.
    doc = Document(
        project_id=project.id,
        filename="something_general.txt",
        file_path="/fake/general.txt",
        file_type="txt",
        classification="general",
        raw_text="dummy text — Agent 2's parser will be patched",
        processing_status="completed",
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    original_classification = doc.classification
    assert original_classification == "general"

    # Patch Agent 2's parser to return one section, regardless of input,
    # so we deterministically hit the path that USED to self-promote.
    fake_section = {
        "section_number": "07 21 00",
        "title": "Thermal Insulation",
        "in_scope": True,
        "material_specs": {},
        "quality_requirements": [],
        "referenced_standards": [],
        "submittals_required": [],
        "raw_content": "fake parsed content",
    }

    def _fake_parse(raw_text, llm_available, provider):
        return ([fake_section], "regex", 0, 0)

    with patch(
        "apex.backend.agents.agent_2_spec_parser._parse_document",
        side_effect=_fake_parse,
    ):
        result = run_spec_parser_agent(db_session, project.id)

    # Sanity: Agent 2 actually processed the doc and created a section
    # (otherwise the no-promotion test is vacuous).
    assert result["sections_parsed"] >= 1, (
        f"test setup failure — Agent 2 parsed {result['sections_parsed']} "
        "sections; the no-promotion assertion below would be vacuous"
    )

    # The HF-26 invariant: classification is unchanged.
    db_session.expire_all()
    fresh_doc = db_session.query(Document).filter_by(id=doc.id).one()
    assert fresh_doc.classification == "general", (
        f"Agent 2 mutated doc.classification from 'general' to "
        f"{fresh_doc.classification!r} — self-promotion regressed"
    )
