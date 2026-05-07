# Domain Rules Validation Worksheet
**Project:** KCCU HQ — clean validation 2026-05-07 (id: 5)
**Spec source:** 2025-11-21 KCCU CI 1 Specifications .pdf
**Work scope:** KCCU_Volume_2_Work_Scopes_12_1_2025.pdf
**Generated:** 2026-05-07T16:51:20.886137+00:00
**Labeled:** 2026-05-07 (manual)
**Total findings to label:** 2

## Instructions

For each finding below, fill in the LABEL column with one of:
- TP (true positive) — the spec genuinely has this gap
- FP (false positive) — the rule misfired; the gap does not exist
- UNCERTAIN — cannot determine from spec alone

Fill in NOTES with a one-sentence rationale or spec section reference.

## Findings by Rule

### CGR-001 — Vapor Barrier Responsibility
_Did not fire on this project._

### CGR-002 — Embedded Items — Anchor Bolts & Embeds
_Did not fire on this project._

### CGR-003 — Rebar Coating Specification
_Did not fire on this project._

### CGR-004 — Architectural Concrete Requirements
_Did not fire on this project._

### CGR-005 — Concrete Pumping Costs
_Did not fire on this project._

### CGR-006 — Cold/Hot Weather Concrete Provisions
_Did not fire on this project._

### CGR-007 — Waterstop at Construction & Expansion Joints
_Did not fire on this project._

### CGR-008 — Post-Tensioning Required
_Did not fire on this project._

### CGR-009 — Testing & Inspection Responsibility
_Did not fire on this project._

### CGR-010 — High-Strength or Specialty Mix Designs
_Did not fire on this project._

### CGR-011 — Mechanical Rebar Splices / Couplers
_Did not fire on this project._

### CGR-012 — Control Joint Sawcutting
_Did not fire on this project._

### CGR-013 — Special Curing Requirements
_Did not fire on this project._

### CGR-014 — Fiber Reinforcement Specified
_Did not fire on this project._

### CGR-015 — Reshoring & Stripping Requirements
_Did not fire on this project._

### CIV-001 — Dewatering Not Included
_Did not fire on this project._

### CIV-002 — Rock Excavation Potential
_Did not fire on this project._

### CIV-003 — Contaminated / Unsuitable Soil
_Did not fire on this project._

### CIV-004 — Cut/Fill Imbalance — Import/Export
_Did not fire on this project._

### CIV-005 — Erosion Control Maintenance Duration
_Did not fire on this project._

### CIV-006 — Utility Crossings & Conflicts
_Fired 1 time._

| # | Division | Section | Title | Severity | LABEL | NOTES |
|---|----------|---------|-------|----------|-------|-------|
| 1 | 33 | 33 10 00 | Existing Utility Crossings & Conflicts | moderate | **FP** | WC-02 item 12 requires MISS-DIG call and utility verification; item 10 requires "verification of existing utility locations prior to excavations" — full bid package covers the concern. |

_New utility installation is in your scope. Verify existing utility locations and potential conflicts. Crossings, protection-in-place, and relocations can add significant cost. Review available utility survey and require test pits / potholing at critical crossings._

**Root cause of FP:** Rule engine analyzed CSI spec text only (section 33 41 00 Storm Drainage — pipe material specs, no utility-conflict language). WC-02 work scope language (MISS-DIG, utility verification, repair-if-disturbed) was in a separately classified document not fed to `run_domain_rules`.

### CIV-007 — Compaction Testing Responsibility
_Did not fire on this project._

### CIV-008 — Trench Safety & OSHA Requirements
_Fired 1 time._

| # | Division | Section | Title | Severity | LABEL | NOTES |
|---|----------|---------|-------|----------|-------|-------|
| 1 | 31 | 31 54 00 | Trench Safety / Shoring for Utilities | critical | **FP** | WC-02 Specific Note 6 explicitly requires "trench boxes, ramps and ladders for safe egress & protection during excavations" — shoring IS in scope. |

_Utility trench excavation is in your scope but trench shoring is not explicitly included. OSHA requires protection for trenches >5 ft deep. Even if not spec'd, this is a regulatory requirement and a cost that must be carried. Include trench box rental or sloping costs._

**Root cause of FP:** Rule triggers when 31 54 00 is absent from parsed spec sections AND no trench-safety keywords appear in spec text. Both conditions true: 31 54 00 was not parsed, and CSI spec sections 31 10 00 / 31 20 00 / 33 41 00 contain no shoring language. However, WC-02 Note 6 explicitly includes trench boxes — invisible to the rule engine.

### CIV-009 — Subgrade Preparation for Building/Paving
_Did not fire on this project._

### CIV-010 — Utility Connection / Tap Fees
_Did not fire on this project._

## Manual Labeling Summary

- True positives: **0**
- False positives: **2**
- Uncertain: **0**
- Precision = TP / (TP + FP) = **0 / 2 = 0%**

## Diagnosis

Both FPs share a single root cause: `run_domain_rules` receives `spec_content_text` built from
CSI `SpecSection` records only. Work scope documents (classification = `"work_scope"`) are parsed
and stored separately and are never included in that text. For this KCCU project both rule
concerns (utility-conflict management and trench shoring) are addressed in WC-02 (Volume 2
Work Scopes), which the rule engine never saw.

This is a **corpus gap**, not a rule-logic error. The rules are structurally correct but operating
on an incomplete text input.
