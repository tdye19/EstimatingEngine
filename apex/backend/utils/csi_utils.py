"""Consolidated CSI MasterFormat utilities.

Single source of truth for:
- CSI division code parsing
- Division name lookup
- Unit of measure normalization

All services that need CSI logic should import from here.
"""

import re

# ---------------------------------------------------------------------------
# CSI Division Names — maps 2-char division to human-readable name
# ---------------------------------------------------------------------------

CSI_DIVISION_NAMES: dict[str, str] = {
    "01": "General Requirements",
    "02": "Existing Conditions",
    "03": "Concrete",
    "04": "Masonry",
    "05": "Metals",
    "06": "Wood, Plastics, and Composites",
    "07": "Thermal and Moisture Protection",
    "08": "Openings",
    "09": "Finishes",
    "10": "Specialties",
    "11": "Equipment",
    "12": "Furnishings",
    "13": "Special Construction",
    "14": "Conveying Equipment",
    "15": "Mechanical (Legacy)",
    "16": "Electrical (Legacy)",
    "21": "Fire Suppression",
    "22": "Plumbing",
    "23": "HVAC",
    "24": "HVAC Instrumentation and Controls (Legacy)",
    "25": "Integrated Automation",
    "26": "Electrical",
    "27": "Communications",
    "28": "Electronic Safety and Security",
    "31": "Earthwork",
    "32": "Exterior Improvements",
    "33": "Utilities",
    "34": "Transportation",
    "35": "Waterway and Marine Construction",
    "40": "Process Interconnections",
    "41": "Material Processing and Handling Equipment",
    "42": "Process Heating, Cooling, and Drying Equipment",
    "43": "Process Gas and Liquid Handling, Purification, and Storage Equipment",
    "44": "Pollution and Waste Control Equipment",
    "45": "Industry-Specific Manufacturing Equipment",
    "46": "Water and Wastewater Equipment",
    "47": "Reserved for Future Use",
    "48": "Electrical Power Generation",
}

# ---------------------------------------------------------------------------
# CSI division parsing
# ---------------------------------------------------------------------------

_CSI_RE = re.compile(r"^(\d{2})")


def parse_csi_division(csi_code: str) -> str:
    """Extract the 2-character division string from a CSI code.

    Handles formats like:
      "03 30 00"  -> "03"
      "09"        -> "09"
      "031000"    -> "03"
      " 05 50 00" -> "05"  (leading whitespace)
      ""          -> "00"  (fallback)
      None-ish    -> "00"  (fallback)

    Returns:
        2-char division string, zero-padded. Falls back to "00" on bad input.
    """
    if not csi_code or not isinstance(csi_code, str):
        return "00"

    cleaned = csi_code.strip()
    if not cleaned:
        return "00"

    m = _CSI_RE.match(cleaned)
    if m:
        return m.group(1)

    return "00"


# ---------------------------------------------------------------------------
# Division name lookup
# ---------------------------------------------------------------------------


def get_division_name(division: str) -> str:
    """Return the human-readable name for a CSI division code.

    Args:
        division: 2-char division string (e.g. "03", "26")

    Returns:
        Division name, or "Division XX" if not found.
    """
    return CSI_DIVISION_NAMES.get(division, f"Division {division}")


# ---------------------------------------------------------------------------
# Unit of measure normalization
# ---------------------------------------------------------------------------

_UOM_MAP: dict[str, str] = {
    # SF
    "SF": "SF",
    "SQ FT": "SF",
    "SQFT": "SF",
    "SQUARE FEET": "SF",
    "SQUARE FOOT": "SF",
    "SQ. FT.": "SF",
    "SQ.FT.": "SF",
    "SQ. FT": "SF",
    # SY
    "SY": "SY",
    "SQ YD": "SY",
    "SQYD": "SY",
    "SQUARE YARD": "SY",
    "SQUARE YARDS": "SY",
    "SQ. YD.": "SY",
    "SQ. YD": "SY",
    # CY
    "CY": "CY",
    "CUBIC YARD": "CY",
    "CUBIC YARDS": "CY",
    "CU YD": "CY",
    "CU. YD.": "CY",
    "CU. YD": "CY",
    "CU YD.": "CY",
    "CUYD": "CY",
    # LF
    "LF": "LF",
    "LIN FT": "LF",
    "LINEAR FEET": "LF",
    "LINEAR FOOT": "LF",
    "LINEAL FOOT": "LF",
    "LINEAL FEET": "LF",
    "LIN. FT.": "LF",
    "LIN. FT": "LF",
    # EA
    "EA": "EA",
    "EACH": "EA",
    "EA.": "EA",
    "PCS": "EA",
    "PIECE": "EA",
    "PIECES": "EA",
    "PC": "EA",
    # LS
    "LS": "LS",
    "LUMP SUM": "LS",
    "L.S.": "LS",
    "LUMPSUM": "LS",
    # TON
    "TON": "TON",
    "TONS": "TON",
    "T": "TON",
    # GAL
    "GAL": "GAL",
    "GALLON": "GAL",
    "GALLONS": "GAL",
    # CF
    "CF": "CF",
    "CU FT": "CF",
    "CUBIC FOOT": "CF",
    "CUBIC FEET": "CF",
    # HR
    "HR": "HR",
    "HOUR": "HR",
    "HOURS": "HR",
    "HRS": "HR",
    # DAY
    "DAY": "DAY",
    "DAYS": "DAY",
    # MO
    "MO": "MO",
    "MONTH": "MO",
    "MONTHS": "MO",
    # LB
    "LB": "LB",
    "LBS": "LB",
    "POUND": "LB",
    "POUNDS": "LB",
}


def normalize_uom(raw_uom: str) -> str:
    """Normalize a unit of measure string to its canonical abbreviation.

    Args:
        raw_uom: Raw UOM string from import data (e.g. "SQ FT", "cubic yard")

    Returns:
        Canonical UOM (e.g. "SF", "CY"). Returns the uppercased/stripped
        input if no mapping is found.
    """
    if not raw_uom or not isinstance(raw_uom, str):
        return ""

    key = raw_uom.strip().upper()
    if not key:
        return ""

    return _UOM_MAP.get(key, key)


# ---------------------------------------------------------------------------
# Master scope checklist by division
# ---------------------------------------------------------------------------

MASTER_SCOPE_CHECKLIST: dict[str, list[dict]] = {
    "03": [
        {"section": "03 10 00", "title": "Concrete Forming and Accessories", "required": True},
        {"section": "03 20 00", "title": "Concrete Reinforcing", "required": True},
        {"section": "03 30 00", "title": "Cast-in-Place Concrete", "required": True},
        {"section": "03 35 00", "title": "Concrete Finishing", "required": True},
        {"section": "03 40 00", "title": "Precast Concrete", "required": False},
        {"section": "03 45 00", "title": "Precast Architectural Concrete", "required": False},
        {"section": "03 50 00", "title": "Cast Decks and Underlayment", "required": False},
        {"section": "03 60 00", "title": "Grouting", "required": False},
    ],
    "05": [
        {"section": "05 10 00", "title": "Structural Metal Framing", "required": True},
        {"section": "05 12 00", "title": "Structural Steel Framing", "required": True},
        {"section": "05 21 00", "title": "Steel Joist Framing", "required": False},
        {"section": "05 31 00", "title": "Steel Decking", "required": True},
        {"section": "05 40 00", "title": "Cold-Formed Metal Framing", "required": False},
        {"section": "05 50 00", "title": "Metal Fabrications", "required": True},
        {"section": "05 51 00", "title": "Metal Stairs", "required": False},
        {"section": "05 52 00", "title": "Metal Railings", "required": True},
    ],
    "07": [
        {"section": "07 10 00", "title": "Dampproofing and Waterproofing", "required": True},
        {"section": "07 21 00", "title": "Thermal Insulation", "required": True},
        {"section": "07 26 00", "title": "Vapor Retarders", "required": True},
        {"section": "07 27 00", "title": "Air Barriers", "required": True},
        {"section": "07 31 00", "title": "Shingles and Shakes", "required": False},
        {"section": "07 41 00", "title": "Roof Panels", "required": False},
        {"section": "07 46 00", "title": "Siding", "required": False},
        {"section": "07 50 00", "title": "Membrane Roofing", "required": True},
        {"section": "07 60 00", "title": "Flashing and Sheet Metal", "required": True},
        {"section": "07 70 00", "title": "Roof and Wall Specialties", "required": True},
        {"section": "07 84 00", "title": "Firestopping", "required": True},
        {"section": "07 92 00", "title": "Joint Sealants", "required": True},
    ],
    "08": [
        {"section": "08 11 00", "title": "Metal Doors and Frames", "required": True},
        {"section": "08 14 00", "title": "Wood Doors", "required": True},
        {"section": "08 31 00", "title": "Access Doors and Panels", "required": True},
        {"section": "08 41 00", "title": "Entrances and Storefronts", "required": True},
        {"section": "08 44 00", "title": "Curtain Wall and Glazed Assemblies", "required": False},
        {"section": "08 50 00", "title": "Windows", "required": True},
        {"section": "08 71 00", "title": "Door Hardware", "required": True},
        {"section": "08 80 00", "title": "Glazing", "required": True},
    ],
    "09": [
        {"section": "09 21 00", "title": "Plaster and Gypsum Board Assemblies", "required": True},
        {"section": "09 22 00", "title": "Supports for Plaster and Gypsum Board", "required": True},
        {"section": "09 29 00", "title": "Gypsum Board", "required": True},
        {"section": "09 30 00", "title": "Tiling", "required": True},
        {"section": "09 51 00", "title": "Acoustical Ceilings", "required": True},
        {"section": "09 65 00", "title": "Resilient Flooring", "required": False},
        {"section": "09 68 00", "title": "Carpeting", "required": False},
        {"section": "09 72 00", "title": "Wall Coverings", "required": False},
        {"section": "09 91 00", "title": "Painting", "required": True},
        {"section": "09 96 00", "title": "High-Performance Coatings", "required": False},
    ],
    "26": [
        {"section": "26 05 00", "title": "Common Work Results for Electrical", "required": True},
        {"section": "26 09 00", "title": "Instrumentation and Control for Electrical", "required": False},
        {"section": "26 20 00", "title": "Low-Voltage Electrical Power Generation and Storage", "required": False},
        {"section": "26 24 00", "title": "Switchboards and Panelboards", "required": True},
        {"section": "26 27 00", "title": "Low-Voltage Distribution Equipment", "required": True},
        {"section": "26 28 00", "title": "Low-Voltage Circuit Protective Devices", "required": True},
        {"section": "26 50 00", "title": "Lighting", "required": True},
    ],
}


def get_checklist_for_divisions(divisions: list[str]) -> dict:
    """Return the master scope checklist entries for the given divisions."""
    result = {}
    for div in divisions:
        if div in MASTER_SCOPE_CHECKLIST:
            result[div] = MASTER_SCOPE_CHECKLIST[div]
    return result
