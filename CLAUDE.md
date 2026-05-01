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
