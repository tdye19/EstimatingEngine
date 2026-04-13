"""Pipeline end-to-end integration test.

Runs the full APEX agent pipeline against a real file and produces a
structured pass/fail report.  This is a standalone CLI tool — NOT a unit test.

Usage:
    python -m apex.backend.tests.test_pipeline_e2e ./test_specs/sample.pdf
    python -m apex.backend.tests.test_pipeline_e2e ./apex/backend/tests/fixtures/sample_spec.txt
    python -m apex.backend.tests.test_pipeline_e2e ./file.xlsx --mode winest_import
    python -m apex.backend.tests.test_pipeline_e2e ./file.pdf --base-url http://localhost:8000

Exit codes:
    0  — accuracy score >= 70%
    1  — accuracy score < 70%, or the pipeline itself errored
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LARGE_FILE_THRESHOLD = 2 * 1024 * 1024  # 2 MB → use chunked upload
POLL_INTERVAL = 5  # seconds between status checks
PIPELINE_TIMEOUT = 300  # 5 minutes total

AGENT_NAMES = {
    1: "Document Ingestion",
    2: "Spec Parser",
    3: "Gap Analysis",
    4: "Quantity Takeoff",
    5: "Labor Productivity",
    6: "Estimate Assembly",
    7: "IMPROVE Feedback",
}

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"
SKIP = "SKIP"

STATUS_ICON = {
    PASS: "✅",
    WARN: "⚠️ ",
    FAIL: "❌",
    SKIP: "⏭️ ",
}


class AgentResult:
    def __init__(
        self,
        number: int,
        verdict: str,
        duration: float,
        detail: str,
    ):
        self.number = number
        self.name = AGENT_NAMES.get(number, f"Agent {number}")
        self.verdict = verdict
        self.duration = duration
        self.detail = detail

    def format_line(self) -> str:
        icon = STATUS_ICON[self.verdict]
        label = f"Agent {self.number} — {self.name}"
        pad = max(0, 36 - len(label))
        return f"  {label}{' ' * pad}{icon} {self.verdict:<4}  ({self.duration:.1f}s)  {self.detail}"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _raise_for_status(resp: httpx.Response, context: str) -> dict:
    if resp.status_code >= 400:
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        raise RuntimeError(f"{context} — HTTP {resp.status_code}: {body}")
    return resp.json()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def authenticate(client: httpx.Client, email: str, password: str) -> str:
    resp = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    data = _raise_for_status(resp, "Authentication")
    token = data.get("access_token")
    if not token:
        raise RuntimeError(f"Login response missing access_token: {data}")
    return token


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------


def create_project(client: httpx.Client, filename: str) -> int:
    name = f"E2E Test — {Path(filename).name} — {datetime.now().strftime('%H:%M:%S')}"
    resp = client.post(
        "/api/projects",
        json={"name": name, "project_type": "commercial"},
    )
    data = _raise_for_status(resp, "Create project")
    project_id = data["data"]["id"]
    return project_id


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


def upload_file(client: httpx.Client, project_id: int, file_path: Path) -> int:
    """Upload file.  Uses chunked protocol for files >2 MB, simple POST otherwise.

    Returns the document ID.
    """
    file_size = file_path.stat().st_size
    if file_size > LARGE_FILE_THRESHOLD:
        return _chunked_upload(client, project_id, file_path, file_size)
    return _simple_upload(client, project_id, file_path)


def _simple_upload(client: httpx.Client, project_id: int, file_path: Path) -> int:
    with open(file_path, "rb") as fh:
        resp = client.post(
            f"/api/projects/{project_id}/documents",
            files={"file": (file_path.name, fh)},
        )
    data = _raise_for_status(resp, "Simple upload")
    return data["data"]["id"]


def _chunked_upload(client: httpx.Client, project_id: int, file_path: Path, file_size: int) -> int:
    # 1. Init session
    resp = client.post(
        f"/api/projects/{project_id}/documents/upload/init",
        json={
            "filename": file_path.name,
            "file_size": file_size,
            "content_type": "application/octet-stream",
        },
    )
    init_data = _raise_for_status(resp, "Chunked upload init")
    upload_id = init_data["data"]["upload_id"]
    chunk_size = init_data["data"]["chunk_size"]

    # 2. Upload chunks
    with open(file_path, "rb") as fh:
        chunk_number = 0
        while True:
            chunk_data = fh.read(chunk_size)
            if not chunk_data:
                break
            resp = client.post(
                f"/api/projects/{project_id}/documents/upload/{upload_id}/chunk",
                params={"chunk_number": chunk_number},
                files={"chunk": (file_path.name, chunk_data)},
            )
            _raise_for_status(resp, f"Upload chunk {chunk_number}")
            chunk_number += 1

    # 3. Complete — server triggers pipeline automatically
    resp = client.post(
        f"/api/projects/{project_id}/documents/upload/{upload_id}/complete",
    )
    complete_data = _raise_for_status(resp, "Chunked upload complete")
    return complete_data["data"]["id"]


# ---------------------------------------------------------------------------
# Pipeline trigger & polling
# ---------------------------------------------------------------------------


def trigger_pipeline(
    client: httpx.Client,
    project_id: int,
    document_id: int,
    mode: str,
) -> None:
    """Explicitly trigger the pipeline (also triggered by chunked upload complete)."""
    resp = client.post(
        f"/api/projects/{project_id}/pipeline/run",
        params={"document_id": document_id, "pipeline_mode": mode},
    )
    _raise_for_status(resp, "Trigger pipeline")


def poll_pipeline(client: httpx.Client, project_id: int) -> dict:
    """Block until the pipeline reaches a terminal state.

    Returns the final PipelineStatusOut payload (as dict).
    Raises RuntimeError on timeout or error.
    """
    deadline = time.monotonic() + PIPELINE_TIMEOUT
    dots = 0
    while time.monotonic() < deadline:
        resp = client.get(f"/api/projects/{project_id}/pipeline/status")
        data = _raise_for_status(resp, "Poll pipeline status")
        overall = data.get("overall", "")
        if overall in ("completed", "failed"):
            print()  # newline after progress dots
            return data
        # Print progress indicator
        dots += 1
        print(f"\r  Waiting for pipeline… {dots * '.':<30}", end="", flush=True)
        time.sleep(POLL_INTERVAL)

    print()
    raise RuntimeError(f"Pipeline did not complete within {PIPELINE_TIMEOUT}s timeout")


# ---------------------------------------------------------------------------
# Result collection
# ---------------------------------------------------------------------------


def collect_results(client: httpx.Client, project_id: int) -> dict[str, Any]:
    """Fetch all result endpoints and return a combined dict."""
    results: dict[str, Any] = {}

    def _get(key: str, path: str) -> None:
        try:
            resp = client.get(path)
            if resp.status_code == 200:
                results[key] = resp.json().get("data")
            else:
                results[key] = None
        except Exception as exc:
            results[key] = None
            results[f"{key}_error"] = str(exc)

    _get("spec_sections", f"/api/projects/{project_id}/spec-sections")
    _get("gap_report", f"/api/projects/{project_id}/gap-report")
    _get("takeoff_items", f"/api/projects/{project_id}/takeoff")
    _get("labor_estimates", f"/api/projects/{project_id}/labor-estimates")
    _get("estimate", f"/api/projects/{project_id}/estimate")
    _get("agent_logs", f"/api/projects/{project_id}/agent-logs")
    _get("token_usage", f"/api/projects/{project_id}/token-usage")

    return results


# ---------------------------------------------------------------------------
# Pass/fail evaluation
# ---------------------------------------------------------------------------


def _agent_log(agent_logs: list[dict], number: int) -> dict | None:
    """Return the most-recent log entry for the given agent number."""
    entries = [entry for entry in (agent_logs or []) if entry.get("agent_number") == number]
    return entries[0] if entries else None


def _log_duration(log: dict | None) -> float:
    return float(log.get("duration_seconds") or 0.0) if log else 0.0


def evaluate_agents(
    pipeline_status: dict,
    results: dict[str, Any],
    mode: str,
) -> list[AgentResult]:
    """Apply pass criteria to produce an AgentResult for each agent."""
    agent_logs: list[dict] = results.get("agent_logs") or []

    # Index pipeline status by agent_number for quick lookup
    status_by_agent: dict[int, dict] = {}
    for a in pipeline_status.get("agents", []):
        status_by_agent[a["agent_number"]] = a

    evaluations: list[AgentResult] = []

    # ── Agent 1 — Document Ingestion ─────────────────────────────────────
    log1 = _agent_log(agent_logs, 1)
    s1 = status_by_agent.get(1, {})
    if (s1.get("status") or log1 and log1.get("status")) == "completed" or (log1 and log1.get("status") == "completed"):
        # Check output_summary for any extracted content signal
        summary = (log1 or {}).get("output_summary") or s1.get("output_summary") or ""
        detail = summary[:80] if summary else "Ingestion completed"
        evaluations.append(AgentResult(1, PASS, _log_duration(log1), detail))
    elif (s1.get("status") or "") == "skipped" or (log1 and log1.get("status") == "skipped"):
        evaluations.append(AgentResult(1, SKIP, 0.0, "Skipped by orchestrator"))
    else:
        err = (log1 or {}).get("error_message") or s1.get("error_message") or "No log found"
        evaluations.append(AgentResult(1, FAIL, _log_duration(log1), err[:80]))

    # ── Agent 2 — Spec Parser ─────────────────────────────────────────────
    if mode == "winest_import":
        evaluations.append(AgentResult(2, SKIP, 0.0, "Skipped — WinEst import mode"))
    else:
        log2 = _agent_log(agent_logs, 2)
        s2 = status_by_agent.get(2, {})
        status2 = (log2 or {}).get("status") or s2.get("status") or ""
        sections: list[dict] = results.get("spec_sections") or []
        if status2 == "completed" and len(sections) > 0:
            csi_divs = sorted({s.get("division_number", "") for s in sections if s.get("division_number")})
            evaluations.append(
                AgentResult(
                    2,
                    PASS,
                    _log_duration(log2),
                    f"Found {len(sections)} CSI sections  "
                    f"(Div: {', '.join(csi_divs[:5])}{'…' if len(csi_divs) > 5 else ''})",
                )
            )
        elif status2 in ("skipped",):
            evaluations.append(AgentResult(2, SKIP, 0.0, "Skipped by orchestrator"))
        elif status2 == "completed" and len(sections) == 0:
            evaluations.append(AgentResult(2, FAIL, _log_duration(log2), "Completed but 0 spec sections stored"))
        else:
            err = (log2 or {}).get("error_message") or s2.get("error_message") or "No log found"
            evaluations.append(AgentResult(2, FAIL, _log_duration(log2), err[:80]))

    # ── Agent 3 — Gap Analysis ────────────────────────────────────────────
    log3 = _agent_log(agent_logs, 3)
    s3 = status_by_agent.get(3, {})
    status3 = (log3 or {}).get("status") or s3.get("status") or ""
    gap_report: dict | None = results.get("gap_report")
    if status3 == "completed" and gap_report:
        total = gap_report.get("total_gaps", 0)
        crit = gap_report.get("critical_count", 0)
        mod = gap_report.get("moderate_count", 0)
        watch = gap_report.get("watch_count", 0)
        evaluations.append(
            AgentResult(3, PASS, _log_duration(log3), f"{total} gaps ({crit} critical, {mod} moderate, {watch} watch)")
        )
    elif status3 in ("skipped",):
        evaluations.append(AgentResult(3, SKIP, 0.0, "Skipped by orchestrator"))
    elif status3 == "completed" and not gap_report:
        evaluations.append(AgentResult(3, FAIL, _log_duration(log3), "Completed but no gap report stored"))
    else:
        err = (log3 or {}).get("error_message") or s3.get("error_message") or "No log found"
        evaluations.append(AgentResult(3, FAIL, _log_duration(log3), err[:80]))

    # ── Agent 4 — Quantity Takeoff ────────────────────────────────────────
    log4 = _agent_log(agent_logs, 4)
    s4 = status_by_agent.get(4, {})
    status4 = (log4 or {}).get("status") or s4.get("status") or ""
    takeoff: list[dict] = results.get("takeoff_items") or []
    if status4 == "skipped":
        evaluations.append(AgentResult(4, SKIP, 0.0, "Skipped — quantities present in WinEst import"))
    elif status4 == "completed" and len(takeoff) > 0:
        zero_qty = [t for t in takeoff if (t.get("quantity") or 0) == 0]
        pct_zero = len(zero_qty) / len(takeoff) * 100
        verdict = WARN if pct_zero > 20 else PASS
        detail = f"{len(takeoff)} items"
        if zero_qty:
            detail += f", {len(zero_qty)} with qty=0 ({pct_zero:.0f}%)"
        evaluations.append(AgentResult(4, verdict, _log_duration(log4), detail))
    elif status4 == "completed" and len(takeoff) == 0:
        evaluations.append(AgentResult(4, FAIL, _log_duration(log4), "Completed but 0 takeoff items stored"))
    else:
        err = (log4 or {}).get("error_message") or s4.get("error_message") or "No log found"
        evaluations.append(AgentResult(4, FAIL, _log_duration(log4), err[:80]))

    # ── Agent 5 — Labor Productivity ─────────────────────────────────────
    log5 = _agent_log(agent_logs, 5)
    s5 = status_by_agent.get(5, {})
    status5 = (log5 or {}).get("status") or s5.get("status") or ""
    labor: list[dict] = results.get("labor_estimates") or []
    if status5 == "completed" and len(labor) > 0:
        zero_rate = [item for item in labor if (item.get("hourly_rate") or 0) == 0]
        verdict = WARN if zero_rate else PASS
        detail = f"{len(labor)} items matched"
        if zero_rate:
            detail += f", {len(zero_rate)} with $0 rate"
        evaluations.append(AgentResult(5, verdict, _log_duration(log5), detail))
    elif status5 in ("skipped",):
        evaluations.append(AgentResult(5, SKIP, 0.0, "Skipped by orchestrator"))
    elif status5 == "completed" and len(labor) == 0:
        evaluations.append(AgentResult(5, FAIL, _log_duration(log5), "Completed but 0 labor estimates stored"))
    else:
        err = (log5 or {}).get("error_message") or s5.get("error_message") or "No log found"
        evaluations.append(AgentResult(5, FAIL, _log_duration(log5), err[:80]))

    # ── Agent 6 — Estimate Assembly ───────────────────────────────────────
    log6 = _agent_log(agent_logs, 6)
    s6 = status_by_agent.get(6, {})
    status6 = (log6 or {}).get("status") or s6.get("status") or ""
    estimate: dict | None = results.get("estimate")
    if status6 == "completed" and estimate and (estimate.get("total_bid_amount") or 0) > 0:
        grand_total = estimate["total_bid_amount"]
        has_summary = bool((estimate.get("executive_summary") or "").strip())
        note = "  (has exec summary)" if has_summary else ""
        evaluations.append(AgentResult(6, PASS, _log_duration(log6), f"Grand total: ${grand_total:,.0f}{note}"))
    elif status6 in ("skipped",):
        evaluations.append(AgentResult(6, SKIP, 0.0, "Skipped by orchestrator"))
    elif status6 == "completed" and estimate and (estimate.get("total_bid_amount") or 0) == 0:
        evaluations.append(AgentResult(6, WARN, _log_duration(log6), "Estimate created but grand total = $0"))
    elif status6 == "completed" and not estimate:
        evaluations.append(AgentResult(6, FAIL, _log_duration(log6), "Completed but no estimate stored"))
    else:
        err = (log6 or {}).get("error_message") or s6.get("error_message") or "No log found"
        evaluations.append(AgentResult(6, FAIL, _log_duration(log6), err[:80]))

    # ── Agent 7 — IMPROVE Feedback ────────────────────────────────────────
    log7 = _agent_log(agent_logs, 7)
    s7 = status_by_agent.get(7, {})
    status7 = (log7 or {}).get("status") or s7.get("status") or ""
    if not log7 or status7 in ("", "pending", "skipped"):
        evaluations.append(AgentResult(7, SKIP, 0.0, "No actuals uploaded"))
    elif status7 == "completed":
        summary7 = (log7 or {}).get("output_summary") or "Improvement feedback applied"
        evaluations.append(AgentResult(7, PASS, _log_duration(log7), summary7[:80]))
    else:
        err = (log7 or {}).get("error_message") or "Agent 7 did not complete"
        evaluations.append(AgentResult(7, FAIL, _log_duration(log7), err[:80]))

    return evaluations


# ---------------------------------------------------------------------------
# Token usage summary
# ---------------------------------------------------------------------------


def summarise_tokens(token_usage: list[dict] | None) -> tuple[float, float]:
    """Return (total_cost, cache_hit_rate_pct)."""
    if not token_usage:
        return 0.0, 0.0

    total_cost = sum(r.get("estimated_cost") or 0.0 for r in token_usage)
    total_input = sum(r.get("input_tokens") or 0 for r in token_usage)
    total_cache_read = sum(r.get("cache_read_tokens") or 0 for r in token_usage)
    total_tokens = total_input + total_cache_read
    cache_hit_rate = (total_cache_read / total_tokens * 100) if total_tokens > 0 else 0.0
    return total_cost, cache_hit_rate


# ---------------------------------------------------------------------------
# Report printing
# ---------------------------------------------------------------------------

BORDER = "═" * 51
DIVIDER = "─" * 51


def print_report(
    file_path: Path,
    mode: str,
    total_duration: float,
    agent_results: list[AgentResult],
    token_cost: float,
    cache_hit_rate: float,
) -> None:
    counts = {PASS: 0, WARN: 0, FAIL: 0, SKIP: 0}
    for r in agent_results:
        counts[r.verdict] += 1

    print(BORDER)
    print("     APEX Pipeline E2E Test Report")
    print(f"     File: {file_path.name} | Mode: {mode}")
    print(f"     Total Duration: {total_duration:.1f}s")
    print(BORDER)
    for r in agent_results:
        print(r.format_line())
    print(DIVIDER)
    print(f"  Token Usage:  ${token_cost:.4f} total | Cache hit: {cache_hit_rate:.0f}%")
    print(f"  Result: {counts[PASS]}/{len(agent_results)} PASS | {counts[WARN]} WARN | {counts[FAIL]} FAIL")
    print(BORDER)


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------


def save_results(
    file_path: Path,
    mode: str,
    total_duration: float,
    project_id: int,
    agent_results: list[AgentResult],
    raw_results: dict[str, Any],
    pipeline_status: dict,
) -> tuple[Path, str]:
    """Save pipeline results to test_specs/results/.

    Returns (output_path, timestamp) so the caller can reuse the timestamp
    for the companion score file.
    """
    out_dir = Path("test_specs/results")
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"{ts}_{project_id}.json"

    payload = {
        "meta": {
            "file": str(file_path),
            "mode": mode,
            "project_id": project_id,
            "total_duration_seconds": round(total_duration, 2),
            "run_at": datetime.now(UTC).isoformat(),
        },
        "summary": {
            a.name: {
                "verdict": a.verdict,
                "duration_seconds": a.duration,
                "detail": a.detail,
            }
            for a in agent_results
        },
        "pipeline_status": pipeline_status,
        "raw": {k: v for k, v in raw_results.items() if not k.endswith("_error")},
    }

    out_path.write_text(json.dumps(payload, indent=2, default=str))
    return out_path, ts


# ---------------------------------------------------------------------------
# Mode detection
# ---------------------------------------------------------------------------


def detect_mode(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    if ext == ".est":
        return "winest_import"
    if ext == ".xlsx":
        # WinEst exports are .xlsx but we default to spec unless overridden
        return "spec"
    return "spec"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="APEX Pipeline E2E Integration Test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("file", help="Path to the spec file to upload and process")
    parser.add_argument(
        "--mode",
        choices=["spec", "winest_import"],
        default=None,
        help="Pipeline mode (default: auto-detect from file extension)",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("APEX_BASE_URL", "http://localhost:8000"),
        help="Backend base URL (default: http://localhost:8000 or $APEX_BASE_URL)",
    )
    parser.add_argument(
        "--email",
        default=os.getenv("APEX_ADMIN_EMAIL", "admin@summitbuilders.com"),
        help="Admin email for authentication",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("APEX_ADMIN_PASSWORD", "admin123"),
        help="Admin password for authentication",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"ERROR: File not found: {file_path}", file=sys.stderr)
        return 1

    mode = args.mode or detect_mode(file_path)
    start_ts = time.monotonic()

    print("\n  Starting APEX E2E test")
    print(f"  File : {file_path}")
    print(f"  Mode : {mode}")
    print(f"  API  : {args.base_url}\n")

    with httpx.Client(
        base_url=args.base_url,
        timeout=60.0,
        follow_redirects=True,
    ) as client:
        # 1. Authenticate
        print("  [1/5] Authenticating…", end=" ", flush=True)
        try:
            token = authenticate(client, args.email, args.password)
        except RuntimeError as exc:
            print(f"FAIL\n  ERROR: {exc}", file=sys.stderr)
            return 1
        client.headers["Authorization"] = f"Bearer {token}"
        print("OK")

        # 2. Create project
        print("  [2/5] Creating test project…", end=" ", flush=True)
        try:
            project_id = create_project(client, file_path.name)
        except RuntimeError as exc:
            print(f"FAIL\n  ERROR: {exc}", file=sys.stderr)
            return 1
        print(f"OK (id={project_id})")

        # 3. Upload file
        file_size = file_path.stat().st_size
        upload_type = "chunked" if file_size > LARGE_FILE_THRESHOLD else "simple"
        print(
            f"  [3/5] Uploading {file_size / 1024:.1f} KB via {upload_type} upload…",
            end=" ",
            flush=True,
        )
        try:
            document_id = upload_file(client, project_id, file_path)
        except RuntimeError as exc:
            print(f"FAIL\n  ERROR: {exc}", file=sys.stderr)
            return 1
        print(f"OK (doc_id={document_id})")

        # 4. Trigger pipeline (chunked upload auto-triggers; single upload needs explicit trigger)
        print("  [4/5] Triggering pipeline…", end=" ", flush=True)
        try:
            if file_size <= LARGE_FILE_THRESHOLD:
                trigger_pipeline(client, project_id, document_id, mode)
            # chunked upload already triggered it — just confirm the mode is applied
            # by calling pipeline/run which is idempotent (starts fresh run)
            else:
                trigger_pipeline(client, project_id, document_id, mode)
        except RuntimeError as exc:
            print(f"FAIL\n  ERROR: {exc}", file=sys.stderr)
            return 1
        print("OK")

        # 5. Poll for completion
        print("  [5/5] Waiting for pipeline to complete…")
        try:
            pipeline_status = poll_pipeline(client, project_id)
        except RuntimeError as exc:
            print(f"  ERROR: {exc}", file=sys.stderr)
            return 1

        total_duration = time.monotonic() - start_ts

        # Collect results
        results = collect_results(client, project_id)

    # Evaluate
    agent_results = evaluate_agents(pipeline_status, results, mode)
    token_cost, cache_hit_rate = summarise_tokens(results.get("token_usage"))

    print()
    print_report(file_path, mode, total_duration, agent_results, token_cost, cache_hit_rate)

    # Save JSON
    out_path, ts = save_results(
        file_path,
        mode,
        total_duration,
        project_id,
        agent_results,
        results,
        pipeline_status,
    )
    print(f"\n  Full results saved to: {out_path}")

    # ── Accuracy scoring ────────────────────────────────────────────────
    from apex.backend.tests.accuracy_scorer import score_pipeline_result

    # Build a flat dict the scorer expects from the collected results
    scorer_input: dict[str, Any] = {}
    # Agent 1 — documents (use agent_logs as proxy for ingestion data)
    if results.get("agent_logs"):
        a1_logs = [lg for lg in results["agent_logs"] if lg.get("agent_number") == 1]
        if a1_logs and a1_logs[0].get("status") == "completed":
            scorer_input["documents"] = [{"source": str(file_path)}]
    # Agent 2
    if results.get("spec_sections") is not None:
        scorer_input["spec_sections"] = results["spec_sections"]
    # Agent 3
    if results.get("gap_report") is not None:
        scorer_input["gap_report"] = results["gap_report"]
    # Agent 4 + 5 — takeoff_items → line_items, merge labor data
    if results.get("takeoff_items") is not None:
        line_items = results["takeoff_items"]
        # Merge labor rates into line items if available
        if results.get("labor_estimates"):
            labor_by_id = {}
            for le in results["labor_estimates"]:
                tid = le.get("takeoff_item_id")
                if tid is not None:
                    labor_by_id[tid] = le
            for item in line_items:
                labor = labor_by_id.get(item.get("id"))
                if labor:
                    item.setdefault("unit_price", labor.get("hourly_rate", 0))
        scorer_input["line_items"] = line_items
    # Agent 6
    est = results.get("estimate")
    if est is not None:
        scorer_input["total_cost"] = est.get("total_bid_amount", 0)
        scorer_input["executive_summary"] = est.get("executive_summary") or ""
    # Agent 7
    # schedule/milestones would be in the estimate or a dedicated endpoint
    if est:
        if est.get("schedule"):
            scorer_input["schedule"] = est["schedule"]
        if est.get("milestones"):
            scorer_input["milestones"] = est["milestones"]

    print("\n  ── Accuracy Scoring ──")
    score_report = score_pipeline_result(scorer_input, verbose=True)

    # Save score report
    score_path = Path("test_specs/results") / f"{ts}_{project_id}_score.json"
    score_path.write_text(json.dumps(score_report, indent=2, default=str))
    print(f"\n  Score report saved to: {score_path}")

    # Final summary
    ps = score_report["pipeline_summary"]
    overall_score = ps["overall_score"]
    passed_agents = ps["passed"]
    total_agents = ps["total_agents"]
    print(f"  ACCURACY: {overall_score:.1%} ({passed_agents}/{total_agents} agents passed)\n")

    # Exit code: gate on 70% accuracy threshold
    if overall_score < 0.70:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
