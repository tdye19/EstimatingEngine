# Sprint 19E.5 War Room — Resolving the Domain Rule Schema Mismatch

**Date drafted:** 2026-05-07
**Source finding:** `apex/docs/architecture/19E-finding-domain-rule-schema-mismatch.md`
**Decision target:** A directional choice plus an implementation sprint scoped to that direction.
**Format:** Four perspectives per direction. Builder argues for, Critic argues against, Strategist names tradeoffs and dependencies, Estimator says what works on a real Christman bid. Read it as a debate, not a recommendation. Tucker makes the call.

---

## Common ground (all four directions accept this)

- The 25 domain rules' keyword-presence gate is structurally mismatched to Christman's bid document workflow.
- The LLM path on Agent 3 is the production path. Project 5 produced 36 gaps via LLM with no rule input.
- The rules contain real value: rule_id provenance, RFI language, cost ranges, typical_responsibility — sourced from Christman estimating experience, not synthesized.
- Pilot is not blocked on this decision. Production gap analysis works.
- Whatever direction wins, the LLM gap output should be enriched to match the rule output's evidence density (doctrine #4).

What we're picking is **how the moat ships**, not whether it ships.

---

## Direction A — `scope_covered_in_workcategory` suppression field

**The change:** Add an optional list to each rule. When keywords in that list appear in WorkCategory text, the rule does not fire even if its other gates match. CIV-006 gets `["miss dig", "miss-dig", "utility verification", "utility relocation"]`. CIV-008 gets `["trench box", "trench shield", "shoring"]`. Encode by editing the 25 rule definitions in `domain_gap_rules.py`.

### Builder

This is the only direction that ships in one sprint and unbreaks the immediate problem. Rule schema gets one additive field; existing CSI scope gate and keyword presence gate stay exactly as they are. The evaluator gets a single new check: if `scope_covered_in_workcategory` is non-empty and any of those keywords match in WC text, `continue`. Five lines of code in the evaluator. The 25 rule definitions get scanned by hand against KCCU and 2-3 other bid packages to populate the new field. Total effort: one focused weekend if the corpus is at hand.

The rules become useful immediately. Re-run force-rule-based on project 5: CIV-006 and CIV-008 suppress correctly. Both move to TN. Precision number becomes meaningful. Sprint 19E.5 closes with a tested fix shipped, not a deferred decision.

The schema mismatch was caused by an additive change in the world (WorkCategory data appearing in Sprint 18.1). The fix is also additive. That's a pattern match worth preserving — additive problems get additive solutions, not refactors.

### Critic

This embeds Christman's specific WC numbering and phrasing conventions into rule data. KCCU uses "miss dig" — but a different Christman job might use "miss-utility verification" or "DigLine confirmation" or "underground locator service." Every project that phrases the same scope differently re-fires the FP. You haven't fixed the schema mismatch; you've patched it for one document corpus.

Worse: the suppression list is unbounded. Every rule needs ongoing maintenance as new bid packages reveal new phrasing. That maintenance burden lands on Tucker (one estimator, 15-20 hr/week). Within six months, half the rule definitions become Christman-bid-language artifacts rather than domain knowledge. The data stops looking like estimating intelligence and starts looking like a regex bank tied to one client's writing style.

There's also a structural confusion this introduces. The keyword presence gate (`spec_keywords`) fires the rule when keywords ARE present. The new suppression gate (`scope_covered_in_workcategory`) suppresses the rule when *different* keywords ARE present. Two opposite-semantics keyword gates per rule is hard to reason about, hard to debug, hard to audit. A future estimator (or a future Tucker, in 8 months) will mis-read the rule logic.

### Strategist

Doctrine alignment: preserves doctrine #1 (deterministic engine disposes — rules still run deterministically) and doctrine #2 (data is the moat — the rule data structure persists). Cedes nothing immediately. But it builds technical debt that compounds: every new client adds suppression-list maintenance load.

Sprint commitment: 1 sprint to ship A, then ongoing 1-2 hours per new bid package to update suppression lists. Over the M1-M2-M3 horizon (June pilot through December seed-readiness), that's potentially 50-100 hours of rule-tuning labor that doesn't compound into a defensible product feature. It's calibration tax.

Dependency creation: A is incompatible with eventually moving to B. If you adopt A and then in 6 months want B's symmetric (SpecSection ∪ WorkCategory) rules, you have to throw away the suppression lists and start over. A is a one-way door if you don't intend to revisit, or a wasted sprint if you do.

External read: at M3 seed-round technical due diligence, "we have 25 rules with ad-hoc suppression lists per client" reads as brittle. "We have a coverage-aware rule engine that reasons about (spec, work_category, takeoff) jointly" reads as defensible. A loses the narrative.

### Estimator

This works on the next 5 Christman bids. After that it depends on whether the language stays consistent. KCCU, CityGate, AWS DCDE all use roughly the same Christman boilerplate ("Miss Dig," "trench boxes," etc.) — the suppression list would probably hit 80%+ on similar Christman work.

But there's a real estimator-side problem A doesn't solve. When a rule fires and the gap card shows up in the report, the estimator has to verify it against the WC document anyway. With A, the rule won't fire when the WC keywords match — but the estimator still doesn't see *that the rule was suppressed because WC-02 covers it*. The intelligence is hidden.

A real estimator would actually prefer a card that says "CIV-006: utility verification — this is typically required. Confirmed addressed in WC-02 items 10 and 12." That's not what A produces. A just hides the rule output.

---

## Direction B — Restructure rules to consume (SpecSection, WorkCategory, takeoff) symmetrically

**The change:** Rules become coverage-aware. Each rule asks: "given the project's spec sections, work categories, and takeoff items, is this scope topic covered or not?" The evaluator stops using a one-shot keyword-presence gate and instead computes a coverage score across all three sources. Rules fire only when no source covers the topic. Touches `domain_gap_rules.py`, every rule's data shape, the evaluator, the tests, and Agent 3's input plumbing.

### Builder

This is the architecturally correct fix. The schema mismatch isn't that one keyword gate is wrong — it's that the rules were designed before WorkCategory existed and were never updated to know about it. B updates them properly. Once shipped, every future client's bid document workflow is naturally accommodated as long as it produces the standard APEX outputs (SpecSection, WorkCategory, TakeoffItem). No client-specific tuning. No suppression lists. The rules become real domain intelligence.

This also unlocks the WC-SPEC-LINK hero feature (Sprint 19F). B's coverage-reasoning is structurally similar to the linking work — same data sources, same coverage semantics. Doing B and 19F in the same sprint pair amortizes the data-plumbing cost across both features.

The rule data persists. Every existing rule's `spec_keywords`, `cost_impact_*`, `rfi_language`, `typical_responsibility` — all stays. What changes is the evaluator's logic and the rule's coverage definition. Existing rules get an additive field (`coverage_signals: list[str]` or similar) that the evaluator uses to check all three sources. The 25 rules' Christman-grade content is preserved; only the firing mechanism changes.

This is doctrine #1 and #2 fully preserved. Deterministic engine, data as moat, both intact and stronger.

### Critic

You just described a 2-3 sprint refactor and called it the "right answer." For a solo estimator at 15-20 hr/week, that's a month and a half. During pilot. With M1 in June.

Let's price the actual scope: redesign the rule data model (a few hours of design work, a day of editing 25 rule definitions), redesign the evaluator with coverage semantics (multi-day work — coverage scoring is non-trivial; what threshold counts as "covered"? what if WC mentions the topic but excludes it? what if takeoff has 10% of expected items?), update Agent 3's input pipeline to feed all three sources to the rules, write new tests, validate against multiple corpora to make sure the new evaluator doesn't regress, debug the inevitable edge cases. Realistic estimate: 60-100 hours of focused work. That's 3-5 weeks at Tucker's bandwidth.

And during that month-plus, the rules are dead code anyway because the LLM path is in production. So you'd be sinking 60-100 hours into a system that doesn't run on healthy projects. The opportunity cost is real: that same time could ship Sprint 19A security work, 19F WC-SPEC-LINK hero feature, or pilot polish.

There's also a measurement problem. How do you validate the new B rules are actually better than A's suppression lists? You'd need a labeled corpus of bids where you know which rules should fire and which shouldn't. That corpus doesn't exist. Sprint 19E proved that the precision number from one project is non-meaningful. B requires multi-project labeled validation. That's another sprint of corpus work *on top of* the implementation.

Finally: the LLM path is producing 36 gaps per bid with critical_count of 30. Is the rule path even competitive? Maybe the rules on B-quality data still produce a strict subset of what the LLM finds. You'd discover that *after* doing the work.

### Strategist

Doctrine alignment: maximally preserves doctrine #1 (deterministic engine), doctrine #2 (data is moat — and the moat gets *stronger*, not just preserved), doctrine #4 (rule output naturally produces richer evidence than LLM output). On paper, B is the most doctrine-aligned direction. The question is whether the implementation cost matches the strategic value at this stage of the company.

Sprint commitment: 2-3 sprints. Probably consumes Sprint 19E.5 + 19E.6 + 19F (the WC-SPEC-LINK hero feature) as a unit. That's the second half of the pre-pilot calendar.

Dependency: B converges with 19F because both want symmetric (SpecSection, WorkCategory, takeoff) data plumbing. Doing them as a pair is more efficient than either alone. But it commits the entire May-June calendar to this one architectural arc. Sprint 19A (security/auth) and 19B (schema migration hygiene) get squeezed.

External read: at M3 due diligence, B is the strongest narrative. "Coverage-aware rule engine that reasons jointly across all bid document types" is a defensible product moat. But M3 is December. The question is whether B is the right December story or the right June story. Probably December.

### Estimator

This is what an estimator would actually want, if it works. A gap report card that says "CIV-008 trench safety: required by OSHA. Spec mentions it (Div 33 sections). WC-02 covers it via Specific Note 6. Takeoff has line items for trench excavation. **Coverage: complete.**" That's the kind of output that builds trust. The rule isn't hiding; it's confirming. When something's missing — "Coverage: incomplete, no takeoff line items match" — the estimator has actionable information.

But here's the practical question: how much of what B would produce is the LLM already producing? Project 5's 36 LLM gaps probably already cover the topics the 25 rules check. If B's rules end up producing a strict subset of what the LLM produces, the marginal value is the *evidence density and provenance*, not the gap topics. That's still real value — rule output with rule_id, cost ranges, RFI language is more useful at a bid table than free-form LLM gap descriptions — but it's a refinement, not a new capability.

The estimator workflow would actually benefit most from B if the rules' output is presented *alongside* the LLM output, not instead of. That implies B needs to converge with D (hybrid), not replace it.

---

## Direction C — Retire rules as primary path, bank data as LLM prompt enrichment

**The change:** Stop treating the 25 rules as a deterministic engine. Restructure them as a knowledge base that grounds Agent 3's LLM prompt. Each rule becomes a JSON entry the prompt can reference: "When you see Div 31 sections, consider whether the bid addresses dewatering — typical responsibility: civil contractor; cost range $5K-$250K; RFI: 'Geotech indicates water table at elevation X, please confirm responsibility.'" The LLM uses this context to produce more grounded, more Christman-shaped gaps. The rule_based fallback path on Agent 3 either disappears or becomes a thin checklist.

### Builder

The LLM is already producing 36 gaps without the rules. Imagine what it produces with the rules' Christman-grade cost ranges, RFI templates, and typical_responsibility text feeding the prompt. The rules' value was never their structural form — it was their content. C delivers that content via the mechanism that already works.

This is one focused sprint. The rule data already exists in `domain_gap_rules.py`. Convert it from `DomainGapRule` Pydantic objects to a structured prompt-context format. Inject relevant entries (filtered by the project's parsed divisions) into Agent 3's system prompt. Test against project 5 — gaps should now have rule_id citations, cost ranges that match the rules' ranges, RFI language that mirrors the rule templates. Validate that LLM-produced gaps inherit the evidence density of rule-produced gaps.

This is also the most pilot-aligned direction. Christman estimators evaluating APEX in June need to see gap cards that read like "real estimating wisdom." LLM gaps grounded in 25 rules' worth of Christman-derived content are exactly that. C ships rule intelligence to pilot users without 2-3 sprints of refactoring.

The hidden upside: as you add more rules over time (new bid packages reveal new gap categories), they're additive prompt entries. No schema changes, no evaluator changes. Just append to the knowledge base.

### Critic

You just turned doctrine #1 into a suggestion. "LLMs handle language, Python handles money" was the foundational rule. C says: LLMs also handle gap analysis. There is no deterministic engine on the gap path anymore — every gap finding is an LLM proposal that the LLM also disposes.

That has real consequences. The LLM can hallucinate citations to rule_ids that don't exist. The LLM can mis-apply a cost range (citing CIV-001's $5K-$250K range against a Div 03 concrete gap). The LLM can produce a gap card that looks rule-grounded but is actually free-form invention. You'd need a deterministic post-validator to catch these — at which point you're back to building B, just from a different starting point.

Doctrine #4 takes a hit too. Rule-shaped gaps carry hard provenance: "this finding was produced by CIV-008 because conditions X, Y, Z were met." LLM-shaped gaps with rule citations carry soft provenance: "the LLM said this finding came from CIV-008, trust me." The estimator can't audit the rule firing logic; they can only audit the LLM's output. That's the abstracted-confidence-score pattern doctrine #4 was written against, just with rule_ids as the abstraction.

There's also a longer-term concern. The rules-as-data play means the moat is now LLM-prompt-engineering quality, not rule-engine quality. If a competitor builds a better LLM-prompted gap analyzer (which Anthropic, OpenAI, or any well-funded competitor could do in weeks), the moat collapses. The rules-as-deterministic-engine play protects the moat with code that's harder to replicate.

### Strategist

Doctrine alignment: cedes doctrine #1 explicitly for gap analysis. Preserves doctrine #2 in spirit (data is moat) but changes how the moat is delivered (prompt context instead of code). Doctrine #4 takes a hit unless paired with a deterministic validator.

Sprint commitment: 1 sprint. Cleanest implementation cost of all four directions.

Dependency: C is the only direction that *de-couples* gap analysis from the rule engine entirely. Future work on Agent 3 becomes prompt-engineering work, not rule-engine work. That's a different skill set and a different career trajectory for the codebase.

External read: at M3 due diligence, C is a defensible "we use frontier models well, with proprietary domain data as prompt context" story. But it's also the story every well-funded LLM-app startup tells. The differentiation is the data, not the architecture. If the data is good (Christman provenance, decades of estimating wisdom), C is fine. If the data isn't actually that defensible relative to public construction estimating texts, C exposes the lack of moat.

There's also a strategic question about what APEX *is.* If APEX is a rate-intelligence platform that produces deterministic, auditable bid analysis — C is the wrong direction. If APEX is an LLM-powered estimating copilot that gets smarter as it accumulates Christman data — C is the right direction. That's a positioning question worth resolving before picking C.

### Estimator

The gap cards from project 5's LLM run were good. Plenty of "specs reference X but your scope might not include Y" findings, mostly accurate. What was missing: cost ranges (the LLM doesn't know that dewatering ranges $5K-$250K — it'd say "significant cost" instead), specific RFI language (the LLM produces generic "please clarify" rather than the rule's pre-drafted question), and rule_id provenance (you can't tell why the LLM flagged it).

C fixes all three. With the rule content in the prompt, the LLM should produce gaps that say "CIV-001 dewatering: ranges $5K-$250K depending on conditions and duration; suggested RFI: 'Geotech report indicates water table at elevation ___...'"

But the worry is: will the LLM actually USE the prompt context faithfully, or will it paraphrase and degrade? You'd need to test. If it degrades, C is worse than current state. If it grounds correctly, C is excellent.

The estimator-trust angle: "this number came from rule CIV-001" is more auditable than "the LLM said this number based on rule CIV-001." Subtle but real. For pilot users at Christman, the deterministic story may build trust faster.

---

## Direction D — Hybrid: rules as deterministic check on LLM output

**The change:** LLM produces gaps as it does today. After LLM output, run the (still flawed) 25 rules. For any rule that fires AND whose topic is not represented in the LLM's gap set, surface as "rule_check_disagreement: rule says topic X is uncovered, LLM did not flag it." The estimator reviews disagreements as a deliberate audit step.

### Builder

D is the cheapest direction on paper — no rule schema changes, no LLM prompt changes. Just an additional pass after Agent 3's main run that diffs rule output against LLM output and surfaces gaps. One sprint, mostly orchestration code.

The framing wins: rules become an audit lane, not a primary lane. The schema mismatch in the rules becomes a feature ("rules sometimes flag things the LLM missed; sometimes flag things that are actually covered — both are useful audit signals"). False positives become "estimator review opportunities." False negatives stay false negatives, but no worse than today.

For pilot, D is the simplest story: "two independent gap analyses, with disagreements flagged for your review." That's the kind of dual-redundancy story that builds trust with construction professionals who are wary of AI.

### Critic

D doesn't fix the schema mismatch. It just moves the mismatch into a different lane. CIV-006 and CIV-008 still fire on project 5. Now they fire AND get labeled "rule_check_disagreement" AND require estimator review. You've turned 2 false positives into 2 forced-review tasks.

Worse: D layers an unfixed problem on top of a working system. The LLM is producing 36 reasonable gaps. D adds a second source of gaps that have a known schema mismatch. Estimator now has to review 36 LLM gaps + N "rule disagreements," most of which will be FPs. The signal-to-noise ratio degrades, not improves.

D also has a cardinality problem. The 25 rules will generate "disagreements" against the LLM on most projects, because the LLM doesn't know about specific rules and the rules don't know about WorkCategories. Most disagreements are noise. Estimators will start ignoring the disagreement column within 2-3 bids. That trains them to ignore rule output entirely — which actively damages the "rules-as-moat" narrative.

D is technically a hybrid but functionally a "rules continue to be useless, in a more visible way" direction.

### Strategist

Doctrine alignment: doesn't really preserve or cede anything cleanly. The rules run deterministically (doctrine #1 OK), the data is preserved (doctrine #2 OK), the disagreement signal is auditable (doctrine #4 OK). But none of it actually fixes the underlying mismatch — it just packages the mismatch differently.

Sprint commitment: 1 sprint. Fastest of the four directions. But it's the one most likely to require a *follow-up* sprint (probably toward A or B) once the disagreement noise is unmanageable.

Dependency: D is compatible with eventually shipping A or B underneath. You could build D first, then fix the rules' schema underneath without changing the audit-lane wiring. That makes D a defensible *intermediate* state if the long-term call is B.

External read: at M3 due diligence, D is hard to pitch as a finished system. It's clearly an interim architecture. But "we ship dual gap analysis with explicit disagreement flagging" is at least an honest interim story.

### Estimator

The disagreement column is a real estimator workflow ask. Estimators *do* like having a checklist they can verify against, and "two systems disagreed on this — please review" is a familiar pattern from how they cross-check their own work today. So the framing has merit.

The execution problem is what the Critic named. Most disagreements will be noise (rules firing on topics the LLM correctly handled, or rules failing to fire because of the schema mismatch when the LLM correctly flagged something). After a few bids of mostly-noise disagreements, the estimator just stops looking at the column. That's worse than not having the column.

For D to work as an estimator-grade audit lane, the disagreement output needs to be high-precision. That requires fixing the rules' schema first (which means doing A or B before D). D layered on top of unfixed rules is a feature with a built-in trust death spiral.

---

## Cross-direction patterns worth naming

**A and B are mutually exclusive long-term.** Adopting A wastes the sprint if you later move to B. They solve the same problem at different layers of investment.

**C and B are mutually exclusive on doctrine.** B preserves doctrine #1; C cedes it. The choice between them is a positioning decision: is APEX a deterministic-engine product or an LLM-powered product?

**D requires A or B underneath to be useful.** D on top of unfixed rules is noise; D on top of A or B is a real audit lane.

**C is the only direction that ships in time for pilot.** A is plausible but tight. B and D-with-fixed-rules are post-pilot work.

**All four directions preserve the rule data.** The cost ranges, RFI language, typical_responsibility content survives in every scenario. What changes is delivery mechanism.

---

## A reasonable decision framework

Three questions, in order:

**1. What is APEX positioning at M3 (December seed-round)?**

If "deterministic-engine rate intelligence platform that LLMs assist" → favors B
If "LLM-powered estimating copilot grounded in proprietary data" → favors C
If unclear or both → C is safer (one sprint), revisit at M2

**2. How important is rule output at pilot?**

If pilot success requires showing rule_id, cost ranges, RFI templates → favors A or C (both ship in time)
If pilot success is fine with current LLM output (36 gaps, narrative form) → no urgency; can defer to B properly

**3. What does Tucker want to spend the May-June calendar on?**

If May-June is "ship every hardening item before pilot" → A or C (1 sprint each)
If May-June is "make one big architectural bet that pays off at pilot" → B (consumes 19E.5 + 19E.6 + 19F)
If May-June is "ship MVP, defer architecture to post-pilot" → C now, revisit B at Sprint 21+

---

## Claude's read at draft time (one perspective, not a recommendation)

Lean: **C with a deterministic post-validator added later as a small sprint**. Rationale:

- LLM-primary is already the production reality; C aligns the architecture with the reality.
- The rule data ships to pilot in June, which matters for estimator trust.
- One sprint to ship.
- B is more doctrine-aligned but the bandwidth cost relative to LLM-already-works payoff is hard to justify pre-pilot.
- A is tactical patching that I expect Tucker to throw away in 6 months.
- D layered on unfixed rules damages trust faster than it builds it.

What would change this lean:

- If pilot estimators specifically ask for "show me the rule that fired and the deterministic logic" — that's a B signal.
- If LLM cost on Agent 3 spikes (Sonnet pricing changes, or Christman bids get larger) and rules-as-deterministic become a cost-control story — that's a B signal too.
- If LLM gap output without rule grounding is materially weaker than the rules would produce — C is worse than assumed, B becomes worth doing.

Treat this as one perspective among the four above, not a recommendation. The four-perspective debate is the actual artifact for the decision.

---

## How to use this document

Read it twice — once when you've made room, once before the decision session. Sit with the four directions for at least a day. The decision is consequential and the right call probably feels obvious after sleeping on it.

When you're ready to decide, the format is: pick a direction (A, B, C, or D), name the ONE thing that would make you wrong, and define what success looks like at the end of that direction's implementation sprint.

Then write the implementation sprint specs.
