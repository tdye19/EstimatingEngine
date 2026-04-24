#!/usr/bin/env python3
"""Sprint 18.4.1 end-to-end Railway validation.

Asserts that Agent 3.5 (Scope Matcher) emits real findings + attributions on
a fresh pipeline run against real production data — the failure mode 18.4.1
was built to fix.

Workflow (Tucker-driven):
    1. Tucker creates a project on Railway, uploads 3 docs, clicks
       "Run Agent Pipeline" in the UI.
    2. Tucker runs this script with PROJECT_ID set.
    3. Script polls until pipeline completes, gathers evidence via the
       production API, runs every assertion, prints PASS/FAIL report.

Exit codes:
    0   all assertions pass
    1   one or more assertions fail (validation failure)
    2   infrastructure error (auth, network, missing project)

Environment / CLI:
    APEX_BASE_URL          (default: Railway prod URL)
    APEX_USERNAME          (default: admin@summitbuilders.com)
    APEX_PASSWORD          (default: admin123)
    PROJECT_ID             (REQUIRED — no default)
    POLL_TIMEOUT_SECONDS   (default: 900)
    POLL_INTERVAL_SECONDS  (default: 15)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
DEFAULT_BASE_URL = "https://web-production-f87116.up.railway.app"
DEFAULT_USERNAME = "admin@summitbuilders.com"
DEFAULT_PASSWORD = "admin123"
DEFAULT_POLL_TIMEOUT = 900
DEFAULT_POLL_INTERVAL = 15
HTTP_TIMEOUT = 30.0

# Pipeline order is [1, 2, 4, 3, 35, 5, 6] (apex/backend/services/agent_orchestrator.py:243).
# Agent 2B runs as a side-effect of Agent 2 and never writes an AgentRunLog row;
# its success is proxied by A3 (work_categories > 0). Agent 7 is not in the
# normal pipeline.
EXPECTED_AGENT_SLOTS: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 35)
PIPELINE_TERMINAL_STATUSES = {"completed", "failed", "skipped"}

# Match-tier vocabulary from apex/backend/services/scope_matcher.py.
TIER_UNMATCHED = "unmatched"
KNOWN_MATCH_TIERS = (
    "csi_exact",
    "spec_section_fuzzy",
    "activity_title_fuzzy",
    "llm_semantic",
    "unmatched",
)

SCOPE_MATCHER_NARRATIVE_MARKER = "SCOPE MATCHER FINDINGS"

EXIT_PASS = 0
EXIT_VALIDATION_FAIL = 1
EXIT_INFRASTRUCTURE = 2


# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    level=logging.INFO,
    stream=sys.stdout,
)
log = logging.getLogger("validate_18_4_1")


# --------------------------------------------------------------------------
# Data classes
# --------------------------------------------------------------------------
@dataclass
class Config:
    base_url: str
    username: str
    password: str
    project_id: int
    poll_timeout: int
    poll_interval: int


@dataclass
class Assertion:
    label: str
    expected: str
    actual: str
    passed: bool
    notes: str = ""
    severity: str = "FAIL"  # FAIL means a failure exits 1; WARN reports but doesn't fail


@dataclass
class Evidence:
    agent_run_logs: list[dict] = field(default_factory=list)
    work_categories: list[dict] = field(default_factory=list)
    gap_findings_payload: dict = field(default_factory=dict)
    attributions_payload: dict = field(default_factory=dict)
    intelligence_report: dict = field(default_factory=dict)
    pipeline_duration_seconds: float | None = None
    pipeline_start_iso: str | None = None


# --------------------------------------------------------------------------
# Infrastructure-error helper
# --------------------------------------------------------------------------
class InfrastructureError(Exception):
    """Raised when something prevents validation from running at all."""


def _die_infra(reason: str, exc: Exception | None = None) -> None:
    log.error("INFRASTRUCTURE ERROR: %s", reason)
    if exc is not None:
        log.error("  underlying: %r", exc)
    sys.exit(EXIT_INFRASTRUCTURE)


# --------------------------------------------------------------------------
# Config + auth
# --------------------------------------------------------------------------
def parse_config() -> Config:
    parser = argparse.ArgumentParser(description="Sprint 18.4.1 Railway validator")
    parser.add_argument("--base-url", default=os.getenv("APEX_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--username", default=os.getenv("APEX_USERNAME", DEFAULT_USERNAME))
    parser.add_argument("--password", default=os.getenv("APEX_PASSWORD", DEFAULT_PASSWORD))
    parser.add_argument(
        "--project-id",
        type=int,
        default=int(os.getenv("PROJECT_ID")) if os.getenv("PROJECT_ID") else None,
    )
    parser.add_argument(
        "--poll-timeout",
        type=int,
        default=int(os.getenv("POLL_TIMEOUT_SECONDS", DEFAULT_POLL_TIMEOUT)),
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=int(os.getenv("POLL_INTERVAL_SECONDS", DEFAULT_POLL_INTERVAL)),
    )
    args = parser.parse_args()

    if args.project_id is None:
        log.error("PROJECT_ID is required (env var or --project-id)")
        sys.exit(EXIT_INFRASTRUCTURE)

    return Config(
        base_url=args.base_url.rstrip("/"),
        username=args.username,
        password=args.password,
        project_id=args.project_id,
        poll_timeout=args.poll_timeout,
        poll_interval=args.poll_interval,
    )


def login(client: httpx.Client, cfg: Config) -> None:
    """POST /api/auth/login, install Authorization header on the client."""
    try:
        resp = client.post(
            "/api/auth/login",
            json={"email": cfg.username, "password": cfg.password},
        )
    except httpx.HTTPError as exc:
        _die_infra(f"login request failed for {cfg.base_url}", exc)

    if resp.status_code != 200:
        _die_infra(
            f"login returned HTTP {resp.status_code}: "
            f"{resp.text[:300]}"
        )

    data = resp.json()
    token = data.get("access_token")
    if not token:
        _die_infra(f"login response missing access_token: {data!r}")

    client.headers["Authorization"] = f"Bearer {token}"
    log.info("Authenticated as %s", cfg.username)


# --------------------------------------------------------------------------
# Polling phase
# --------------------------------------------------------------------------
def _latest_log_per_agent(logs: list[dict]) -> dict[int, dict]:
    """Pick the most recent run per agent_number (handles re-runs)."""
    latest: dict[int, dict] = {}
    for row in logs:
        n = row.get("agent_number")
        if n is None:
            continue
        existing = latest.get(n)
        if existing is None or (row.get("created_at") or "") > (existing.get("created_at") or ""):
            latest[n] = row
    return latest


def _pipeline_status(latest: dict[int, dict]) -> tuple[bool, str]:
    """Return (complete, reason). Complete iff every expected slot has a
    latest row in a terminal status."""
    missing = []
    still_running = []
    for slot in EXPECTED_AGENT_SLOTS:
        row = latest.get(slot)
        if row is None:
            missing.append(slot)
            continue
        if row.get("status") not in PIPELINE_TERMINAL_STATUSES:
            still_running.append(f"{slot}({row.get('status')})")
    if missing:
        return False, f"missing slots: {missing}"
    if still_running:
        return False, f"still running: {still_running}"
    return True, "all terminal"


def fetch_agent_run_logs(client: httpx.Client, project_id: int) -> list[dict]:
    resp = client.get(f"/api/projects/{project_id}/agent-run-logs")
    if resp.status_code == 404:
        _die_infra(f"project {project_id} not found")
    if resp.status_code != 200:
        _die_infra(
            f"agent-run-logs returned HTTP {resp.status_code}: {resp.text[:300]}"
        )
    body = resp.json()
    rows = body.get("data") if isinstance(body, dict) else None
    if rows is None:
        _die_infra(f"agent-run-logs response missing data field: {body!r}")
    return rows


def poll_until_complete(client: httpx.Client, cfg: Config) -> tuple[list[dict], float]:
    """Poll agent-run-logs until pipeline complete or timeout.

    Returns (final_logs, elapsed_seconds). Raises infra exit on timeout.
    """
    start = time.monotonic()
    log.info(
        "Polling /agent-run-logs every %ds (timeout %ds)",
        cfg.poll_interval,
        cfg.poll_timeout,
    )
    while True:
        try:
            logs = fetch_agent_run_logs(client, cfg.project_id)
        except httpx.HTTPError as exc:
            log.warning("transient fetch error during poll, retrying: %r", exc)
            time.sleep(cfg.poll_interval)
            continue

        latest = _latest_log_per_agent(logs)
        complete, reason = _pipeline_status(latest)
        elapsed = time.monotonic() - start

        if complete:
            log.info(
                "Pipeline complete after %.1fs (%d log rows, %d distinct agents)",
                elapsed,
                len(logs),
                len(latest),
            )
            return logs, elapsed

        if elapsed >= cfg.poll_timeout:
            log.error(
                "Pipeline did not complete within %ds (last status: %s)",
                cfg.poll_timeout,
                reason,
            )
            # Return what we have so the report can still print partial state.
            return logs, elapsed

        log.info("  pipeline status: %s (elapsed %.0fs)", reason, elapsed)
        time.sleep(cfg.poll_interval)


# --------------------------------------------------------------------------
# Evidence gathering
# --------------------------------------------------------------------------
def _get_json(client: httpx.Client, path: str, *, allow_404: bool = False) -> Any:
    try:
        resp = client.get(path)
    except httpx.HTTPError as exc:
        raise InfrastructureError(f"GET {path} failed: {exc!r}") from exc
    if resp.status_code == 404 and allow_404:
        return None
    if resp.status_code != 200:
        raise InfrastructureError(
            f"GET {path} returned HTTP {resp.status_code}: {resp.text[:300]}"
        )
    return resp.json()


def gather_evidence(
    client: httpx.Client,
    cfg: Config,
    logs: list[dict],
    pipeline_elapsed: float,
) -> Evidence:
    """Pull every endpoint we'll assert against. Network errors here are
    infrastructure failures (exit 2), not validation failures."""
    pid = cfg.project_id
    try:
        wc_raw = _get_json(client, f"/api/projects/{pid}/work-categories")
        gap_payload = _get_json(client, f"/api/projects/{pid}/gap-findings")
        attr_payload = _get_json(client, f"/api/projects/{pid}/line-item-attributions")
        ir_payload = _get_json(client, f"/api/projects/{pid}/intelligence-report")
    except InfrastructureError as exc:
        _die_infra(str(exc))

    # work-categories returns a raw array (NOT APIResponse-wrapped).
    if not isinstance(wc_raw, list):
        _die_infra(f"work-categories returned non-list: {type(wc_raw).__name__}")

    gap_data = (gap_payload or {}).get("data") or {}
    attr_data = (attr_payload or {}).get("data") or {}
    ir_data = (ir_payload or {}).get("data") or {}

    # Pipeline start reference (Amendment 1): earliest started_at across ALL
    # agent-run-log rows for this project. Robust to delay between
    # trigger-time and script-launch-time.
    start_times = [r["started_at"] for r in logs if r.get("started_at")]
    pipeline_start = min(start_times) if start_times else None

    return Evidence(
        agent_run_logs=logs,
        work_categories=wc_raw,
        gap_findings_payload=gap_data,
        attributions_payload=attr_data,
        intelligence_report=ir_data,
        pipeline_duration_seconds=pipeline_elapsed,
        pipeline_start_iso=pipeline_start,
    )


# --------------------------------------------------------------------------
# Helpers shared across assertions
# --------------------------------------------------------------------------
def _output_data(row: dict) -> dict:
    """Return output_data as a dict (or empty dict if missing/non-dict)."""
    od = row.get("output_data")
    return od if isinstance(od, dict) else {}


def _flatten_findings(payload: dict) -> list[dict]:
    """Flatten the {finding_type: [rows]} dict into a single list (Amendment 2)."""
    grouped = payload.get("findings") or {}
    out: list[dict] = []
    if isinstance(grouped, dict):
        for _ftype, rows in grouped.items():
            if isinstance(rows, list):
                out.extend(rows)
    return out


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        # Tolerate both naive ISO and Z-suffixed ISO.
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Assertions
# --------------------------------------------------------------------------
def _agent_label(num: int) -> str:
    return "3.5" if num == 35 else str(num)


def assert_a1_all_slots_present(ev: Evidence) -> Assertion:
    latest = _latest_log_per_agent(ev.agent_run_logs)
    missing = sorted(set(EXPECTED_AGENT_SLOTS) - latest.keys())

    if missing:
        return Assertion(
            "A1",
            expected=f"7/7 slots {sorted(EXPECTED_AGENT_SLOTS)}",
            actual=f"{len(EXPECTED_AGENT_SLOTS) - len(missing)}/7 (missing {missing})",
            passed=False,
            notes="missing agent run logs for required slots",
        )

    # Bucket by status. Anything other than "completed" is a fail — this
    # catches both pre-terminal states (running/queued, possible after
    # poll timeout) and terminal-but-bad states (failed/skipped).
    by_status: dict[str, list[str]] = {}
    for n in EXPECTED_AGENT_SLOTS:
        st = (latest[n].get("status") or "unknown")
        by_status.setdefault(st, []).append(_agent_label(n))

    bad = {st: agents for st, agents in by_status.items() if st != "completed"}
    if bad:
        return Assertion(
            "A1",
            expected="7/7 completed",
            actual=f"non-completed: {bad}",
            passed=False,
            notes="some agents not in status=completed (poll may have timed out)",
        )

    return Assertion(
        "A1",
        expected="7/7 completed",
        actual="7/7 completed",
        passed=True,
    )


def assert_a2_takeoff_count(ev: Evidence) -> tuple[Assertion, int]:
    """Returns (assertion, takeoff_count). Count is 0 on miss, used by A5."""
    latest = _latest_log_per_agent(ev.agent_run_logs)
    a4 = latest.get(4)
    od = _output_data(a4) if a4 else {}
    count = od.get("takeoff_items_parsed")
    if not isinstance(count, int):
        return (
            Assertion(
                "A2",
                expected=">0 (output_data.takeoff_items_parsed)",
                actual=f"missing/non-int (got {count!r})",
                passed=False,
                notes="Agent 4 didn't emit takeoff_items_parsed",
            ),
            0,
        )
    return (
        Assertion(
            "A2",
            expected=">0",
            actual=str(count),
            passed=count > 0,
        ),
        count,
    )


def assert_a3_work_categories(ev: Evidence) -> tuple[Assertion, int]:
    n = len(ev.work_categories)
    return (
        Assertion(
            "A3",
            expected=">=1 (proxy for Agent 2B success)",
            actual=str(n),
            passed=n >= 1,
            notes="" if n >= 1 else "no work categories — scope matcher cannot fire",
        ),
        n,
    )


def assert_a4_findings_created(ev: Evidence) -> tuple[Assertion, int]:
    """The critical assertion 18.4.1 was built for."""
    latest = _latest_log_per_agent(ev.agent_run_logs)
    a35 = latest.get(35)
    od = _output_data(a35) if a35 else {}
    val = od.get("findings_created")
    if not isinstance(val, int):
        return (
            Assertion(
                "A4",
                expected=">0 (output_data.findings_created)",
                actual=f"missing/non-int (got {val!r})",
                passed=False,
                notes="Agent 3.5 didn't emit findings_created",
            ),
            0,
        )
    return (
        Assertion(
            "A4",
            expected=">0",
            actual=str(val),
            passed=val > 0,
            notes="" if val > 0 else "matcher emitted zero findings — 18.4.1 regression",
        ),
        val,
    )


def assert_a5_attributions_count(ev: Evidence, takeoff_count: int) -> tuple[Assertion, int]:
    latest = _latest_log_per_agent(ev.agent_run_logs)
    a35 = latest.get(35)
    od = _output_data(a35) if a35 else {}
    val = od.get("attributions_created")
    if not isinstance(val, int):
        return (
            Assertion(
                "A5",
                expected=f"~{takeoff_count} (output_data.attributions_created)",
                actual=f"missing/non-int (got {val!r})",
                passed=False,
            ),
            0,
        )

    notes = ""
    severity = "FAIL"
    if takeoff_count == 0:
        passed = val > 0
        notes = "takeoff_count was 0; can't compute delta"
    else:
        delta_pct = abs(val - takeoff_count) / takeoff_count * 100
        notes = f"delta {((val - takeoff_count) / takeoff_count * 100):+.1f}%"
        # Pass requires >0 AND within 5% — but >5% delta is a WARN, not a hard fail.
        if val <= 0:
            passed = False
        elif delta_pct > 5.0:
            passed = True  # report-as-warn handled below
            severity = "WARN"
            notes += " (>5% — surface for review)"
        else:
            passed = True

    return (
        Assertion(
            "A5",
            expected=f"~{takeoff_count} (within 5%)" if takeoff_count else ">0",
            actual=str(val),
            passed=passed,
            notes=notes,
            severity=severity,
        ),
        val,
    )


def assert_a6_findings_freshness(ev: Evidence, findings_created: int) -> Assertion:
    findings = _flatten_findings(ev.gap_findings_payload)
    n = len(findings)

    # Count check.
    if n < findings_created:
        return Assertion(
            "A6",
            expected=f">={findings_created} fresh",
            actual=f"{n} returned (count < findings_created)",
            passed=False,
            notes="DB has fewer rows than Agent 3.5 reported emitting",
        )

    # Freshness check (Amendment 1: pipeline_start = min(started_at)).
    ref = _parse_iso(ev.pipeline_start_iso)
    if ref is None:
        return Assertion(
            "A6",
            expected=f">={findings_created} fresh",
            actual=f"{n} returned",
            passed=True,
            notes="no pipeline_start reference (no started_at on any agent log)",
        )

    stale = []
    for f in findings:
        ts = _parse_iso(f.get("created_at"))
        if ts is None:
            continue
        if ts < ref:
            stale.append(f.get("id"))

    if stale:
        return Assertion(
            "A6",
            expected="all created_at >= pipeline_start",
            actual=f"{len(stale)} stale (ids: {stale[:5]}{'...' if len(stale) > 5 else ''})",
            passed=False,
            notes=f"stale findings predate pipeline_start={ev.pipeline_start_iso}",
        )

    return Assertion(
        "A6",
        expected=f">={findings_created} fresh",
        actual=f"{n} fresh",
        passed=True,
    )


def assert_a7_match_tier_mix(ev: Evidence) -> Assertion:
    """Amendment 3: read output_data.attributions_by_tier; assert sum of
    non-unmatched > 0; print full breakdown regardless."""
    latest = _latest_log_per_agent(ev.agent_run_logs)
    a35 = latest.get(35)
    od = _output_data(a35) if a35 else {}
    by_tier = od.get("attributions_by_tier")
    if not isinstance(by_tier, dict):
        return Assertion(
            "A7",
            expected="dict with non-unmatched > 0",
            actual=f"missing/non-dict (got {by_tier!r})",
            passed=False,
        )

    total_unmatched = by_tier.get(TIER_UNMATCHED, 0)
    matched_total = sum(v for k, v in by_tier.items() if k != TIER_UNMATCHED)
    breakdown = ",".join(f"{k}={v}" for k, v in sorted(by_tier.items()))

    if matched_total <= 0 and total_unmatched > 0:
        # Soft-pass-but-loud (per Amendment 3): WC exists but matcher
        # found nothing to attribute. Possible but suspect.
        return Assertion(
            "A7",
            expected="any non-unmatched tier > 0",
            actual=breakdown,
            passed=True,
            severity="WARN",
            notes=(
                f"all {total_unmatched} attributions are unmatched — "
                "WC may not align with takeoff data"
            ),
        )

    if matched_total <= 0:
        return Assertion(
            "A7",
            expected="any non-unmatched tier > 0",
            actual=breakdown or "(empty)",
            passed=False,
            notes="no attributions at all",
        )

    return Assertion(
        "A7",
        expected="non-unmatched > 0",
        actual=breakdown,
        passed=True,
    )


def assert_a8_attribution_endpoint_count(
    ev: Evidence, attributions_created: int
) -> Assertion:
    rows = ev.attributions_payload.get("attributions") or []
    n = len(rows)
    return Assertion(
        "A8",
        expected=f"={attributions_created}",
        actual=str(n),
        passed=n == attributions_created,
        notes="" if n == attributions_created else "endpoint count != log count",
    )


def assert_a9_narrative_marker(ev: Evidence) -> Assertion:
    narrative = ev.intelligence_report.get("executive_narrative") or ""
    has = SCOPE_MATCHER_NARRATIVE_MARKER in narrative
    if has:
        # Find the surrounding context for the report.
        idx = narrative.find(SCOPE_MATCHER_NARRATIVE_MARKER)
        snippet = narrative[idx : idx + 120].replace("\n", " ")
        return Assertion(
            "A9",
            expected=f"contains {SCOPE_MATCHER_NARRATIVE_MARKER!r}",
            actual=f"present: {snippet!r}",
            passed=True,
        )

    if not narrative:
        return Assertion(
            "A9",
            expected=f"contains {SCOPE_MATCHER_NARRATIVE_MARKER!r}",
            actual="(no narrative — no intelligence report)",
            passed=False,
            notes="intelligence-report endpoint returned no executive_narrative",
        )

    preview = narrative[:300].replace("\n", " ")
    return Assertion(
        "A9",
        expected=f"contains {SCOPE_MATCHER_NARRATIVE_MARKER!r}",
        actual=f"missing — narrative preview: {preview!r}",
        passed=False,
    )


def assert_a10_no_agent_errors(ev: Evidence) -> Assertion:
    latest = _latest_log_per_agent(ev.agent_run_logs)
    errs = []
    for slot, row in latest.items():
        if slot not in EXPECTED_AGENT_SLOTS:
            continue
        od = _output_data(row)
        err = od.get("error")
        if err:
            errs.append((slot, str(err)[:120]))
        # Also surface error_message field if status was failed.
        if row.get("status") == "failed" and row.get("error_message"):
            errs.append((slot, f"error_message={str(row['error_message'])[:120]}"))
    if errs:
        return Assertion(
            "A10",
            expected="no errors in any agent's output_data",
            actual=f"errors found: {errs}",
            passed=False,
        )
    return Assertion(
        "A10",
        expected="no errors",
        actual="ok",
        passed=True,
    )


def assert_a11_attribution_consistency(
    ev: Evidence, attributions_created: int
) -> Assertion:
    """Amendment: log.attributions_created must match endpoint row count."""
    rows = ev.attributions_payload.get("attributions") or []
    n = len(rows)
    return Assertion(
        "A11",
        expected=f"log({attributions_created}) == endpoint({n})",
        actual=f"log={attributions_created} endpoint={n}",
        passed=n == attributions_created,
        notes="" if n == attributions_created else "log/DB drift — investigate",
    )


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------
def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def print_report(cfg: Config, ev: Evidence, assertions: list[Assertion]) -> int:
    sep = "=" * 72
    print()
    print(sep)
    print(f"SPRINT 18.4.1 VALIDATION — PROJECT {cfg.project_id}")
    print(sep)
    print(f"Railway:           {cfg.base_url}")
    if ev.pipeline_duration_seconds is not None:
        print(f"Polling duration:  {ev.pipeline_duration_seconds:.1f}s")
    if ev.pipeline_start_iso:
        print(f"Pipeline start:    {ev.pipeline_start_iso}")
    print(f"Takeoff items V2:  {(_output_data(_latest_log_per_agent(ev.agent_run_logs).get(4) or {}) or {}).get('takeoff_items_parsed', '?')}")
    print(f"Work categories:   {len(ev.work_categories)}")
    print()
    # Header
    print(f"  {'Label':<5} {'Status':<6} {'Expected':<35} {'Actual':<35} Notes")
    print(f"  {'-'*5} {'-'*6} {'-'*35} {'-'*35} {'-'*30}")
    fail_count = 0
    warn_count = 0
    for a in assertions:
        if a.passed:
            status = "WARN" if a.severity == "WARN" else "PASS"
        else:
            status = "FAIL"
        if status == "FAIL":
            fail_count += 1
        elif status == "WARN":
            warn_count += 1
        print(
            f"  {a.label:<5} {status:<6} "
            f"{_truncate(a.expected, 35):<35} "
            f"{_truncate(a.actual, 35):<35} "
            f"{_truncate(a.notes, 60)}"
        )
    print()
    total = len(assertions)
    passed = total - fail_count  # WARN counts as pass-with-caveat
    if fail_count == 0 and warn_count == 0:
        verdict = "PASS"
        exit_code = EXIT_PASS
    elif fail_count == 0:
        verdict = f"PASS ({warn_count} warn)"
        exit_code = EXIT_PASS
    else:
        verdict = "FAIL"
        exit_code = EXIT_VALIDATION_FAIL
    print(f"OVERALL: {verdict}   ({passed}/{total} assertions, {warn_count} warn, {fail_count} fail)")
    print(sep)
    return exit_code


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main() -> int:
    cfg = parse_config()
    log.info("Validating project %d on %s", cfg.project_id, cfg.base_url)

    with httpx.Client(base_url=cfg.base_url, timeout=HTTP_TIMEOUT) as client:
        # Sanity: hit /api/health first so a Railway outage exits 2 cleanly.
        try:
            health = client.get("/api/health")
        except httpx.HTTPError as exc:
            _die_infra(f"health check unreachable at {cfg.base_url}", exc)
        if health.status_code != 200:
            _die_infra(f"health returned HTTP {health.status_code}: {health.text[:200]}")
        log.info("Backend healthy: %s", health.json())

        login(client, cfg)

        logs, elapsed = poll_until_complete(client, cfg)
        ev = gather_evidence(client, cfg, logs, elapsed)

    # Run every assertion. None short-circuit.
    assertions: list[Assertion] = []
    a1 = assert_a1_all_slots_present(ev)
    a2, takeoff_count = assert_a2_takeoff_count(ev)
    a3, _wc_count = assert_a3_work_categories(ev)
    a4, findings_created = assert_a4_findings_created(ev)
    a5, attributions_created = assert_a5_attributions_count(ev, takeoff_count)
    a6 = assert_a6_findings_freshness(ev, findings_created)
    a7 = assert_a7_match_tier_mix(ev)
    a8 = assert_a8_attribution_endpoint_count(ev, attributions_created)
    a9 = assert_a9_narrative_marker(ev)
    a10 = assert_a10_no_agent_errors(ev)
    a11 = assert_a11_attribution_consistency(ev, attributions_created)
    assertions.extend([a1, a2, a3, a4, a5, a6, a7, a8, a9, a10, a11])

    return print_report(cfg, ev, assertions)


if __name__ == "__main__":
    sys.exit(main())
