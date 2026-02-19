"""Labor productivity tools for Agent 5."""

import logging
from sqlalchemy.orm import Session
from sqlalchemy import func
from apex.backend.models.productivity_history import ProductivityHistory

logger = logging.getLogger("apex.tools.labor")

# Default productivity rates when no historical data exists
DEFAULT_RATES = {
    "03 30 00": {"rate": 1.5, "unit": "CY", "crew_type": "Concrete Crew", "work_type": "Cast-in-Place Concrete"},
    "03 20 00": {"rate": 500, "unit": "LB", "crew_type": "Ironworker Crew", "work_type": "Concrete Reinforcing"},
    "03 10 00": {"rate": 50, "unit": "SF", "crew_type": "Carpenter Crew", "work_type": "Concrete Forming"},
    "05 12 00": {"rate": 0.15, "unit": "TON", "crew_type": "Ironworker Crew", "work_type": "Structural Steel"},
    "05 31 00": {"rate": 300, "unit": "SF", "crew_type": "Ironworker Crew", "work_type": "Steel Decking"},
    "05 50 00": {"rate": 100, "unit": "LB", "crew_type": "Ironworker Crew", "work_type": "Metal Fabrications"},
    "07 21 00": {"rate": 80, "unit": "SF", "crew_type": "Insulation Crew", "work_type": "Thermal Insulation"},
    "07 50 00": {"rate": 25, "unit": "SQ", "crew_type": "Roofing Crew", "work_type": "Membrane Roofing"},
    "07 60 00": {"rate": 20, "unit": "LF", "crew_type": "Sheet Metal Crew", "work_type": "Flashing"},
    "07 92 00": {"rate": 80, "unit": "LF", "crew_type": "Caulking Crew", "work_type": "Joint Sealants"},
    "08 11 00": {"rate": 4, "unit": "EA", "crew_type": "Carpentry Crew", "work_type": "Metal Doors"},
    "08 14 00": {"rate": 6, "unit": "EA", "crew_type": "Carpentry Crew", "work_type": "Wood Doors"},
    "08 50 00": {"rate": 3, "unit": "EA", "crew_type": "Glazing Crew", "work_type": "Windows"},
    "09 21 00": {"rate": 150, "unit": "SF", "crew_type": "Drywall Crew", "work_type": "Gypsum Board"},
    "09 29 00": {"rate": 150, "unit": "SF", "crew_type": "Drywall Crew", "work_type": "Gypsum Board"},
    "09 30 00": {"rate": 15, "unit": "SF", "crew_type": "Tile Crew", "work_type": "Tiling"},
    "09 51 00": {"rate": 100, "unit": "SF", "crew_type": "Ceiling Crew", "work_type": "Acoustical Ceilings"},
    "09 91 00": {"rate": 250, "unit": "SF", "crew_type": "Painting Crew", "work_type": "Painting"},
}


def productivity_lookup_tool(db: Session, csi_code: str, work_type: str = None) -> dict:
    """Look up productivity rate from historical database.

    Returns: {rate, unit, crew_type, source_count, confidence}
    """
    query = db.query(ProductivityHistory).filter(
        ProductivityHistory.csi_code == csi_code,
        ProductivityHistory.is_deleted == False,  # noqa: E712
    )
    if work_type:
        query = query.filter(ProductivityHistory.work_type == work_type)

    records = query.all()

    if records:
        # Weighted average by confidence
        total_weight = sum(r.confidence_score * r.sample_count for r in records)
        if total_weight > 0:
            weighted_rate = sum(
                r.productivity_rate * r.confidence_score * r.sample_count
                for r in records
            ) / total_weight
        else:
            weighted_rate = sum(r.productivity_rate for r in records) / len(records)

        return {
            "rate": round(weighted_rate, 4),
            "unit": records[0].unit_of_measure,
            "crew_type": records[0].crew_type,
            "work_type": records[0].work_type,
            "source_count": len(records),
            "confidence": min(0.95, 0.5 + len(records) * 0.1),
        }

    # Fall back to defaults
    normalized = csi_code.strip()
    if normalized in DEFAULT_RATES:
        d = DEFAULT_RATES[normalized]
        return {
            "rate": d["rate"],
            "unit": d["unit"],
            "crew_type": d["crew_type"],
            "work_type": d["work_type"],
            "source_count": 0,
            "confidence": 0.3,
        }

    return {
        "rate": 1.0,
        "unit": "EA",
        "crew_type": "General Crew",
        "work_type": work_type or "General",
        "source_count": 0,
        "confidence": 0.1,
    }


def crew_config_tool(crew_type: str) -> dict:
    """Get crew configuration — size and hourly rate."""
    configs = {
        "Concrete Crew": {"size": 6, "hourly_rate": 78.50},
        "Ironworker Crew": {"size": 4, "hourly_rate": 92.00},
        "Carpenter Crew": {"size": 4, "hourly_rate": 72.00},
        "Carpentry Crew": {"size": 4, "hourly_rate": 72.00},
        "Insulation Crew": {"size": 3, "hourly_rate": 65.00},
        "Roofing Crew": {"size": 5, "hourly_rate": 70.00},
        "Sheet Metal Crew": {"size": 3, "hourly_rate": 82.00},
        "Caulking Crew": {"size": 2, "hourly_rate": 62.00},
        "Drywall Crew": {"size": 4, "hourly_rate": 68.00},
        "Tile Crew": {"size": 3, "hourly_rate": 75.00},
        "Ceiling Crew": {"size": 3, "hourly_rate": 68.00},
        "Painting Crew": {"size": 4, "hourly_rate": 58.00},
        "Glazing Crew": {"size": 3, "hourly_rate": 80.00},
        "General Crew": {"size": 4, "hourly_rate": 65.00},
    }
    return configs.get(crew_type, {"size": 4, "hourly_rate": 65.00})


def duration_calculator_tool(quantity: float, rate: float, crew_size: int = 4) -> dict:
    """Calculate labor hours and crew days from quantity and rate.

    Args:
        quantity: total quantity of work
        rate: units per crew-hour
        crew_size: number of workers

    Returns: {labor_hours, crew_days, total_man_hours}
    """
    if rate <= 0:
        rate = 1.0

    crew_hours = quantity / rate
    total_man_hours = crew_hours * crew_size
    crew_days = crew_hours / 8.0  # 8-hour workday

    return {
        "labor_hours": round(crew_hours, 2),
        "crew_days": round(crew_days, 2),
        "total_man_hours": round(total_man_hours, 2),
    }
