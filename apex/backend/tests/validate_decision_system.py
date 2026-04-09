"""Validation script — tests all decision system endpoints end-to-end.

Usage:
  python apex/backend/tests/validate_decision_system.py
  python apex/backend/tests/validate_decision_system.py https://web-production-f87116.up.railway.app

Exits 0 if all checks pass, 1 if any fail.
"""

import json
import sys

try:
    import httpx
except ImportError:
    print("[ERROR] httpx not installed. Run: pip install httpx")
    sys.exit(1)

BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8000"
TIMEOUT = 30

_QUANTITIES = [
    {"description": "Continuous Footing Forms", "quantity": 2400, "unit": "SF", "division_code": "03 30 00"},
    {"description": "Place Continuous Footing Concrete - 43 meter Boom", "quantity": 120, "unit": "CY", "division_code": "03 30 00"},
    {"description": "Fine Grade Slab on Grade by Hand", "quantity": 15000, "unit": "SF", "division_code": "03 30 00"},
    {"description": "Sawcut Joints - 1-1/2 Depth", "quantity": 800, "unit": "LF", "division_code": "03 35 00"},
    {"description": "Concrete Slab Edge Forms 2x8", "quantity": 600, "unit": "LF", "division_code": "03 30 00"},
    {"description": "Expansion Joint Material - SOG", "quantity": 400, "unit": "LF", "division_code": "03 30 00"},
]

results = []
_project_id = None
_line_id = None


def _pass(name, detail=""):
    results.append(("PASS", name, detail))
    print(f"  [PASS] {name}" + (f" — {detail}" if detail else ""))


def _fail(name, detail=""):
    results.append(("FAIL", name, detail))
    print(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))


def check(num, name, fn):
    print(f"\nCheck {num}: {name}")
    try:
        fn()
    except Exception as e:
        _fail(name, str(e))


# ---------------------------------------------------------------------------
# 1. Health check
# ---------------------------------------------------------------------------
def check_1():
    r = httpx.get(f"{BASE_URL}/api/decision/health", timeout=TIMEOUT)
    r.raise_for_status()
    d = r.json()
    assert d.get("comparable_projects", 0) > 0, f"comparable_projects={d.get('comparable_projects')}"
    assert d.get("rate_observations", 0) > 0, f"rate_observations={d.get('rate_observations')}"
    _pass("Decision health", f"projects={d['comparable_projects']}, obs={d['rate_observations']}, activities={d.get('canonical_activities',0)}")


# ---------------------------------------------------------------------------
# 2. Create test project + set context
# ---------------------------------------------------------------------------
def check_2():
    global _project_id

    # Create project
    r = httpx.post(
        f"{BASE_URL}/api/projects",
        json={
            "name": "Decision System Validation Test",
            "project_type": "industrial",
            "status": "draft",
            "location": "Michigan",
        },
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    proj = r.json()
    _project_id = proj.get("id") or proj.get("project", {}).get("id")
    assert _project_id, f"No project id in response: {proj}"

    # Set context
    r2 = httpx.patch(
        f"{BASE_URL}/api/decision/projects/{_project_id}/context",
        json={
            "project_type": "industrial",
            "market_sector": "energy",
            "region": "michigan",
            "delivery_method": "cmar",
            "contract_type": "self_perform",
        },
        timeout=TIMEOUT,
    )
    r2.raise_for_status()
    ctx = r2.json()
    assert ctx.get("project_type") == "industrial"
    _pass("Create project + set context", f"project_id={_project_id}")


# ---------------------------------------------------------------------------
# 3. Comparable projects
# ---------------------------------------------------------------------------
def check_3():
    assert _project_id, "No project_id from check 2"
    r = httpx.get(
        f"{BASE_URL}/api/decision/projects/{_project_id}/comparable-projects",
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    comps = r.json()
    assert len(comps) > 0, "No comparable projects returned"
    assert comps[0].get("context_similarity", 0) > 0, f"First comparable has zero similarity: {comps[0]}"
    _pass("Comparable projects", f"count={len(comps)}, top_similarity={comps[0]['context_similarity']}")


# ---------------------------------------------------------------------------
# 4. Benchmark activity
# ---------------------------------------------------------------------------
def check_4():
    assert _project_id, "No project_id from check 2"
    activity = "Continuous Footing Forms"
    r = httpx.get(
        f"{BASE_URL}/api/decision/projects/{_project_id}/benchmarks/{activity}",
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    bm = r.json()
    assert bm.get("sample_size", 0) > 0, f"sample_size=0 for '{activity}'"
    _pass("Benchmark activity", f"sample_size={bm['sample_size']}, p50={bm.get('p50')}, confidence={bm.get('confidence_label')}")


# ---------------------------------------------------------------------------
# 5. Run estimate
# ---------------------------------------------------------------------------
def check_5():
    assert _project_id, "No project_id from check 2"
    r = httpx.post(
        f"{BASE_URL}/api/decision/projects/{_project_id}/estimate",
        json={"quantities": _QUANTITIES},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    est = r.json()
    assert est.get("line_count", 0) >= 5, f"line_count={est.get('line_count')}"
    assert est.get("direct_cost", 0) > 0, f"direct_cost={est.get('direct_cost')}"
    _pass("Run estimate", f"lines={est['line_count']}, direct_cost=${est['direct_cost']:,.2f}")


# ---------------------------------------------------------------------------
# 6. Estimate lines — unique unit costs
# ---------------------------------------------------------------------------
def check_6():
    global _line_id
    assert _project_id, "No project_id from check 2"
    r = httpx.get(
        f"{BASE_URL}/api/decision/projects/{_project_id}/estimate-lines",
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    lines = r.json()
    unit_costs = set(
        ln["recommended_unit_cost"]
        for ln in lines
        if ln.get("recommended_unit_cost") is not None
    )
    assert len(unit_costs) >= 3, f"Only {len(unit_costs)} unique unit costs (need >=3 for activity-specific matching)"
    if lines:
        _line_id = lines[0]["id"]
    _pass("Estimate lines unique costs", f"unique_unit_costs={len(unit_costs)}, line_id={_line_id}")


# ---------------------------------------------------------------------------
# 7. Cost breakdown
# ---------------------------------------------------------------------------
def check_7():
    assert _project_id, "No project_id from check 2"
    r = httpx.get(
        f"{BASE_URL}/api/decision/projects/{_project_id}/cost-breakdown",
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    cb = r.json()
    assert cb.get("direct_cost", 0) > 0, f"direct_cost={cb.get('direct_cost')}"
    assert cb.get("final_bid", 0) > cb.get("direct_cost", 0), \
        f"final_bid={cb.get('final_bid')} should exceed direct_cost={cb.get('direct_cost')}"
    _pass("Cost breakdown", f"direct=${cb['direct_cost']:,.2f}, final_bid=${cb['final_bid']:,.2f}")


# ---------------------------------------------------------------------------
# 8. Risk items
# ---------------------------------------------------------------------------
def check_8():
    assert _project_id, "No project_id from check 2"
    r = httpx.get(
        f"{BASE_URL}/api/decision/projects/{_project_id}/risk-items",
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    risks = r.json()
    assert len(risks) >= 3, f"Only {len(risks)} risk items (need >=3)"
    _pass("Risk items", f"count={len(risks)}")


# ---------------------------------------------------------------------------
# 9. Override estimate line
# ---------------------------------------------------------------------------
def check_9():
    assert _line_id, "No line_id from check 6"
    r = httpx.post(
        f"{BASE_URL}/api/decision/estimate-lines/{_line_id}/override",
        json={
            "overridden_value": 99.99,
            "override_type": "manual",
            "reason_code": "validation_test",
            "reason_text": "Validation script override test",
            "created_by": "validator",
        },
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    updated = r.json()
    assert abs(updated.get("recommended_unit_cost", 0) - 99.99) < 0.01, \
        f"Override not applied: unit_cost={updated.get('recommended_unit_cost')}"
    assert updated.get("pricing_basis") == "estimator_override"
    assert updated.get("needs_review") is False
    _pass("Override estimate line", f"unit_cost={updated['recommended_unit_cost']}, basis={updated['pricing_basis']}")


# ---------------------------------------------------------------------------
# 10. Cleanup
# ---------------------------------------------------------------------------
def check_10():
    assert _project_id, "No project_id from check 2"
    # Attempt delete (may not exist on all deployments)
    try:
        r = httpx.delete(f"{BASE_URL}/api/projects/{_project_id}", timeout=TIMEOUT)
        if r.status_code in (200, 204, 404):
            _pass("Cleanup", f"Deleted project {_project_id}")
        else:
            _pass("Cleanup", f"Project {_project_id} — delete returned {r.status_code} (manual cleanup may be needed)")
    except Exception:
        _pass("Cleanup", f"Note test project_id={_project_id} — manual cleanup may be needed")


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
print(f"\n=== APEX Decision System Validation ===")
print(f"Target: {BASE_URL}\n")

check(1, "Decision health",         check_1)
check(2, "Create project + context", check_2)
check(3, "Comparable projects",      check_3)
check(4, "Benchmark activity",       check_4)
check(5, "Run estimate",             check_5)
check(6, "Estimate lines",           check_6)
check(7, "Cost breakdown",           check_7)
check(8, "Risk items",               check_8)
check(9, "Override line",            check_9)
check(10, "Cleanup",                 check_10)

passed = sum(1 for r in results if r[0] == "PASS")
failed = sum(1 for r in results if r[0] == "FAIL")

print(f"\n=== Summary: {passed}/{len(results)} passed ===")
if failed:
    print(f"FAILURES:")
    for status, name, detail in results:
        if status == "FAIL":
            print(f"  - {name}: {detail}")

sys.exit(0 if failed == 0 else 1)
