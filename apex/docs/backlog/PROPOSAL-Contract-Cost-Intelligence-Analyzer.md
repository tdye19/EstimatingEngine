# Proposal — Contract Cost Intelligence Analyzer

**Status:** Proposed, not scheduled
**Date drafted:** 2026-05-07
**Proposed by:** Tucker Dye
**Estimated sprint slot:** 22.2 (post-pilot, after Insurance/Bond) — see
ordering rationale in `apex/docs/backlog/IDEAS-Tucker-2026-05-07-ordering.md`

---

## What it is

A new APEX analyzer module that reads contract documents (Division 00
front-end, supplementary conditions, owner-furnished agreements) and
surfaces every provision that has a **quantified or quantifiable cost or
risk dollar implication for the bid**. Output is a line-item list the
estimator can roll directly into bid pricing.

**This is contract-driven cost intelligence, not contract review.**

The distinction matters and was deliberately reframed during the
2026-05-07 ideation session:

- **What this is NOT:** legal review, redline suggestions, full contract
  analysis, "is this contract favorable?" — that's Document Crunch / legal
  counsel territory and APEX explicitly does not compete there.
- **What this IS:** "how does this contract change my bid number?"
  Estimators need to know that liquidated damages exist, that consequential
  damages are not waived, that pay-if-paid is in effect, that retention
  is 10% — *because each of those provisions changes what the bid should
  be.* That's APEX's lane.

The pitch sentence: *"Document Crunch tells your legal team what the
contract says. APEX tells your estimator what the contract costs."*

---

## What it produces

A structured "Contract Cost Intelligence" section in the Intelligence
Report. Each row contains:

| Field | Example |
|---|---|
| Contract provision | Liquidated damages: $5,000/day, no cap |
| Source citation | Article 8.2, Owner-Contractor Agreement, page 14 |
| Quantified impact | 200-day project = up to $1M unbounded exposure |
| Risk classification | High |
| Suggested bid treatment | Add 1.5–2% schedule contingency markup; qualify exclusions for owner-caused delay in bid notes |
| Estimator action | Confirm | Verify | Mark addressed |

### Provisions APEX will surface (initial scope)

**Schedule risk:**
- Liquidated damages — daily rate, cap, triggering events
- Time extension provisions — what events qualify, notice deadlines
- Acceleration clauses — at whose cost
- Owner work / phased turnover impact

**Liability risk:**
- Consequential damages — waived or not waived; what's excluded
- Indemnification — broad-form / intermediate / limited; comparative fault?
- Mutual waiver of subrogation — present?
- Notice provisions for claims — written notice timelines

**Labor cost:**
- Davis-Bacon prevailing wage requirements
- Project labor agreement (PLA) requirements
- Union vs open-shop requirements
- MWBE / DBE participation requirements (with target percentages)
- Apprenticeship requirements

**Cash flow:**
- Retention — percentage, when reduced, when released
- Pay-when-paid vs pay-if-paid language
- Stored materials reimbursement — on-site only or off-site allowed?
- Mobilization / front-end loading restrictions

**Insurance / bonding cost (cross-reference with Insurance Analyzer):**
- OCIP/CCIP credits if applicable
- Bond requirements impacting bid

**Change order pricing:**
- Markup limits on change orders (typically 10–15%)
- T&M caps and rate restrictions
- Contractor proposal time limits

**Termination risk:**
- Termination for convenience — present? compensation terms?
- Termination for default triggers

**Dispute resolution:**
- Arbitration vs litigation
- Venue and choice of law
- Jury waiver
- Mediation prerequisites

### Output discipline

If a contract provision doesn't move the bid number or the bid risk in
a quantifiable way, APEX does NOT surface it. Force majeure language
without dollar impact, governing law clauses, and similar boilerplate
get filtered out. The bar is: can an estimator do something different
in their bid because of this provision? If yes, surface it. If no, skip it.

---

## Why this is APEX's lane (and not Document Crunch's)

| | APEX Contract Cost Intelligence | Document Crunch (and similar) |
|---|---|---|
| User | Estimator pricing the bid | Legal/risk reviewing for execution |
| Timing | Bid phase — before submission | Post-award — before signing |
| Output | Cost line items + bid markup recommendations | Redline + risk memo |
| Question answered | "How does this contract change my bid?" | "What are we agreeing to?" |
| Audit trail | Cited contract sections per cost item | Cited contract sections per legal risk |
| Decisions enabled | Bid pricing, qualification language | Negotiation, counter-redlines, signing |

These are complementary, not competing. A real Christman workflow
plausibly uses both: APEX during bid pricing, Document Crunch (or
equivalent) at contract execution.

---

## Why it matters

Three concrete failure modes this prevents:

1. **Unbounded liability surprise.** An estimator who misses a $5K/day
   liquidated damages clause on a 200-day project just left $1M of risk
   unpriced. Even with a 25% likelihood-weighted risk reserve, that's a
   $250K bid markup decision being made unconsciously.

2. **Margin erosion via cash flow drag.** 10% retention held until 1
   year past substantial completion ties up cash for 18+ months on most
   projects. On a $5M contract, that's $500K parked. Financing cost on
   $500K at 6% over 18 months is $45K — about 1% of contract value.
   Every project that doesn't price this gives back margin.

3. **Wage rate misalignment.** Davis-Bacon / prevailing wage requirements
   add 18–35% to labor cost over open-shop rates. WinEst's default rate
   library is open-shop. If the bid is priced from the default library
   without prevailing wage adjustment, the bid is 5–10% under-priced
   and the project loses money on every hour worked.

These aren't edge cases. They're the failure modes experienced estimators
manually check on every bid, and miss occasionally because the language
is buried across 200+ pages of contract documents.

---

## Why this fits APEX doctrine

- **Doctrine #1 — LLMs handle language, Python handles money.** This
  feature is the cleanest possible application of doctrine #1. The LLM
  extracts: "liquidated damages: $5,000/day." Python computes:
  "200-day project × $5,000/day × 25% likelihood = $250K expected
  exposure → 1.25% bid markup recommendation." LLM never touches the
  dollar amount.

- **Doctrine #2 — Historical data is the moat.** Once Christman runs
  this on 50+ bids, you have a Christman-specific calibration of typical
  contract terms vs. risk reserves. That's a new rate library built from
  Christman's actual contract corpus. Defensible moat.

- **Doctrine #3 — Estimator-first.** This is exactly what an estimator
  wishes existed. Currently this analysis happens (if at all) in
  scattered conversations with legal, risk, and PMs. APEX surfacing it
  in the Intelligence Report at the moment of bid pricing is the right
  workflow.

- **Doctrine #4 — Show evidence.** Each line item cites the contract
  section it came from with the quoted language. Hard provenance.

---

## Open questions

1. **Cost calibration corpus.** The "suggested bid treatment" column
   needs ranges (e.g., "1.5–2% schedule contingency for $5K/day LDs").
   Where do those ranges come from? Probably need 5–10 past Christman
   bids with documented contract terms AND the actual bid markups
   applied. Without this calibration, APEX can flag the provision but
   not recommend a treatment.

2. **Risk classification thresholds.** What makes a provision High vs
   Medium vs Low risk? Default rules need design. Probably:
   - High: provisions with unbounded exposure (no cap on LDs, no cap on
     consequential damages, broad-form indemnification)
   - Medium: provisions with bounded but material exposure (capped LDs,
     prevailing wage, retention >5%)
   - Low: provisions with bounded and minor exposure (1% retention,
     standard 30-day notice)
   But this needs estimator validation.

3. **Document Crunch friction.** Does Christman currently use Document
   Crunch (or similar)? If yes, how does APEX's output integrate with
   their existing workflow? Probably: APEX output is bid-phase, Document
   Crunch is execution-phase, no integration needed. But verify.

4. **Pre-bid vs post-award.** Some provisions only become quantifiable
   after award (e.g., actual schedule, actual workforce mix). For pre-bid
   APEX runs, surface the provision and the formula; estimator computes
   when project specifics are known.

5. **Subcontract vs prime contract.** Christman is a CM/GC. Are they
   reviewing the OWNER-Christman contract (prime) or the
   Christman-Subcontractor contract (sub)? Likely both, but the cost
   implications differ. Initial scope: prime contract analysis from the
   GC's perspective.

---

## Dependencies

- Agent 1 (file ingest) — already exists.
- New agent or extension: Contract document classification + extraction.
  Architectural call: probably new Agent 9 (Contract Analyzer) since the
  document type and prompt strategy are sufficiently different from spec
  parsing.
- Calibration corpus — Christman past bids with documented contract terms
  and applied markups. This is the long-pole dependency.
- Agent 6 (Intelligence Report) — needs new section.

---

## Estimated effort

- Design pass: 8–16 hours (deeper than Insurance/Bond — risk
  classification thresholds, treatment recommendation logic require
  estimator input)
- Calibration corpus collection: 8–24 hours (depends on data accessibility)
- New Agent 9 implementation: 16–32 hours
- Output schema + Intelligence Report integration: 4–8 hours
- Testing on real Christman corpus: 16–32 hours (validation depth needs
  to be high — bid-pricing recommendations are consequential)
- **Total: 52–112 hours / 2–3 sprints at 15–20 hr/week pace**

---

## Related items

- Insurance & Bond Requirements Analyzer (separate proposal) — sister
  feature; cross-references on bond cost and insurance cost line items.
- Sprint 20 RSMeans pricing integration — independent, but both are
  cost-intelligence features.
- Sprint 19F WC-SPEC-LINK hero feature — independent.
- Construction Monitor MarketContext — independent but conceptually
  adjacent (both surface project-context information that affects pricing).

---

## Success criteria for v1

- 95%+ extraction accuracy on the high-risk provision categories
  (liquidated damages, consequential damages, retention, prevailing wage,
  pay-if-paid). False negatives on these are unacceptable — they're the
  ones that sink projects.
- Cost treatment recommendations that align with Christman's actual
  historical bid markup behavior on similar contract terms (validated
  against the calibration corpus).
- Output that an estimator can defend in front of a project executive
  asking "why are we adding 2% to this bid?" — the answer is the cited
  contract provision and the calculation behind the recommendation.
- Zero false positives on "this is a contract risk you must price for"
  on provisions that are actually standard / non-issue. Crying wolf
  damages estimator trust faster than missing a risk.

---

## Christman pilot fit

This feature is well-positioned for Christman pilot extension once the
core APEX surfaces (gap analysis, rate intelligence, takeoff matching)
are validated. Specific positioning:

- **Pitch differentiation:** "Document Crunch tells your legal team
  what the contract says. APEX tells your estimator what the contract
  costs." This is a clean, defensible product story that doesn't compete
  with existing Christman tooling.
- **User base expansion:** Currently APEX targets estimators. This
  feature naturally expands the audience to project executives and risk
  officers who want to see contract-driven cost reserves explicit in
  the bid.
- **Data flywheel:** Every bid run on this feature contributes to the
  cost-treatment calibration corpus. M2 data flywheel target benefits
  directly.

