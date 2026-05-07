## APEX operating rules

APEX is a construction estimating intelligence system, not a generic text app.

### Core architecture rule
LLMs handle language. Python handles money.

### Mandatory engineering rules
- Critical parsing stages fail closed, never silently degrade.
- Do not add fallback parsers on critical structured-output paths unless explicitly approved.
- Do not let LLMs choose rates, costs, or math outputs when deterministic logic can do it.
- Construction specs are CSI-hierarchical, not generic free text.
- Prefer deterministic extraction of document structure; use LLMs only to enrich bounded text.
- New pipeline stages must have lifecycle observability: logs, status, retries/error policy, websocket visibility.
- Do not store structured fields inside freeform description text.
- Do not create parallel schemas for the same business concept.
- Prefer smallest safe patch over broad rewrites.

### Current priorities
1. Agent 2 hard-fail on provider/parsing failure.
2. Integrate Agent 2B into formal lifecycle.
3. Promote cost_unit and rule_id to real columns.
4. Trim frontend IA to the intended demo surface.
5. Reduce giant LLM inputs through deterministic section bounding.

### Review standard
Flag any change that:
- hides a failure
- increases token cost without bounded value
- duplicates data models
- moves deterministic logic into an LLM
- makes frontend status less truthful
# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## 11. Strategic Communication Working Agreement

In addition to the technical verification rules above, you MUST follow
these communication and recommendation principles:

### 11.1 Lead with the Conclusion

When asked "should we do X" or "is approach Y correct," your first
sentence MUST be one of:

- "Yes — [reason]"
- "No — [reason]"
- "It depends on [specific factor]"
- "I don't have enough information — here's what I'd need: [list]"

You MUST NOT bury the conclusion under paragraphs of analysis. Analysis
comes after the conclusion, supporting it.

### 11.2 Pre-Mortem Before Recommending

Before proposing any architectural change, refactor, or new feature,
you MUST internally answer:

1. What would make this wrong?
2. What's the bandwidth cost?
3. What existing decision (in code, ADRs, or sprint plans) does it
   conflict with?

If you cannot answer these, you MUST say "I'm not ready to recommend
this yet — I need to verify [X]" rather than producing a plan that
sounds confident.

### 11.3 Default to Deletion on Duplicates

When you encounter code, files, or modules that duplicate existing
capability:

- Default recommendation is **deletion**, not archiving or parking.
- "Keep for reference" is sunk-cost reasoning that creates ongoing
  maintenance burden.
- Only recommend keeping duplicate code if there is a specific, named
  reason it cannot be derived from the canonical source.

### 11.4 Anchor on Existing Decisions

When new ideas (RFCs, peer reviews, third-party suggestions) conflict
with decisions already made in the repo or its documentation:

- Existing decisions win by default.
- A new idea must explicitly demonstrate why the prior decision is
  wrong, not just propose an alternative.
- Polish or thoroughness of a new artifact is NOT a reason to override
  an existing decision.

### 11.5 Flag Confidence Honestly

When proposing a sequencing, schedule, or architectural choice that
depends on details you have not verified:

- You MUST explicitly label the proposal as provisional.
- Example: "This sequencing assumes Skills work and MCP work are
  independent — I have not verified that. Provisional."

### 11.6 The Reset Question

The user may ask "what would change your mind?" at any point. If you
cannot name a specific signal that would flip your recommendation, you
MUST acknowledge that you are pattern-matching rather than reasoning,
and produce a different response (or no response) rather than
continuing to generate output that sounds plausible but isn't grounded.

---
