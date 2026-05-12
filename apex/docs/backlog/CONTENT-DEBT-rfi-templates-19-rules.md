# Content Debt: RFI Templates Missing for 19 of 25 Domain Rules

**Logged:** 2026-05-12
**Origin:** Spec 19E.6.1 (canonical grounding format)
**Priority:** Must resolve before estimator-facing surfacing of rule-attached fields (Specs 3+4)

## What

19 of 25 domain rules have an empty `rfi_language` field in `domain_gap_rules.py`.
The `to_canonical_facts()` accessor (added in Spec 19E.6.1) substitutes the placeholder
`"TBD — author pending"` for these rules rather than inventing RFI text.

**Populated (6):** CGR-001, CGR-002, CGR-004, CGR-008, CIV-001, CIV-003

**Placeholder (19):** CGR-003, CGR-005–CGR-007, CGR-009–CGR-015, CIV-002, CIV-004–CIV-010

## Why it matters

Spec 3 (rule-cited finding validator) will attach `rfi_template` from `to_canonical_facts()`
to findings surfaced in gap reports. Any finding backed by one of the 19 placeholder rules
will display `"TBD — author pending"` where an estimator expects paste-ready RFI language.
This is invisible until validator attachment is wired in Spec 3.

The placeholder is doctrine-correct over invention — the ADR forbids LLM-authored cost/RFI
content. But "TBD" at 76% coverage is not acceptable for pilot.

## Effort

Small per rule — each `rfi_language` value needs 1–3 sentences of estimator-facing prose
mirroring the pattern in the 6 already-authored rules (e.g. CGR-001's language asking the
owner to clarify which contractor installs the vapor barrier). Total: 1–2 hours of authoring.
No code changes needed; values go directly into the rule constructors in `domain_gap_rules.py`.

## Acceptance

All 25 rules have a non-placeholder `rfi_language` value. The `test_all_25_have_rfi_template`
test in `test_domain_gap_rules_views.py` already enforces non-null; add a separate assertion
that none equal `"TBD — author pending"` once authoring is complete.
