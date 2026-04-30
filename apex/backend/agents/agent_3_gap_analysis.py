"""Agent 3: Scope Gap Analysis Agent.

Compares parsed spec scope against a master scope checklist.
Uses LLM-powered analysis (Claude Sonnet) when a provider is available;
falls back to rule-based checklist logic if the LLM is unavailable or fails.
"""

import asyncio
import json
import logging
import re
from typing import Literal

from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from apex.backend.agents.pipeline_contracts import validate_agent_output
from apex.backend.agents.tools.domain_gap_rules import run_domain_rules
from apex.backend.agents.tools.gap_tools import (
    checklist_compare_tool,
    gap_scorer_tool,
    risk_tagger_tool,
)
from apex.backend.models.gap_report import GapReport, GapReportItem
from apex.backend.models.spec_section import SpecSection
from apex.backend.services.token_tracker import log_token_usage
from apex.backend.utils.async_helper import run_async as _run_async
from apex.backend.utils.csi_utils import MASTER_SCOPE_CHECKLIST

logger = logging.getLogger("apex.agent.gap_analysis")

# Timeout guards (Sprint 18.3.3.4): cap LLM and health-check calls so Agent 3
# cannot hang indefinitely when the provider is unresponsive. 120s covers the
# historical 72-78s ceiling with ~60% headroom; 10s is enough for a health ping.
LLM_TIMEOUT_SECONDS = 120
HEALTH_CHECK_TIMEOUT_SECONDS = 10


# ---------------------------------------------------------------------------
# Spec-vs-Takeoff cross-reference keyword mapping
# ---------------------------------------------------------------------------

SCOPE_CROSS_REFERENCES = {
    "concrete": ["forms", "formwork", "rebar", "reinforcement", "finishing", "curing", "placement"],
    "foundations": ["excavation", "backfill", "forms", "rebar", "concrete", "waterproofing"],
    "walls": ["forms", "formwork", "rebar", "concrete", "bracing", "scaffolding"],
    "slabs": ["forms", "formwork", "rebar", "concrete", "finishing", "curing", "vapor barrier"],
    "post-tension": ["pt strand", "pt cable", "stressing", "anchor", "grout"],
    "precast": ["erection", "grouting", "connections", "bearing pads"],
    "structural steel": ["erection", "bolting", "welding", "shear studs", "fireproofing"],
    "masonry": ["mortar", "grout", "reinforcement", "lintels", "flashing"],
    "roofing": ["insulation", "flashing", "drains", "membrane", "vapor barrier"],
    "excavation": ["shoring", "dewatering", "backfill", "compaction"],
}


def _spec_vs_takeoff_gaps(db, project_id, spec_sections):
    """Compare parsed spec sections against uploaded takeoff items.

    Flags divisions present in spec but absent from takeoff, and
    cross-references related activities (e.g., concrete without formwork).

    Returns list of gap dicts ready for GapReportItem creation.
    No LLM calls — keyword matching + cross-reference logic only.
    """
    from apex.backend.models.takeoff_v2 import TakeoffItemV2

    rows = (
        db.query(TakeoffItemV2)
        .filter(
            TakeoffItemV2.project_id == project_id,
        )
        .all()
    )

    if not rows:
        return []  # No takeoff uploaded — skip this pass

    # Build searchable sets from takeoff
    takeoff_activities_lower = set()
    takeoff_text_blob = ""
    for r in rows:
        if r.activity:
            takeoff_activities_lower.add(r.activity.lower().strip())
            takeoff_text_blob += " " + r.activity.lower()
        if r.wbs_area:
            takeoff_text_blob += " " + r.wbs_area.lower()

    gaps = []

    # ── Pass 1: Division-level check ──────────────────────────────────
    # For each spec section, check if the takeoff has ANY relevant activity
    _DIVISION_KEYWORDS = {
        "03": ["concrete", "formwork", "rebar", "reinforc", "slab", "footing", "foundation", "wall", "column"],
        "04": ["masonry", "block", "brick", "mortar", "grout"],
        "05": ["steel", "metal", "joist", "deck", "beam", "column", "erect"],
        "07": ["roofing", "insulation", "waterproof", "membrane", "flashing", "sealant"],
        "31": ["earthwork", "excavat", "grading", "backfill", "compaction"],
        "32": ["paving", "asphalt", "concrete paving", "curb", "sidewalk", "landscape"],
    }

    spec_divisions = set()
    for s in spec_sections:
        div = (s.division_number or "")[:2].strip()
        if div:
            spec_divisions.add(div)

    for div in spec_divisions:
        keywords = _DIVISION_KEYWORDS.get(div, [])
        if not keywords:
            continue
        has_match = any(kw in takeoff_text_blob for kw in keywords)
        if not has_match:
            div_name = _get_division_name(div)
            gaps.append(
                {
                    "division_number": div,
                    "section_number": None,
                    "title": f"Spec includes Division {div} ({div_name}) but takeoff has no matching items",
                    "gap_type": "spec_vs_takeoff",
                    "severity": "critical",
                    "description": (
                        f"The project specification includes Division {div} ({div_name}) "
                        f"but no takeoff line items match expected activities for this division. "
                        f"Keywords checked: {', '.join(keywords[:5])}."
                    ),
                    "recommendation": (
                        f"Review Division {div} scope and confirm whether these items are included "
                        f"in your takeoff or intentionally excluded."
                    ),
                }
            )

    # ── Pass 2: Activity cross-reference check ────────────────────────
    # If takeoff has an activity matching a key, check associated activities exist
    for scope_key, required_companions in SCOPE_CROSS_REFERENCES.items():
        # Check if any takeoff activity matches the scope key
        key_present = any(scope_key in act for act in takeoff_activities_lower)
        if not key_present:
            continue

        for companion in required_companions:
            companion_present = companion in takeoff_text_blob
            if not companion_present:
                gaps.append(
                    {
                        "division_number": None,
                        "section_number": None,
                        "title": f"Takeoff includes {scope_key} but missing associated {companion}",
                        "gap_type": "spec_vs_takeoff",
                        "severity": "critical",
                        "description": (
                            f"Your takeoff includes items related to '{scope_key}' but no line item "
                            f"for '{companion}' was found. This is commonly required scope that may "
                            f"be missing from your estimate."
                        ),
                        "recommendation": (
                            f"Check whether '{companion}' is included elsewhere in your estimate "
                            f"(e.g., as a sub-bid or general conditions item). If not, add it."
                        ),
                    }
                )

    return gaps


def _get_division_name(div: str) -> str:
    """Short name for a CSI division number."""
    names = {
        "01": "General Requirements",
        "02": "Existing Conditions",
        "03": "Concrete",
        "04": "Masonry",
        "05": "Metals",
        "06": "Wood/Plastics/Composites",
        "07": "Thermal/Moisture Protection",
        "08": "Openings",
        "09": "Finishes",
        "10": "Specialties",
        "11": "Equipment",
        "12": "Furnishings",
        "13": "Special Construction",
        "14": "Conveying Equipment",
        "21": "Fire Suppression",
        "22": "Plumbing",
        "23": "HVAC",
        "26": "Electrical",
        "27": "Communications",
        "28": "Electronic Safety",
        "31": "Earthwork",
        "32": "Exterior Improvements",
        "33": "Utilities",
    }
    return names.get(div, f"Division {div}")


# ---------------------------------------------------------------------------
# Pydantic contract for individual gap items returned by the LLM
# ---------------------------------------------------------------------------


class LLMGapItem(BaseModel):
    """Validated gap item from LLM response."""

    description: str
    severity: Literal["critical", "high", "medium", "low"]
    affected_csi_division: str
    recommendation: str
    gap_type: str | None = "missing_division"

    @field_validator("severity", mode="before")
    @classmethod
    def _normalise_severity(cls, v: str) -> str:
        return str(v).lower().strip()

    @field_validator("affected_csi_division", mode="before")
    @classmethod
    def _normalise_division(cls, v: str) -> str:
        return str(v).strip().lstrip("0").zfill(2) if str(v).strip().isdigit() else str(v).strip()

    @field_validator("gap_type", mode="before")
    @classmethod
    def _normalise_gap_type(cls, v) -> str:
        return str(v).lower().strip() if v else "missing_division"


# ---------------------------------------------------------------------------
# Severity / gap_type mapping: LLM values → DB schema values
# ---------------------------------------------------------------------------

_SEVERITY_MAP: dict[str, str] = {
    "critical": "critical",
    "high": "critical",  # treat high as critical for DB compatibility
    "medium": "moderate",
    "low": "watch",
}

_GAP_TYPE_MAP: dict[str, str] = {
    "missing_division": "missing",
    "implied_scope": "ambiguous",
    "missing_common": "missing",
    "coordination_gap": "conflicting",
    # passthrough aliases
    "missing": "missing",
    "ambiguous": "ambiguous",
    "conflicting": "conflicting",
}


# ---------------------------------------------------------------------------
# CSI MasterFormat divisions reference (01–49) used in the system prompt
# ---------------------------------------------------------------------------

_CSI_DIVISIONS_REFERENCE = """\
DIVISION 00 — Procurement and Contracting Requirements
DIVISION 01 — General Requirements
DIVISION 02 — Existing Conditions
DIVISION 03 — Concrete
DIVISION 04 — Masonry
DIVISION 05 — Metals
DIVISION 06 — Wood, Plastics, and Composites
DIVISION 07 — Thermal and Moisture Protection
DIVISION 08 — Openings (Doors, Windows, Glazing)
DIVISION 09 — Finishes
DIVISION 10 — Specialties
DIVISION 11 — Equipment
DIVISION 12 — Furnishings
DIVISION 13 — Special Construction
DIVISION 14 — Conveying Equipment (Elevators, Escalators)
DIVISION 21 — Fire Suppression (Sprinklers)
DIVISION 22 — Plumbing
DIVISION 23 — HVAC (Heating, Ventilating, Air Conditioning)
DIVISION 25 — Integrated Automation
DIVISION 26 — Electrical
DIVISION 27 — Communications
DIVISION 28 — Electronic Safety and Security
DIVISION 31 — Earthwork
DIVISION 32 — Exterior Improvements (Paving, Landscaping)
DIVISION 33 — Utilities (Site Utilities)
DIVISION 34 — Transportation
DIVISION 35 — Waterway and Marine Construction
DIVISION 40 — Process Integration
DIVISION 41 — Material Processing and Handling Equipment
DIVISION 42 — Process Heating, Cooling, and Drying Equipment
DIVISION 43 — Process Gas and Liquid Handling and Purification
DIVISION 44 — Pollution Control Equipment
DIVISION 45 — Industry-Specific Manufacturing Equipment
DIVISION 46 — Water and Wastewater Equipment
DIVISION 48 — Electrical Power Generation
DIVISION 49 — (Reserved)"""

# Build system prompt at module level (avoids re-building on every call)
GAP_ANALYSIS_SYSTEM_PROMPT = (
    "You are a senior construction estimator with 20+ years of experience reviewing commercial "
    "building specifications for general contractors. Your job is to identify scope gaps — "
    "missing, implied, or ambiguous items that could cause cost overruns or change orders if "
    "not caught during the bid phase.\n\n"
    "You will receive a JSON array of CSI MasterFormat spec sections that have been parsed from "
    "a project specification. Identify what is MISSING or problematic.\n\n"
    "## CSI MasterFormat Complete Division Reference\n" + _CSI_DIVISIONS_REFERENCE + "\n\n"
    "## Four Gap Categories to Identify\n\n"
    "1. **missing_division** — A CSI division entirely absent from the spec that would typically "
    "be required for this building type (e.g., no Division 22 Plumbing in a commercial office "
    "building).\n\n"
    "2. **implied_scope** — Work referenced or strongly implied by another section but never "
    "explicitly specified (e.g., a concrete section implies Division 03 rebar and formwork; a "
    "roofing section implies roof drains and flashing; any MEP rough-in implies sleeves and "
    "coordination drawings).\n\n"
    "3. **missing_common** — Items commonly required for the apparent building type that are "
    "simply absent (e.g., a multi-story building should have Division 14 Elevators; a commercial "
    "tenant fit-out should have Division 10 Specialties such as toilet accessories and "
    "fire extinguisher cabinets).\n\n"
    "4. **coordination_gap** — Interface points between trades that no spec section addresses "
    "(e.g., who provides electrical connections for HVAC equipment; who installs pipe sleeves "
    "through structural concrete; who coordinates fire alarm with sprinkler contractor).\n\n"
    "## Severity Definitions\n\n"
    "- **critical**: Could cause a major cost overrun (>$50K) or significant RFI/schedule delay\n"
    "- **high**: Likely to generate a change order or dispute (>$10K impact)\n"
    "- **medium**: Should be clarified before bid submission (<$10K impact)\n"
    "- **low**: Minor coordination item, informational note only\n\n"
    "## Output Format\n\n"
    "Respond ONLY with a valid JSON array. No markdown fences, no explanation, no preamble — "
    "just the raw JSON array.\n\n"
    "Each object must have exactly these five fields:\n"
    '  "description"          — clear explanation of the gap and its cost risk\n'
    '  "severity"             — one of: "critical", "high", "medium", "low"\n'
    '  "affected_csi_division"— the CSI division number as a string, e.g. "22" or "03"\n'
    '  "recommendation"       — specific action the estimator should take before finalising bid\n'
    '  "gap_type"             — one of: "missing_division", "implied_scope", '
    '"missing_common", "coordination_gap"\n\n'
    "Include all significant gaps you identify. Do not fabricate gaps for divisions that are "
    "legitimately out of scope for the apparent building type."
)


# ---------------------------------------------------------------------------
# LLM gap analysis
# ---------------------------------------------------------------------------


def _build_user_prompt(parsed_sections: list[dict], spec_context: str = "") -> str:
    prefix = ""
    if spec_context:
        prefix = spec_context + "\n\n"
    return (
        prefix + "Below are the CSI spec sections parsed from this project's specification documents. "
        "Identify all scope gaps across the four categories.\n\n"
        "PARSED SPEC SECTIONS:\n" + json.dumps(parsed_sections, indent=2)
    )


def _is_truncated(content: str) -> bool:
    """Return True if the LLM response was cut off mid-string.

    Heuristic: find the last '}' and count unescaped double-quotes that follow.
    An odd count means there is an unterminated string literal — the model hit
    its max_tokens ceiling before closing the JSON structure.
    """
    stripped = content.strip()
    last_brace = stripped.rfind("}")
    if last_brace == -1:
        return True
    tail = stripped[last_brace + 1 :]
    quote_count = 0
    i = 0
    while i < len(tail):
        if tail[i] == "\\":
            i += 2
            continue
        if tail[i] == '"':
            quote_count += 1
        i += 1
    return quote_count % 2 == 1


def _parse_llm_gap_response(raw_content: str) -> list[LLMGapItem]:
    """Strip markdown fences, parse JSON, and validate each item with Pydantic."""
    content = raw_content.strip()
    # Strip optional markdown code fence
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```$", "", content.strip())
    content = content.strip()

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        logger.error(f"Agent 3 LLM: JSON parse error — {exc}")
        return []

    if not isinstance(data, list):
        logger.error(f"Agent 3 LLM: expected JSON array, got {type(data).__name__}")
        return []

    validated: list[LLMGapItem] = []
    skipped = 0
    for i, item in enumerate(data):
        try:
            validated.append(LLMGapItem.model_validate(item))
        except Exception as exc:
            skipped += 1
            logger.warning(f"Agent 3 LLM: skipping malformed gap item [{i}]: {exc}")

    if skipped:
        logger.warning(f"Agent 3 LLM: {skipped}/{len(data)} items skipped due to malformed data")

    return validated


async def _llm_gap_analysis(
    parsed_sections: list[dict], provider, spec_context: str = ""
) -> tuple[list[LLMGapItem] | None, int, int]:
    """Send parsed sections to LLM for gap analysis.

    Returns (items, input_tokens, output_tokens). items is None on any failure.
    Retries once with max_tokens=32000 when the initial response is truncated.
    """
    user_prompt = _build_user_prompt(parsed_sections, spec_context=spec_context)

    async def _call(max_tokens: int) -> "LLMResponse":  # noqa: F821
        return await asyncio.wait_for(
            provider.complete(
                system_prompt=GAP_ANALYSIS_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.1,
                max_tokens=max_tokens,
            ),
            timeout=LLM_TIMEOUT_SECONDS,
        )

    try:
        response = await _call(16000)
        logger.info(
            f"Agent 3 LLM: provider={response.provider} model={response.model} "
            f"input_tokens={response.input_tokens} output_tokens={response.output_tokens} "
            f"duration_ms={response.duration_ms:.0f}ms"
        )

        if _is_truncated(response.content):
            logger.warning(
                "Agent 3 LLM: response truncated at %d chars — last 200: %r — retrying with max_tokens=32000",
                len(response.content),
                response.content[-200:],
            )
            try:
                response = await _call(32000)
                logger.info(
                    f"Agent 3 LLM: provider={response.provider} model={response.model} "
                    f"input_tokens={response.input_tokens} output_tokens={response.output_tokens} "
                    f"duration_ms={response.duration_ms:.0f}ms"
                )
            except TimeoutError:
                logger.error(
                    f"Agent 3 LLM: retry timed out after {LLM_TIMEOUT_SECONDS}s — falling back to rule-based"
                )
                return None, 0, 0, 0, 0
            except Exception as exc:
                logger.error(f"Agent 3 LLM: retry call failed — {exc}")
                return None, 0, 0, 0, 0

            if _is_truncated(response.content):
                logger.error(
                    "Agent 3 LLM: retry response also truncated at %d chars — falling back to rule-based",
                    len(response.content),
                )
                return None, 0, 0, 0, 0

        items = _parse_llm_gap_response(response.content)
        logger.info(f"Agent 3 LLM: parsed {len(items)} validated gap items")
        return (
            items,
            response.input_tokens,
            response.output_tokens,
            response.cache_creation_input_tokens,
            response.cache_read_input_tokens,
        )
    except TimeoutError:
        logger.error(
            f"Agent 3 LLM: call timed out after {LLM_TIMEOUT_SECONDS}s — falling back to rule-based"
        )
        return None, 0, 0, 0, 0
    except Exception as exc:
        logger.error(f"Agent 3 LLM: call failed — {exc}")
        return None, 0, 0, 0, 0


# ---------------------------------------------------------------------------
# Convert LLM items → gap dicts compatible with existing scoring tools
# ---------------------------------------------------------------------------


def _llm_items_to_gap_dicts(llm_items: list[LLMGapItem]) -> list[dict]:
    """Normalise LLMGapItem objects into gap dicts for gap_scorer_tool / risk_tagger_tool."""
    gaps = []
    for item in llm_items:
        db_severity = _SEVERITY_MAP.get(item.severity, "watch")
        raw_gap_type = (item.gap_type or "missing_division").lower()
        db_gap_type = _GAP_TYPE_MAP.get(raw_gap_type, "missing")

        # Derive a short title from the first sentence of the description
        title = (item.description.split(".")[0] or item.description)[:200]

        gaps.append(
            {
                "division_number": item.affected_csi_division,
                "section_number": None,
                "title": title,
                "gap_type": db_gap_type,
                "severity": db_severity,
                "description": item.description,
                "recommendation": item.recommendation,
            }
        )
    return gaps


# ---------------------------------------------------------------------------
# Spec retrieval helpers — inject real spec text into the LLM prompt
# ---------------------------------------------------------------------------

# Queries that retrieve the spec language most relevant to gap categories
_RETRIEVAL_QUERIES = [
    "concrete mix design compressive strength requirements",
    "reinforcing steel bar size grade specification",
    "formwork shoring falsework requirements",
    "testing inspection quality control requirements",
    "submittals shop drawings submittal schedule",
    "waterproofing moisture protection membrane",
    "mechanical electrical plumbing coordination",
]


def _retrieve_spec_context_for_gaps(project_id: int) -> str:
    """Retrieve real spec language to ground gap analysis in project-specific requirements.

    Attempts to auto-index the project if not yet indexed.
    Returns a formatted REFERENCE MATERIAL block, or "" if retrieval is unavailable.
    """
    try:
        from apex.backend.retrieval.embedder import is_available

        if not is_available():
            return ""

        from apex.backend.retrieval.retriever import format_for_agent, search_multi
        from apex.backend.retrieval.store import collection_exists

        if not collection_exists(project_id):
            logger.info(
                f"Agent 3: project {project_id} not yet indexed — retrieval context unavailable. "
                "Index the project via POST /api/projects/{id}/specs/index to enable spec-grounded gaps."
            )
            return ""

        chunks = search_multi(
            project_id,
            queries=_RETRIEVAL_QUERIES,
            top_k_each=2,
            min_score=0.3,
        )

        if not chunks:
            logger.debug(f"Agent 3: no relevant spec chunks retrieved for project {project_id}")
            return ""

        logger.info(f"Agent 3: retrieved {len(chunks)} spec chunks for gap analysis context (project {project_id})")
        return format_for_agent(chunks, label="SPEC REFERENCE MATERIAL")

    except Exception as exc:
        logger.warning(f"Agent 3: spec retrieval failed (non-fatal, continuing without context): {exc}")
        return ""


# ---------------------------------------------------------------------------
# Main agent entry point
# ---------------------------------------------------------------------------


def run_gap_analysis_agent(db: Session, project_id: int) -> dict:
    """Run gap analysis comparing project specs against master checklist.

    Execution order:
      1. Try LLM path — get_llm_provider(agent_number=3), health-check, call LLM.
      2. If LLM unavailable or returns nothing, fall back to rule-based checklist diff.

    Returns dict validated against Agent3Output pipeline contract.
    """
    # Fetch all parsed spec sections for this project
    sections = (
        db.query(SpecSection)
        .filter(
            SpecSection.project_id == project_id,
            SpecSection.is_deleted == False,  # noqa: E712
        )
        .all()
    )

    parsed_sections = [
        {
            "division_number": s.division_number,
            "section_number": s.section_number,
            "title": s.title,
        }
        for s in sections
    ]

    # -----------------------------------------------------------------------
    # Attempt LLM-powered gap analysis
    # -----------------------------------------------------------------------
    provider = None
    llm_available = False
    analysis_method = "rule_based"
    scored_gaps: list[dict] = []

    try:
        from apex.backend.services.llm_provider import get_llm_provider

        provider = get_llm_provider(agent_number=3)
        try:
            llm_available = _run_async(
                asyncio.wait_for(provider.health_check(), timeout=HEALTH_CHECK_TIMEOUT_SECONDS)
            )
        except TimeoutError:
            logger.warning(
                f"Agent 3: LLM provider '{provider.provider_name}' health check timed out "
                f"after {HEALTH_CHECK_TIMEOUT_SECONDS}s — using rule-based fallback"
            )
            llm_available = False
        if llm_available:
            logger.info(
                f"Agent 3: LLM provider '{provider.provider_name}/{provider.model_name}' "
                "is available — attempting LLM gap analysis"
            )
        else:
            logger.info(f"Agent 3: LLM provider '{provider.provider_name}' is unreachable — using rule-based fallback")
    except Exception as exc:
        logger.warning(f"Agent 3: could not initialise LLM provider ({exc}) — using rule-based fallback")

    if llm_available and provider is not None:
        # Retrieve real spec language to ground the LLM's gap analysis
        spec_context = _retrieve_spec_context_for_gaps(project_id)
        if spec_context:
            logger.info("Agent 3: injecting spec retrieval context into LLM prompt")
        llm_items, in_tok, out_tok, cache_create, cache_read = _run_async(
            _llm_gap_analysis(parsed_sections, provider, spec_context=spec_context)
        )
        if llm_items:
            log_token_usage(
                db=db,
                project_id=project_id,
                agent_number=3,
                provider=provider.provider_name,
                model=provider.model_name,
                input_tokens=in_tok,
                output_tokens=out_tok,
                cache_creation_tokens=cache_create,
                cache_read_tokens=cache_read,
            )
            analysis_method = "llm"
            gap_dicts = _llm_items_to_gap_dicts(llm_items)
            for gap in gap_dicts:
                scored_gaps.append(risk_tagger_tool(gap))
            logger.info(
                f"Agent 3: LLM path succeeded — {len(scored_gaps)} gaps identified "
                f"(provider={provider.provider_name}, model={provider.model_name})"
            )
        else:
            logger.warning("Agent 3: LLM returned no valid gap items — falling back to rule-based analysis")

    # -----------------------------------------------------------------------
    # Rule-based fallback — Sprint 17.2-v2: domain rules Priority 1, generic Priority 2
    # -----------------------------------------------------------------------
    if analysis_method == "rule_based":
        spec_text_parts = []
        for s in sections:
            for field in ("raw_text", "work_description", "execution_requirements", "submittal_requirements"):
                v = getattr(s, field, None)
                if v:
                    spec_text_parts.append(str(v))
        spec_text = " ".join(spec_text_parts)

        domain_gaps: list[dict] = []
        try:
            domain_gaps = run_domain_rules(parsed_sections, spec_content_text=spec_text)
        except Exception as exc:
            logger.warning(f"Agent 3: domain rules engine failed ({exc}) — continuing to generic checklist")
            domain_gaps = []

        if domain_gaps:
            logger.info(f"Agent 3: domain rules fired {len(domain_gaps)} findings — using as primary fallback output")
            for gap in domain_gaps:
                scored_gaps.append(risk_tagger_tool(gap))
        else:
            logger.info("Agent 3: no domain rules triggered — falling back to generic CSI checklist")
            project_divisions = set(s.division_number for s in sections)
            core_divisions = {"03", "05", "07", "08", "09"}
            check_divisions = project_divisions | core_divisions
            checklist = {div: items for div, items in MASTER_SCOPE_CHECKLIST.items() if div in check_divisions}
            gaps = checklist_compare_tool(parsed_sections, checklist)
            for gap in gaps:
                scored_gaps.append(risk_tagger_tool(gap))

    # -----------------------------------------------------------------------
    # Score, persist, and return
    # -----------------------------------------------------------------------
    scores = gap_scorer_tool(scored_gaps)

    report = GapReport(
        project_id=project_id,
        overall_score=scores["overall_score"],
        total_gaps=scores["total_gaps"],
        critical_count=scores["critical_count"],
        moderate_count=scores["moderate_count"],
        watch_count=scores["watch_count"],
        summary=(
            f"Analysis of {len(parsed_sections)} spec sections via {analysis_method}. "
            f"Found {scores['total_gaps']} gaps: "
            f"{scores['critical_count']} critical, "
            f"{scores['moderate_count']} moderate, "
            f"{scores['watch_count']} watch."
        ),
        metadata_json={"analysis_method": analysis_method},
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    for gap in scored_gaps:
        base_description = gap.get("description") or ""
        extra_blocks: list[str] = []
        if gap.get("typical_responsibility"):
            extra_blocks.append(f"[Typical responsibility]\n{gap['typical_responsibility']}")
        if gap.get("cost_impact_description"):
            cost_line = gap["cost_impact_description"]
            if gap.get("cost_unit"):
                cost_line = f"{cost_line}  [unit: {gap['cost_unit']}]"
            extra_blocks.append(f"[Cost impact]\n{cost_line}")
        if gap.get("rfi_language"):
            extra_blocks.append(f"[Recommended RFI]\n{gap['rfi_language']}")
        if gap.get("rule_id"):
            extra_blocks.append(f"[Rule ID: {gap['rule_id']}]")
        full_description = base_description
        if extra_blocks:
            full_description = base_description + "\n\n" + "\n\n".join(extra_blocks)

        db.add(
            GapReportItem(
                gap_report_id=report.id,
                division_number=gap["division_number"],
                section_number=gap.get("section_number"),
                title=gap["title"],
                gap_type=gap["gap_type"],
                severity=gap["severity"],
                description=full_description or None,
                recommendation=gap.get("recommendation"),
                risk_score=gap.get("risk_score"),
            )
        )

    db.commit()

    # -----------------------------------------------------------------------
    # Spec-vs-Takeoff cross-reference pass (v2 enhancement)
    # Runs AFTER existing gap analysis. No LLM — keyword matching only.
    # -----------------------------------------------------------------------
    svt_gap_count = 0
    try:
        svt_gaps = _spec_vs_takeoff_gaps(db, project_id, sections)
        if svt_gaps:
            for gap in svt_gaps:
                db.add(
                    GapReportItem(
                        gap_report_id=report.id,
                        division_number=gap.get("division_number"),
                        section_number=gap.get("section_number"),
                        title=gap["title"],
                        gap_type=gap["gap_type"],
                        severity=gap["severity"],
                        description=gap.get("description"),
                        recommendation=gap.get("recommendation"),
                    )
                )
            db.commit()
            svt_gap_count = len(svt_gaps)

            # Update report totals
            report.total_gaps = (report.total_gaps or 0) + svt_gap_count
            report.critical_count = (report.critical_count or 0) + svt_gap_count  # all svt gaps are critical
            report.summary = (report.summary or "") + f" Spec-vs-takeoff: {svt_gap_count} cross-reference gaps."
            db.commit()

            logger.info(f"Agent 3: spec-vs-takeoff pass found {svt_gap_count} additional gaps")
        else:
            logger.info("Agent 3: spec-vs-takeoff pass — no additional gaps found")
    except Exception as exc:
        logger.warning(f"Agent 3: spec-vs-takeoff pass failed (non-fatal): {exc}")
        # HF-22: release the SQLAlchemy session if the failed db.commit() left
        # it in rolled-back state. Without this, every downstream operation on
        # this session — including the orchestrator's AgentRunLog status write
        # — raises PendingRollbackError, hanging the pipeline at status="running".
        db.rollback()

    total_gaps = scores["total_gaps"] + svt_gap_count
    critical_total = scores["critical_count"] + svt_gap_count

    logger.info(
        f"Agent 3 complete: {total_gaps} gaps ({svt_gap_count} spec-vs-takeoff), "
        f"analysis_method={analysis_method}, report_id={report.id}"
    )

    return validate_agent_output(
        3,
        {
            "total_gaps": total_gaps,
            "critical_count": critical_total,
            "moderate_count": scores["moderate_count"],
            "watch_count": scores["watch_count"],
            "overall_score": scores["overall_score"],
            "report_id": report.id,
            "sections_analyzed": len(parsed_sections),
            "spec_vs_takeoff_gaps": svt_gap_count,
        },
    )
