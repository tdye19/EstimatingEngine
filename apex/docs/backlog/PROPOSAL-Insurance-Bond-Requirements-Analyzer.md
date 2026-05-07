# Proposal — Insurance & Bond Requirements Analyzer

**Status:** Proposed, not scheduled
**Date drafted:** 2026-05-07
**Proposed by:** Tucker Dye
**Estimated sprint slot:** 22.1 (post-pilot) — see ordering rationale in
`apex/docs/backlog/IDEAS-Tucker-2026-05-07-ordering.md`

---

## What it is

A new APEX analyzer module that reads bid documents (specs, supplementary
conditions, owner-furnished insurance requirements) and surfaces all
insurance and bonding requirements in structured form. Output appears as
a new section in the Intelligence Report.

This is a requirements-extraction feature, not interpretation. The bid
documents always state insurance and bond requirements explicitly —
APEX's job is to find them, normalize them, and present them in a
checklist the estimator's risk/insurance team can verify against the
company's existing coverage.

---

## What it produces

A structured "Insurance & Bond Requirements" section in the Intelligence
Report containing:

### Insurance requirements
For each required policy type:
- Policy type (general liability, auto, umbrella, professional liability,
  builder's risk, pollution liability, workers comp, etc.)
- Required coverage amount (per occurrence + aggregate)
- Required additional insureds (owner, CM, architect, lender, etc.)
- Waiver of subrogation requirements
- Notice of cancellation provisions (typically 30/60/90 day)
- Source citation: which spec section the requirement came from
- A.M. Best rating requirement (typically A- or better)

### Bond requirements
For each required bond:
- Bond type (bid bond, performance bond, payment bond, maintenance bond)
- Amount (typically % of contract value)
- Surety A.M. Best rating requirement
- Duration / when released
- Source citation

### OCIP / CCIP indicators
- Whether the project uses Owner-Controlled or Contractor-Controlled
  Insurance Program — affects what the bidder needs to carry vs what's
  provided by the program

### Estimator action checklist
- "Confirm GL coverage at $X / $Y meets requirement"
- "Confirm bonding capacity covers $Z performance bond"
- "Add OCIP credit to bid if applicable" / "Subtract own GL/auto policy
  cost if OCIP-covered"

---

## Why it matters

Three concrete failure modes this prevents:

1. **Bid disqualification.** Christman bids get rejected when subcontractors
   submit insurance certificates that don't match required coverage amounts
   or required additional insureds. APEX surfacing the requirements at bid
   time prevents the certificate-mismatch rejection.

2. **Mispriced bonding.** Bond cost ranges 0.5–2.0% of contract value
   depending on project size, surety, and bidder financial strength.
   Missing a 100% performance + payment bond requirement on a $5M project
   is $25K–$100K of unbidded cost.

3. **OCIP/CCIP miss.** When the owner provides OCIP coverage, the bidder
   should NOT carry duplicate GL/auto policies in the bid — that's 1.5–2.5%
   of contract value in unnecessary cost. When OCIP language is buried in
   supplementary conditions and missed, the bid carries the duplicate cost
   and becomes uncompetitive.

---

## Why this is APEX's lane

- **Doctrine #1** — Pure extraction work. LLM reads the language; Python
  structures the output. No money math required.
- **Doctrine #3** — This is exactly what an estimator wishes existed.
  Currently estimators rely on the company's risk/insurance department to
  send back a coverage-confirmation memo, often days after the bid is
  due. APEX surfacing the requirements at the moment of bid pricing is
  the right workflow.
- **Doctrine #4** — Each requirement cites the spec section it came from.
  Hard provenance.

---

## Open questions

1. **Corpus availability.** Does Christman have 5–10 past bid packages
   with documented insurance/bond requirements that can serve as a
   validation corpus? (Probably yes — most projects have the requirements
   in a standard supplementary conditions document.)

2. **Output integration.** Does this become a new tab in the project view,
   or a section in the existing Intelligence Report, or both? Lean toward
   "new section in Intelligence Report" + "new tab for the checklist
   with verification status" — but defer to design pass.

3. **Verification workflow.** Should APEX track verification status
   (estimator confirmed coverage exists, risk team approved, bond capacity
   confirmed)? Or is APEX read-only and the verification happens in
   external systems? Lean toward read-only for v1, verification-tracking
   for v2.

---

## Dependencies

- Agent 1 (file ingest) — already exists.
- Agent 2 (spec parser) — already exists; insurance requirements are
  typically in Division 00 supplementary conditions or a dedicated
  insurance section. May need targeted prompt extension.
- Agent 6 (Intelligence Report) — already exists; needs new section.
- New: Agent 8 or extension to Agent 2 for insurance/bond extraction.
  Architectural call: should this be a new agent or a new tool inside
  Agent 2? Lean toward new tool inside Agent 2 — same source documents,
  just a different extraction target.

---

## Estimated effort

- Design pass: 4–8 hours
- Agent 2 extension or new tool: 8–16 hours
- Output schema + Intelligence Report integration: 4–8 hours
- Testing on real Christman corpus: 8–16 hours
- **Total: 24–48 hours / one focused weekend or 1.5–2 sprints at
  15–20 hr/week pace**

---

## Related items

- Sprint 19F WC-SPEC-LINK hero feature — independent, but the data
  plumbing (linking spec sections to other extraction targets) is similar.
- Contract Cost Intelligence Analyzer (separate proposal) — both surface
  bid-pricing-relevant information from documents traditionally handled
  by other departments.
- Construction Monitor MarketContext — independent.

---

## Success criteria for v1

- 90%+ extraction accuracy on the required insurance types and coverage
  amounts (validated against estimator's manual review of 5+ Christman
  bids).
- Zero false negatives on OCIP/CCIP detection (better to flag uncertain
  than miss it — too costly to miss).
- Output format that an estimator can hand to the risk/insurance team
  without reformatting.

