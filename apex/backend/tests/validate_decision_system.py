"""End-to-end validation script for the APEX decision system API.

Usage:
    python apex/backend/tests/validate_decision_system.py                       # local
    python apex/backend/tests/validate_decision_system.py https://host.railway.app
"""

import json
import sys
import httpx

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8000"
TIMEOUT = 30

# Auth header — Railway deployments may require it; local typically does not.
# Set APEX_TOKEN env var if needed.
import os
_TOKEN = os.environ.get("APEX_TOKEN", "")
HEADERS = {"Authorization": f"Bearer {_TOKEN}"} if _TOKEN else {}

# ---------------------------------------------------------------------------
# Terminal colors
# ---------------------------------------------------------------------------
_tty = sys.stdout.isatty()
GREEN  = "\033[32m" if _tty else ""
RED    = "\033[31m" if _tty else ""
YELLOW = "\033[33m" if _tty else ""
CYAN   = "\033[36m" if _tty else ""
RESET  = "\033[0m"  if _tty else ""
BOLD   = "\033[1m"  if _tty else ""

results: list[tuple[str, bool, str]] = []


def _pass(check: str, detail: str) -> None:
    results.append((check, True, detail))
    print(f"  {GREEN}✅ {check}{RESET}  {CYAN}{detail}{RESET}")


def _fail(check: str, detail: str) -> None:
    results.append((check, False, detail))
    print(f"  {RED}❌ {check}{RESET}  {detail}")


def _info(msg: str) -> None:
    print(f"     {YELLOW}{msg}{RESET}")


def _get(path: str, **kwargs) -> httpx.Response:
    return httpx.get(f"{BASE_URL}{path}", headers=HEADERS, timeout=TIMEOUT, **kwargs)


def _post(path: str, json_body=None, **kwargs) -> httpx.Response:
    return httpx.post(
        f"{BASE_URL}{path}", json=json_body, headers=HEADERS, timeout=TIMEOUT, **kwargs
    )


def _patch(path: str, json_body=None) -> httpx.Response:
    return httpx.patch(
        f"{BASE_URL}{path}", json=json_body, headers=HEADERS, timeout=TIMEOUT
    )


def _delete(path: str) -> httpx.Response:
    return httpx.delete(f"{BASE_URL}{path}", headers=HEADERS, timeout=TIMEOUT)


# ---------------------------------------------------------------------------
# Validation checks
# ---------------------------------------------------------------------------

project_id: int | None = None
first_line_id: str | None = None


def check_1_health() -> bool:
    try:
        r = _get("/api/decision/health")
        if r.status_code != 200:
            _fail("CHECK 1: Decision Health", f"HTTP {r.status_code}")
            return False
        data = r.json()
        cp = data.get("comparable_projects", 0)
        ro = data.get("rate_observations", 0)
        ca = data.get("canonical_activities", 0)
        if cp == 0 or ro == 0 or ca == 0:
            _fail("CHECK 1: Decision Health", f"Empty data: {cp} projects, {ro} obs, {ca} activities")
            return False
        _pass("CHECK 1: Decision Health", f"{cp} comparable projects · {ro} observations · {ca} canonical activities")
        return True
    except Exception as e:
        _fail("CHECK 1: Decision Health", str(e))
        return False


def check_2_create_project() -> bool:
    global project_id
    try:
        # Try creating without auth first; fall back to skip if auth is required
        r = _post("/api/projects", {
            "name": "Validation Test Project",
            "project_number": f"VAL-{os.urandom(3).hex().upper()}",
            "project_type": "industrial",
        })
        if r.status_code not in (200, 201):
            _fail("CHECK 2: Create Project", f"HTTP {r.status_code}: {r.text[:200]}")
            return False
        data = r.json()
        # Handle both {project: {id}} and {id} response shapes
        project_id = (data.get("project") or data).get("id")
        if not project_id:
            _fail("CHECK 2: Create Project", f"No project id in response: {json.dumps(data)[:200]}")
            return False

        # Patch context
        r2 = _patch(f"/api/projects/{project_id}/context", {
            "project_type": "industrial",
            "market_sector": "energy",
            "region": "michigan",
            "delivery_method": "cmar",
            "contract_type": "self_perform",
            "complexity_level": "medium",
        })
        if r2.status_code not in (200, 201):
            _fail("CHECK 2: Create Project", f"Context PATCH HTTP {r2.status_code}: {r2.text[:200]}")
            return False
        _pass("CHECK 2: Project + Context", f"project_id={project_id}")
        return True
    except Exception as e:
        _fail("CHECK 2: Create Project", str(e))
        return False


def check_3_comparable_projects() -> bool:
    try:
        r = _get(f"/api/projects/{project_id}/comparable-projects")
        if r.status_code != 200:
            _fail("CHECK 3: Comparable Projects", f"HTTP {r.status_code}")
            return False
        data = r.json()
        if not data:
            _fail("CHECK 3: Comparable Projects", "Empty list returned")
            return False
        top = data[0]
        if top.get("context_similarity", 0) <= 0:
            _fail("CHECK 3: Comparable Projects", "Top similarity is 0 — context scoring broken")
            return False
        _pass("CHECK 3: Comparable Projects", f"{len(data)} scored, top similarity: {top['context_similarity']:.3f}")
        for item in data[:3]:
            _info(f"  {item['name']}  sim={item['context_similarity']:.3f}  obs={item['observation_count']}")
        return True
    except Exception as e:
        _fail("CHECK 3: Comparable Projects", str(e))
        return False


def check_4_single_benchmark() -> bool:
    try:
        activity = "Continuous Footing Forms"
        r = _get(
            f"/api/projects/{project_id}/benchmarks/{activity}",
            params={"division_code": "03 30 00"},
        )
        if r.status_code != 200:
            _fail("CHECK 4: Single Benchmark", f"HTTP {r.status_code}")
            return False
        data = r.json()
        ss = data.get("sample_size", 0)
        p50 = data.get("p50")
        conf = data.get("confidence_label", "very_low")
        if ss == 0 or p50 is None:
            _fail("CHECK 4: Single Benchmark", f"No observations found (sample_size={ss})")
            return False
        if conf == "very_low":
            _info(f"  ⚠ Confidence is very_low (sample_size={ss}) — more data needed")
        _pass("CHECK 4: Single Benchmark", f"sample_size={ss} · p50=${p50:.2f} · confidence={conf}")
        return True
    except Exception as e:
        _fail("CHECK 4: Single Benchmark", str(e))
        return False


def check_5_full_estimate() -> bool:
    try:
        quantities = [
            {"description": "Continuous Footing Forms", "quantity": 2400, "unit": "SF", "division_code": "03 30 00"},
            {"description": "Place Continuous Footing Concrete - 43 meter Boom", "quantity": 120, "unit": "CY", "division_code": "03 30 00"},
            {"description": "Fine Grade Slab on Grade by Hand", "quantity": 15000, "unit": "SF", "division_code": "03 30 00"},
            {"description": "Sawcut Joints - 1-1/2 Depth", "quantity": 800, "unit": "LF", "division_code": "03 35 00"},
            {"description": "Concrete Slab Edge Forms 2x8", "quantity": 600, "unit": "LF", "division_code": "03 30 00"},
            {"description": "Expansion Joint Material - SOG", "quantity": 400, "unit": "LF", "division_code": "03 30 00"},
        ]
        r = _post(f"/api/projects/{project_id}/estimate", {"quantities": quantities})
        if r.status_code not in (200, 201):
            _fail("CHECK 5: Full Estimate", f"HTTP {r.status_code}: {r.text[:300]}")
            return False
        data = r.json()
        lc = data.get("line_count", 0)
        dc = data.get("direct_cost", 0)
        fb = data.get("final_bid_value", 0)
        if lc < 5:
            _fail("CHECK 5: Full Estimate", f"Expected >= 5 lines, got {lc}")
            return False
        if dc <= 0:
            _fail("CHECK 5: Full Estimate", f"direct_cost={dc} — no lines were priced")
            return False
        if fb <= dc:
            _fail("CHECK 5: Full Estimate", f"final_bid ({fb}) <= direct_cost ({dc}) — commercial structure broken")
            return False
        _pass("CHECK 5: Full Estimate", f"lines={lc} · direct=${dc:,.2f} · final_bid=${fb:,.2f}")
        return True
    except Exception as e:
        _fail("CHECK 5: Full Estimate", str(e))
        return False


def check_6_line_differentiation() -> bool:
    global first_line_id
    try:
        r = _get(f"/api/projects/{project_id}/estimate-lines")
        if r.status_code != 200:
            _fail("CHECK 6: Line Differentiation", f"HTTP {r.status_code}")
            return False
        lines = r.json()
        costs = [l["recommended_unit_cost"] for l in lines if l.get("recommended_unit_cost") is not None]
        unique = set(round(c, 4) for c in costs)
        if lines:
            first_line_id = lines[0]["id"]
        _info("  Line breakdown:")
        for l in lines:
            uc = l.get("recommended_unit_cost")
            _info(f"    {l['description'][:45]:<45} ${uc:>9.2f}/unit  [{l['confidence_level']}]" if uc else
                  f"    {l['description'][:45]:<45} {'NO DATA':>12}  [{l['confidence_level']}]")
        if len(unique) < 3:
            _fail("CHECK 6: Line Differentiation", f"Only {len(unique)} unique unit costs — benchmark matching too flat")
            return False
        _pass("CHECK 6: Line Differentiation", f"{len(unique)} distinct unit costs across {len(lines)} lines")
        return True
    except Exception as e:
        _fail("CHECK 6: Line Differentiation", str(e))
        return False


def check_7_cost_breakdown() -> bool:
    try:
        r = _get(f"/api/projects/{project_id}/cost-breakdown")
        if r.status_code != 200:
            _fail("CHECK 7: Cost Breakdown", f"HTTP {r.status_code}")
            return False
        data = r.json()
        dc = data.get("direct_cost", 0)
        gc = data.get("general_conditions", 0)
        fee = data.get("fee", 0)
        fb = data.get("final_bid", 0)
        if dc <= 0 or gc <= 0 or fee <= 0 or fb <= dc:
            _fail("CHECK 7: Cost Breakdown", f"dc={dc} gc={gc} fee={fee} fb={fb}")
            return False
        _pass("CHECK 7: Cost Breakdown", f"direct=${dc:,.0f} → final_bid=${fb:,.0f}")
        for b in data.get("buckets", []):
            _info(f"    {b['bucket_type']:<25} ${b['amount']:>12,.2f}")
        return True
    except Exception as e:
        _fail("CHECK 7: Cost Breakdown", str(e))
        return False


def check_8_risk_items() -> bool:
    try:
        r = _get(f"/api/projects/{project_id}/risk-items")
        if r.status_code != 200:
            _fail("CHECK 8: Risk Items", f"HTTP {r.status_code}")
            return False
        items = r.json()
        if len(items) < 3:
            _fail("CHECK 8: Risk Items", f"Expected >= 3 items, got {len(items)}")
            return False
        zero_ev = [i for i in items if (i.get("expected_value") or 0) <= 0]
        if zero_ev:
            _fail("CHECK 8: Risk Items", f"{len(zero_ev)} items have expected_value=0")
            return False
        total_ev = sum(i.get("expected_value", 0) for i in items)
        _pass("CHECK 8: Risk Items", f"{len(items)} items · total EV=${total_ev:,.0f}")
        for i in items:
            _info(f"    [{i['severity']:<8}] {i['name']:<40} P={i['probability']:.0%}  EV=${i['expected_value']:>10,.0f}")
        return True
    except Exception as e:
        _fail("CHECK 8: Risk Items", str(e))
        return False


def check_9_override() -> bool:
    if not first_line_id:
        _fail("CHECK 9: Override", "No line ID available (CHECK 6 must pass first)")
        return False
    try:
        r = _post(f"/api/estimate-lines/{first_line_id}/override", {
            "overridden_value": 99.99,
            "override_type": "unit_cost",
            "reason_code": "local_knowledge",
            "reason_text": "Validation test",
        })
        if r.status_code not in (200, 201):
            _fail("CHECK 9: Override", f"HTTP {r.status_code}: {r.text[:200]}")
            return False
        ov = r.json()
        if ov.get("overridden_value") != 99.99:
            _fail("CHECK 9: Override", f"overridden_value={ov.get('overridden_value')} expected 99.99")
            return False
        orig = ov.get("original_value")

        # Verify the line reflects the override
        r2 = _get(f"/api/projects/{project_id}/estimate-lines")
        lines = r2.json() if r2.status_code == 200 else []
        target = next((l for l in lines if l["id"] == first_line_id), None)
        if not target:
            _fail("CHECK 9: Override", "Could not find line after override")
            return False
        if abs((target.get("recommended_unit_cost") or 0) - 99.99) > 0.01:
            _fail("CHECK 9: Override", f"Line unit_cost={target.get('recommended_unit_cost')} expected 99.99")
            return False
        if target.get("pricing_basis") != "estimator_override":
            _fail("CHECK 9: Override", f"pricing_basis={target.get('pricing_basis')} expected 'estimator_override'")
            return False
        _pass("CHECK 9: Override", f"${orig:.2f} → $99.99 · basis=estimator_override")
        return True
    except Exception as e:
        _fail("CHECK 9: Override", str(e))
        return False


def check_10_cleanup() -> bool:
    if not project_id:
        _pass("CHECK 10: Cleanup", "No project created — nothing to clean up")
        return True
    try:
        r = _delete(f"/api/projects/{project_id}")
        if r.status_code in (200, 204, 404):
            _pass("CHECK 10: Cleanup", f"Test project {project_id} deleted")
        else:
            _info(f"  Could not delete project {project_id} (HTTP {r.status_code}) — manual cleanup needed")
            _pass("CHECK 10: Cleanup", f"Non-critical: project {project_id} left in DB for inspection")
        return True
    except Exception as e:
        _info(f"  Cleanup error (non-critical): {e}")
        _pass("CHECK 10: Cleanup", "Non-critical cleanup issue")
        return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print(f"\n{BOLD}APEX Decision System Validation{RESET}")
    print(f"{CYAN}Target: {BASE_URL}{RESET}\n")

    checks = [
        check_1_health,
        check_2_create_project,
        check_3_comparable_projects,
        check_4_single_benchmark,
        check_5_full_estimate,
        check_6_line_differentiation,
        check_7_cost_breakdown,
        check_8_risk_items,
        check_9_override,
        check_10_cleanup,
    ]

    all_passed = True
    for fn in checks:
        passed = fn()
        if not passed:
            all_passed = False
        print()

    # Summary
    print(f"{BOLD}{'─'*60}{RESET}")
    print(f"{BOLD}SUMMARY{RESET}")
    for name, ok, detail in results:
        icon = f"{GREEN}✅{RESET}" if ok else f"{RED}❌{RESET}"
        print(f"  {icon}  {name}")
    print()
    total = len(results)
    passed_count = sum(1 for _, ok, _ in results if ok)
    if all_passed:
        print(f"{GREEN}{BOLD}All {total} checks passed.{RESET}\n")
    else:
        failed = total - passed_count
        print(f"{RED}{BOLD}{failed}/{total} checks FAILED.{RESET}\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
