"""Smoke test for the APEX 6-agent pipeline.

Calls the dev-only POST /api/test/run-pipeline endpoint and asserts that
all pipeline stages produced meaningful output.

Usage:
    # Ensure APEX_DEV_MODE=true and the backend is running on localhost:8000
    python -m pytest apex/backend/tests/test_pipeline.py -v

    # Or run directly:
    python apex/backend/tests/test_pipeline.py
"""

import json
import sys
import urllib.error
import urllib.request

BASE_URL = "http://localhost:8000"
ENDPOINT = f"{BASE_URL}/api/test/run-pipeline"


def run_smoke_test() -> dict:
    req = urllib.request.Request(ENDPOINT, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach {ENDPOINT}. Is the backend running with APEX_DEV_MODE=true?") from exc


def assert_results(result: dict) -> list[str]:
    failures = []
    for a in result.get("assertions", []):
        status = "PASS" if a["passed"] else "FAIL"
        print(f"  [{status}] {a['check']} — {a['detail']}")
        if not a["passed"]:
            failures.append(a["check"])
    return failures


def main():
    print("=" * 60)
    print("APEX Pipeline Smoke Test")
    print("=" * 60)
    print(f"Endpoint: {ENDPOINT}")
    print()

    try:
        result = run_smoke_test()
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    print(f"Project ID  : {result.get('project_id')}")
    print(f"Document ID : {result.get('document_id')}")
    print(f"Pipeline    : {result.get('pipeline_status')}")
    print()
    print("Assertions:")
    failures = assert_results(result)

    print()
    if result.get("all_assertions_passed"):
        print("RESULT: ALL ASSERTIONS PASSED")
        sys.exit(0)
    else:
        print(f"RESULT: {len(failures)} ASSERTION(S) FAILED: {failures}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# pytest integration
# ---------------------------------------------------------------------------

try:
    import pytest

    @pytest.mark.integration
    def test_full_pipeline():
        """Integration smoke test — requires running backend with APEX_DEV_MODE=true."""
        result = run_smoke_test()
        failures = [a["check"] for a in result.get("assertions", []) if not a["passed"]]
        assert result.get("all_assertions_passed"), f"Pipeline assertions failed: {failures}"

except ImportError:
    pass  # pytest not available — only direct execution supported


if __name__ == "__main__":
    main()
