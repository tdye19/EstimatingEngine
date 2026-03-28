"""Line item normalization service for WinEst parser output.

Converts raw WinEst parser dicts into clean, standardized dicts suitable for
insertion as HistoricalLineItem records.  All logic is deterministic — no LLM calls.
"""

import logging
import re
from typing import Optional

from apex.backend.models.estimate_library import EstimateLibraryEntry
from apex.backend.utils.csi_utils import CSI_DIVISION_NAMES, parse_csi_division

logger = logging.getLogger("apex.line_item_normalizer")


# ---------------------------------------------------------------------------
# CSI division labor/material/equipment split defaults
# ---------------------------------------------------------------------------

CSI_DIVISION_DEFAULTS: dict[int, dict[str, float]] = {
    # Div  labor   material  equipment
    1:  {"labor": 0.60, "material": 0.35, "equipment": 0.05},
    2:  {"labor": 0.40, "material": 0.45, "equipment": 0.15},
    3:  {"labor": 0.45, "material": 0.40, "equipment": 0.15},  # Concrete
    4:  {"labor": 0.50, "material": 0.45, "equipment": 0.05},  # Masonry
    5:  {"labor": 0.35, "material": 0.55, "equipment": 0.10},  # Metals
    6:  {"labor": 0.50, "material": 0.45, "equipment": 0.05},  # Wood
    7:  {"labor": 0.45, "material": 0.50, "equipment": 0.05},  # Thermal & Moisture
    8:  {"labor": 0.40, "material": 0.55, "equipment": 0.05},  # Openings
    9:  {"labor": 0.55, "material": 0.40, "equipment": 0.05},  # Finishes
    10: {"labor": 0.35, "material": 0.60, "equipment": 0.05},  # Specialties
    11: {"labor": 0.30, "material": 0.65, "equipment": 0.05},  # Equipment
    12: {"labor": 0.35, "material": 0.60, "equipment": 0.05},  # Furnishings
    13: {"labor": 0.40, "material": 0.50, "equipment": 0.10},  # Special Construction
    14: {"labor": 0.35, "material": 0.55, "equipment": 0.10},  # Conveying Equipment
    15: {"labor": 0.50, "material": 0.45, "equipment": 0.05},  # (legacy Mechanical)
    16: {"labor": 0.50, "material": 0.45, "equipment": 0.05},  # (legacy Electrical)
    21: {"labor": 0.45, "material": 0.50, "equipment": 0.05},  # Fire Suppression
    22: {"labor": 0.50, "material": 0.45, "equipment": 0.05},  # Plumbing
    23: {"labor": 0.50, "material": 0.45, "equipment": 0.05},  # HVAC
    26: {"labor": 0.50, "material": 0.45, "equipment": 0.05},  # Electrical
    27: {"labor": 0.45, "material": 0.50, "equipment": 0.05},  # Communications
    28: {"labor": 0.45, "material": 0.50, "equipment": 0.05},  # Electronic Safety
    31: {"labor": 0.40, "material": 0.25, "equipment": 0.35},  # Earthwork
    32: {"labor": 0.40, "material": 0.45, "equipment": 0.15},  # Exterior Improvements
    33: {"labor": 0.40, "material": 0.45, "equipment": 0.15},  # Utilities
}

_DEFAULT_SPLIT = {"labor": 0.50, "material": 0.45, "equipment": 0.05}


# ---------------------------------------------------------------------------
# Unit normalization map
# Each key is a lowercase normalized form of possible raw values
# ---------------------------------------------------------------------------

_UNIT_CANONICAL: dict[str, str] = {
    # SF
    "sq ft": "SF", "sqft": "SF", "sf": "SF", "s.f.": "SF",
    "square foot": "SF", "square feet": "SF",
    # LF
    "lin ft": "LF", "lnft": "LF", "lf": "LF", "l.f.": "LF",
    "linear foot": "LF", "linear feet": "LF", "linft": "LF",
    # CY
    "cubic yd": "CY", "cuyd": "CY", "cy": "CY", "c.y.": "CY",
    "cubic yard": "CY", "cubic yards": "CY",
    # EA
    "each": "EA", "ea": "EA", "ea.": "EA",
    # LS
    "lump sum": "LS", "ls": "LS", "l.s.": "LS",
    # HR
    "hours": "HR", "hrs": "HR", "hr": "HR", "h.r.": "HR", "hour": "HR",
    # TON
    "ton": "TON", "tons": "TON",
    # GAL
    "gallon": "GAL", "gallons": "GAL", "gal": "GAL", "g.a.l.": "GAL",
}


# ---------------------------------------------------------------------------
# CSI keyword → two-digit division string
# ---------------------------------------------------------------------------

_CSI_KEYWORD_MAP: dict[str, str] = {
    # Division 03 — Concrete
    "concrete": "03", "rebar": "03", "formwork": "03", "reinforc": "03",
    "grout": "03", "precast": "03",
    # Division 04 — Masonry
    "masonry": "04", "brick": "04", "block": "04", "mortar": "04", "cmu": "04",
    # Division 05 — Metals
    "steel": "05", "metal": "05", "structural": "05", "joist": "05",
    "decking": "05", "railing": "05", "stair": "05",
    # Division 06 — Wood
    "lumber": "06", "framing": "06", "plywood": "06", "carpent": "06",
    "millwork": "06", "casework": "06",
    # Division 07 — Thermal & Moisture
    "roofing": "07", "waterproof": "07", "insulation": "07",
    "flashing": "07", "sealant": "07", "firestop": "07", "membrane": "07",
    "vapor": "07", "air barrier": "07",
    # Division 08 — Openings
    "door": "08", "window": "08", "glazing": "08", "storefront": "08",
    "hardware": "08", "curtain wall": "08", "entrance": "08",
    # Division 09 — Finishes
    "drywall": "09", "gypsum": "09", "paint": "09", "floor": "09",
    "carpet": "09", "tile": "09", "ceiling": "09", "plaster": "09",
    "coating": "09", "finish": "09",
    # Division 10 — Specialties
    "signage": "10", "toilet": "10", "partition": "10", "locker": "10",
    "fire extinguisher": "10",
    # Division 11 — Equipment
    "equipment": "11",
    # Division 12 — Furnishings
    "furniture": "12", "furnishing": "12", "blind": "12",
    # Division 13 — Special Construction
    "modular": "13", "pre-engineered": "13",
    # Division 14 — Conveying
    "elevator": "14", "escalator": "14", "lift": "14",
    # Division 21 — Fire Suppression
    "sprinkler": "21", "fire suppression": "21", "fire protection": "21",
    # Division 22 — Plumbing
    "plumbing": "22", "pipe": "22", "drain": "22", "fixture": "22",
    "sanitary": "22",
    # Division 23 — HVAC
    "hvac": "23", "mechanical": "23", "duct": "23", "ventilat": "23",
    "air handl": "23", "chiller": "23", "boiler": "23",
    # Division 26 — Electrical
    "electrical": "26", "wiring": "26", "conduit": "26", "panel": "26",
    "lighting": "26", "switchboard": "26",
    # Division 27 — Communications
    "data": "27", "telecom": "27", "communicat": "27", "low voltage": "27",
    # Division 28 — Electronic Safety
    "security": "28", "access control": "28", "camera": "28", "cctv": "28",
    "fire alarm": "28",
    # Division 31 — Earthwork
    "earthwork": "31", "grading": "31", "excavat": "31", "backfill": "31",
    "demo": "31", "demolition": "31",
    # Division 32 — Exterior Improvements
    "paving": "32", "landscap": "32", "sidewalk": "32", "asphalt": "32",
    "curb": "32",
    # Division 33 — Utilities
    "utilities": "33", "sewer": "33", "water main": "33", "storm": "33",
}


# ---------------------------------------------------------------------------
# LineItemNormalizer
# ---------------------------------------------------------------------------


class LineItemNormalizer:
    """Normalize raw WinEst parser output into HistoricalLineItem-ready dicts."""

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def normalize_winest_items(
        self,
        raw_items: list[dict],
        library_entry: Optional[EstimateLibraryEntry],
    ) -> list[dict]:
        """Normalize a list of raw WinEst parser line items.

        For each item:
          1. Attempt CSI code mapping (exact → keyword → fuzzy)
          2. Normalize unit of measure
          3. Estimate labor/material/equipment split if missing
          4. Calculate productivity rate when possible
          5. Denormalize project metadata from *library_entry*

        Returns a list of dicts suitable for **HistoricalLineItem** insertion.
        """
        # Pull denormalized fields from the parent library entry once
        proj_type     = getattr(library_entry, "project_type",   None) if library_entry else None
        building_type = getattr(library_entry, "building_type",  None) if library_entry else None
        loc_state     = getattr(library_entry, "location_state", None) if library_entry else None
        bid_date      = getattr(library_entry, "bid_date",       None) if library_entry else None
        bid_result    = getattr(library_entry, "bid_result",     None) if library_entry else None

        normalized: list[dict] = []

        for raw in raw_items:
            desc = (raw.get("description") or "").strip()
            if not desc:
                continue

            # ------ CSI mapping --------------------------------------------------
            csi_code, csi_division = self._resolve_csi(raw, desc)

            # ------ Unit normalization -------------------------------------------
            raw_unit = raw.get("unit") or raw.get("uom") or ""
            unit = self.normalize_unit(raw_unit)

            # ------ Cost fields --------------------------------------------------
            quantity      = raw.get("quantity")
            labor_hours   = raw.get("labor_hours")
            labor_rate    = raw.get("labor_rate")
            material_cost = raw.get("material_cost")
            total_cost    = raw.get("total") or 0.0

            # Compute labor cost from hours × rate when available
            labor_cost: Optional[float] = None
            if labor_hours is not None and labor_rate is not None:
                labor_cost = round(labor_hours * labor_rate, 2)

            # Estimate split when total is known but breakdown is missing
            equipment_cost: Optional[float] = None
            if total_cost and (labor_cost is None or material_cost is None):
                split = self.estimate_cost_split(float(total_cost), csi_division)
                if labor_cost is None:
                    labor_cost = split["labor"]
                if material_cost is None:
                    material_cost = split["material"]
                equipment_cost = split["equipment"]

            # ------ Unit cost ----------------------------------------------------
            unit_cost: Optional[float] = None
            if total_cost and quantity and quantity > 0:
                unit_cost = round(float(total_cost) / float(quantity), 4)

            # ------ Productivity -------------------------------------------------
            productivity_rate: Optional[float] = None
            productivity_unit: Optional[str] = None
            if labor_hours is not None and quantity is not None and quantity > 0:
                productivity_rate, productivity_unit = self.calculate_productivity(
                    float(quantity), float(labor_hours), unit
                )

            # ------ CSI division name --------------------------------------------
            csi_div_key  = f"{csi_division:02d}" if csi_division is not None else None
            csi_div_name = CSI_DIVISION_NAMES.get(csi_div_key) if csi_div_key else None

            normalized.append({
                # Provenance
                "source_type": "winest",
                # CSI
                "csi_code":          csi_code,
                "csi_division":      csi_division,
                "csi_division_name": csi_div_name,
                # Content
                "description":     desc,
                "quantity":        quantity,
                "unit_of_measure": unit,
                "unit_cost":       unit_cost,
                "total_cost":      total_cost,
                # Cost breakdown
                "labor_cost":      labor_cost,
                "material_cost":   material_cost,
                "equipment_cost":  equipment_cost,
                # Labor
                "labor_hours":        labor_hours,
                "labor_rate":         labor_rate,
                "productivity_rate":  productivity_rate,
                "productivity_unit":  productivity_unit,
                # Denormalized from library entry
                "project_type":   proj_type,
                "building_type":  building_type,
                "location_state": loc_state,
                "bid_date":       bid_date,
                "bid_result":     bid_result,
            })

        return normalized

    # ------------------------------------------------------------------ #
    # Unit normalization                                                   #
    # ------------------------------------------------------------------ #

    @staticmethod
    def normalize_unit(raw_unit: str) -> str:
        """Return a canonical unit string for *raw_unit*.

        Canonical set: SF, LF, CY, EA, LS, HR, TON, GAL.
        Anything unrecognized is returned lowercase (stripped).
        """
        if not raw_unit:
            return ""
        normalized_key = raw_unit.strip().lower()
        return _UNIT_CANONICAL.get(normalized_key, raw_unit.strip().lower())

    # ------------------------------------------------------------------ #
    # Cost split estimation                                                #
    # ------------------------------------------------------------------ #

    @staticmethod
    def estimate_cost_split(total_cost: float, csi_division: Optional[int]) -> dict:
        """Return {"labor": x, "material": y, "equipment": z} for *total_cost*.

        Uses CSI_DIVISION_DEFAULTS percentages; falls back to 50/45/5 when the
        division is unknown.
        """
        ratios = CSI_DIVISION_DEFAULTS.get(csi_division, _DEFAULT_SPLIT) if csi_division is not None else _DEFAULT_SPLIT
        return {
            "labor":     round(total_cost * ratios["labor"],     2),
            "material":  round(total_cost * ratios["material"],  2),
            "equipment": round(total_cost * ratios["equipment"], 2),
        }

    # ------------------------------------------------------------------ #
    # Productivity                                                         #
    # ------------------------------------------------------------------ #

    @staticmethod
    def calculate_productivity(
        quantity: float,
        labor_hours: float,
        unit: str,
    ) -> tuple[float, str]:
        """Return (productivity_rate, productivity_unit_string).

        productivity_rate = quantity / labor_hours  (output per hour)
        productivity_unit = "<unit>/hr"
        """
        if labor_hours == 0:
            return (0.0, f"{unit}/hr")
        rate = round(quantity / labor_hours, 4)
        unit_str = f"{unit}/hr" if unit else "unit/hr"
        return (rate, unit_str)

    # ------------------------------------------------------------------ #
    # Private CSI resolution                                               #
    # ------------------------------------------------------------------ #

    def _resolve_csi(
        self,
        raw: dict,
        description: str,
    ) -> tuple[Optional[str], Optional[int]]:
        """Try three strategies to resolve a CSI code and division integer.

        1. Exact: raw data already contains a csi_code field.
        2. Keyword: scan description against _CSI_KEYWORD_MAP.
        3. Fuzzy: match description words against CSI division names.

        Returns (csi_code_str | None, division_int | None).
        """
        # Strategy 1 — raw CSI code already supplied
        raw_csi = raw.get("csi_code")
        if raw_csi:
            div_int = int(parse_csi_division(str(raw_csi))) or None
            return (str(raw_csi), div_int)

        # Strategy 2 — keyword match on description
        lower_desc = description.lower()
        for keyword, div_str in _CSI_KEYWORD_MAP.items():
            if keyword in lower_desc:
                return (f"{div_str} 00 00", int(div_str))

        # Strategy 3 — fuzzy: check if any CSI division name word appears in desc
        desc_words = set(re.findall(r"[a-z]+", lower_desc))
        for div_str, div_name in CSI_DIVISION_NAMES.items():
            for word in re.findall(r"[a-z]+", div_name.lower()):
                if len(word) >= 4 and word in desc_words:
                    return (f"{div_str} 00 00", int(div_str))

        logger.warning("Could not map to CSI: %s", description)
        return (None, None)
