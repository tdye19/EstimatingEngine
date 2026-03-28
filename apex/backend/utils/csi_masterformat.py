"""CSI MasterFormat division reference data and master scope checklist.

Division names and lookup are delegated to the canonical csi_utils module.
"""

from apex.backend.utils.csi_utils import CSI_DIVISION_NAMES as CSI_DIVISIONS
from apex.backend.utils.csi_utils import get_division_name  # noqa: F401 — re-export

# Master scope checklist by division — key sections a complete spec should address
MASTER_SCOPE_CHECKLIST = {
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
    result = {}
    for div in divisions:
        if div in MASTER_SCOPE_CHECKLIST:
            result[div] = MASTER_SCOPE_CHECKLIST[div]
    return result
