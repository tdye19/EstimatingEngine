"""Tests for file_classifier_tool — Sprint 18.3.3.2.

Covers the new work_scope detection branch and the invariant that it
cannot eat existing spec-classification paths. The branch is defensive:
it keeps Christman-style Work Scope PDFs out of Agent 2's classification
filters (agent_2_spec_parser.py:316 spec filter, :328 general/None
fallback). Agent 2B is not gated on Document.classification and is
unaffected by this tag.
"""

from __future__ import annotations

from apex.backend.agents.tools.document_tools import (
    _is_work_scope_document,
    file_classifier_tool,
)

# ---------------------------------------------------------------------------
# Representative content samples
# ---------------------------------------------------------------------------

# Christman-style KCCU Work Scopes content — hits all four content signals.
KCCU_CONTENT = """\
Christman / Kellogg Community College Utilities

Proposal Section                   Work Category Description
WC 00                              General Conditions
WC 05                              Site Concrete
WC 28A                             Electrical Distribution

Work Category No. 05 — Site Concrete

Work Included:
 1. Furnish and install all cast-in-place concrete.
 2. Furnish and install formwork for foundation walls.

Related Work by Others:
 - Structural steel supplied by WC 05B.
"""

# A spec that mentions Work Category once in passing — must NOT classify
# as work_scope, should fall through to spec.
SPEC_WITH_PASSING_MENTION = """\
SECTION 01 23 00 — ALTERNATES

PART 1 GENERAL

1.1 SUMMARY
    A. Coordinate with the assigned Work Category and submit pricing per
       the bid form. No single reference here should classify this as
       anything other than a spec.
    B. Reference Division 03 and MasterFormat indexing as required.
"""

# Pure spec content — no work-scope signals at all.
SPEC_CONCRETE = """\
SECTION 03 30 00 — CAST-IN-PLACE CONCRETE

PART 1 GENERAL
    1.1 SUMMARY
    1.2 REFERENCES
PART 2 PRODUCTS
PART 3 EXECUTION
"""

SPEC_INDEX = """\
PROJECT MANUAL — MASTERFORMAT 2020
Division 01 General Requirements
Division 03 Concrete
Division 05 Metals
"""


# ---------------------------------------------------------------------------
# Filename-signal path
# ---------------------------------------------------------------------------


def test_classifier_detects_work_scope_by_filename():
    result = file_classifier_tool(
        "KCCU Volume 2 - Work Scopes - 12.1.2025.pdf",
        # Generic content that would otherwise route to "spec" — filename alone
        # must be sufficient.
        "SECTION 01 23 00 Division 03 Part 1 General.",
    )
    assert result == "work_scope"


def test_filename_signal_volume_plus_scope_suffices():
    # Christman naming can omit the hyphenated "Work Scopes" phrase — the
    # filename hint falls back to "volume" + "scope" both present.
    assert _is_work_scope_document("KCCU_Volume_2_Scope_Package.pdf", "") is True


# ---------------------------------------------------------------------------
# Content-signal path (innocuous filename)
# ---------------------------------------------------------------------------


def test_classifier_detects_work_scope_by_content():
    # "submission.pdf" has no work-scope filename hint. Content has:
    #   signal 1: "Work Category No." present
    #   signal 2: "WC 00", "WC 05", "WC 28A" all match _WC_NUMBER_RE
    #   signal 3: "Proposal Section" + "Work Category Description" both present
    #   signal 4: "Work Included:" at line start
    # ≥ 2 signals → work_scope.
    result = file_classifier_tool("submission.pdf", KCCU_CONTENT)
    assert result == "work_scope"


# ---------------------------------------------------------------------------
# Negative — single-signal must NOT classify as work_scope
# ---------------------------------------------------------------------------


def test_classifier_rejects_single_content_signal():
    # This spec mentions "Work Category" in a coordination note but none of
    # the four signals trigger: no "Work Category No.", no WC <digits>,
    # no "Proposal Section" + "Work Category Description" pair, no
    # "Work Included:" line. It must fall through to "spec" via the
    # existing filename branch (filename contains "section").
    result = file_classifier_tool("Section_01_23_00_Alternates.pdf", SPEC_WITH_PASSING_MENTION)
    assert result == "spec"
    # Helper itself must also agree — zero signals trip.
    assert _is_work_scope_document("Section_01_23_00_Alternates.pdf", SPEC_WITH_PASSING_MENTION) is False


# ---------------------------------------------------------------------------
# WinEst priority — must still beat work_scope
# ---------------------------------------------------------------------------


def test_classifier_winest_still_wins():
    # A .est file with Work-Scope-looking content must still return "winest".
    result = file_classifier_tool("estimator_draft.est", KCCU_CONTENT)
    assert result == "winest"


# ---------------------------------------------------------------------------
# Regression guard — existing spec paths are unchanged
# ---------------------------------------------------------------------------


def test_classifier_existing_spec_paths_unchanged():
    # Filename hint ("specification")
    assert file_classifier_tool("Project_Specification_Manual.pdf", "") == "spec"

    # Filename hint ("section")
    assert file_classifier_tool("Section_03_30_00.pdf", "") == "spec"

    # Content-only (no filename signal) — the existing text-based branch.
    assert file_classifier_tool("document_001.pdf", SPEC_CONCRETE) == "spec"

    # MasterFormat index content
    assert file_classifier_tool("manual_index.pdf", SPEC_INDEX) == "spec"
