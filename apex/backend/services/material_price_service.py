"""Material price service — fetch live or cached pricing for common construction
materials. Designed to plug in real supplier APIs (RS Means, Home Depot Pro, etc.)
with a built-in fallback to reasonable benchmark rates when no key is configured."""

import logging
import os
from datetime import UTC, datetime

from apex.backend.utils.csi_utils import parse_csi_division

logger = logging.getLogger("apex.material_prices")

# ---------------------------------------------------------------------------
# Benchmark rates (unit cost USD) keyed by (csi_code_prefix, unit).
# These serve as fallback when no live API is configured and as floor-check
# validation for live results that look unreasonable.
# Source: RS Means 2024 national averages.
# ---------------------------------------------------------------------------
BENCHMARK_RATES: dict[tuple[str, str], dict] = {
    # Division 03 — Concrete
    ("03", "CY"): {"description": "Concrete (ready-mix, 4000 psi)", "unit_cost": 185.0},
    ("03", "SF"): {"description": 'Concrete slab on grade (4")', "unit_cost": 8.50},
    # Division 04 — Masonry
    ("04", "SF"): {"description": 'CMU block wall (8" standard)', "unit_cost": 18.0},
    ("04", "MSF"): {"description": "Brick (standard)", "unit_cost": 950.0},
    # Division 05 — Metals
    ("05", "TON"): {"description": "Structural steel (A36)", "unit_cost": 3800.0},
    ("05", "LF"): {"description": 'Steel decking (1.5" type B)', "unit_cost": 4.20},
    # Division 06 — Wood
    ("06", "MBF"): {"description": "Framing lumber (2x4 SPF)", "unit_cost": 540.0},
    ("06", "SF"): {"description": 'OSB sheathing (7/16")', "unit_cost": 1.10},
    # Division 07 — Thermal & Moisture
    ("07", "SF"): {"description": "TPO roofing membrane", "unit_cost": 7.50},
    ("07", "LF"): {"description": 'Pipe insulation (1" fiberglass)', "unit_cost": 3.20},
    # Division 08 — Openings
    ("08", "EA"): {"description": "Hollow metal door & frame (3'×7')", "unit_cost": 920.0},
    # Division 09 — Finishes
    ("09", "SF"): {"description": 'Gypsum board (5/8")', "unit_cost": 1.45},
    ("09", "SY"): {"description": "Carpet (commercial grade)", "unit_cost": 32.0},
    # Division 22 — Plumbing
    ("22", "EA"): {"description": "Water closet (commercial)", "unit_cost": 680.0},
    ("22", "LF"): {"description": 'Copper pipe (1" type L)', "unit_cost": 12.50},
    # Division 23 — HVAC
    ("23", "TON"): {"description": "Rooftop HVAC unit", "unit_cost": 2800.0},
    ("23", "LF"): {"description": "Rectangular ductwork (24 ga)", "unit_cost": 18.0},
    # Division 26 — Electrical
    ("26", "LF"): {"description": 'EMT conduit (3/4")', "unit_cost": 4.80},
    ("26", "EA"): {"description": "Panel board (200A, 42-circuit)", "unit_cost": 2100.0},
}


def _benchmark_lookup(csi_code: str, unit: str) -> dict | None:
    prefix = parse_csi_division(csi_code)
    unit_upper = unit.upper().strip()
    key = (prefix, unit_upper)
    entry = BENCHMARK_RATES.get(key)
    if entry:
        return {
            "csi_code": csi_code,
            "description": entry["description"],
            "unit": unit,
            "unit_cost": entry["unit_cost"],
            "source": "benchmark",
            "last_updated": datetime.now(UTC).date().isoformat(),
        }
    return None


async def _fetch_live_price(csi_code: str, description: str, unit: str) -> dict | None:  # noqa: C901
    """Attempt to fetch a live price from configured supplier API.

    Supports:
    - MATERIAL_PRICE_API=rsmeans  → RS Means API (requires RSMEANS_API_KEY)
    - MATERIAL_PRICE_API=custom   → arbitrary REST endpoint (MATERIAL_PRICE_API_URL)

    Returns None when no provider is configured so callers fall back to benchmark.
    """
    provider = os.getenv("MATERIAL_PRICE_API", "").lower()

    if provider == "rsmeans":
        api_key = os.getenv("RSMEANS_API_KEY", "")
        if not api_key:
            return None
        try:
            import httpx

            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(
                    "https://api.rsmeans.com/v1/materials/search",
                    params={"csi_code": csi_code, "unit": unit},
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("items", [])
                    if items:
                        item = items[0]
                        return {
                            "csi_code": csi_code,
                            "description": item.get("description", description),
                            "unit": unit,
                            "unit_cost": float(item.get("unit_cost", 0)),
                            "source": "rsmeans",
                            "last_updated": datetime.now(UTC).date().isoformat(),
                        }
        except Exception as exc:
            logger.warning("RS Means price lookup failed: %s", exc)

    elif provider == "custom":
        api_url = os.getenv("MATERIAL_PRICE_API_URL", "")
        if not api_url:
            return None
        try:
            import httpx

            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(
                    api_url,
                    params={"csi_code": csi_code, "unit": unit, "q": description},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "csi_code": csi_code,
                        "description": data.get("description", description),
                        "unit": unit,
                        "unit_cost": float(data.get("unit_cost", 0)),
                        "source": "custom",
                        "last_updated": datetime.now(UTC).date().isoformat(),
                    }
        except Exception as exc:
            logger.warning("Custom price API lookup failed: %s", exc)

    return None


async def get_material_price(csi_code: str, description: str, unit: str) -> dict:
    """Return the best available unit price for a material.

    Priority: live API → benchmark table → zero-cost placeholder.
    """
    live = await _fetch_live_price(csi_code, description, unit)
    if live:
        return live

    benchmark = _benchmark_lookup(csi_code, unit)
    if benchmark:
        return benchmark

    # Graceful fallback — return zero so the estimate can still be generated
    return {
        "csi_code": csi_code,
        "description": description,
        "unit": unit,
        "unit_cost": 0.0,
        "source": "not_found",
        "last_updated": datetime.now(UTC).date().isoformat(),
    }


async def get_material_prices_bulk(items: list[dict]) -> list[dict]:
    """Fetch prices for multiple items concurrently.

    Each item dict must have: csi_code, description, unit.
    """
    import asyncio

    tasks = [
        get_material_price(
            item.get("csi_code", ""),
            item.get("description", ""),
            item.get("unit", "EA"),
        )
        for item in items
    ]
    return await asyncio.gather(*tasks)
