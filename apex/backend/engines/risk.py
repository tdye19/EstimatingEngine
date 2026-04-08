"""Risk Engine — generates risk register from templates. No LLM calls."""

from sqlalchemy.orm import Session

from apex.backend.models.decision_models import RiskItem

_SEVERITY_PCT = {
    "low":      0.01,
    "medium":   0.03,
    "high":     0.06,
    "critical": 0.10,
}

RISK_TEMPLATES: dict[str, list[dict]] = {
    "default": [
        {"name": "Scope ambiguity",              "category": "scope",    "probability": 0.4, "severity": "medium"},
        {"name": "Design incompleteness",         "category": "design",   "probability": 0.3, "severity": "medium"},
        {"name": "Market volatility",             "category": "market",   "probability": 0.5, "severity": "medium"},
        {"name": "Labor availability",            "category": "labor",    "probability": 0.3, "severity": "medium"},
        {"name": "Permit/utility coordination",   "category": "schedule", "probability": 0.2, "severity": "low"},
    ],
    "industrial": [
        {"name": "Equipment lead time",           "category": "procurement","probability": 0.4, "severity": "high"},
        {"name": "Hazardous material handling",   "category": "safety",   "probability": 0.2, "severity": "high"},
        {"name": "Process tie-in complexity",     "category": "scope",    "probability": 0.3, "severity": "medium"},
    ],
    "healthcare": [
        {"name": "Infection control requirements","category": "scope",    "probability": 0.5, "severity": "medium"},
        {"name": "ICRA zone compliance",          "category": "safety",   "probability": 0.4, "severity": "medium"},
        {"name": "Phased operations impact",      "category": "schedule", "probability": 0.3, "severity": "high"},
    ],
    "data_center": [
        {"name": "Critical systems downtime risk","category": "safety",   "probability": 0.3, "severity": "critical"},
        {"name": "MEP coordination complexity",   "category": "design",   "probability": 0.5, "severity": "high"},
        {"name": "Power redundancy requirements", "category": "scope",    "probability": 0.4, "severity": "high"},
    ],
}


class RiskEngine:
    def __init__(self, db: Session):
        self.db = db

    def generate_risks(self, project, direct_cost: float) -> list[RiskItem]:
        """Generate risk register from templates, scaled by direct cost."""
        project_type = (getattr(project, "project_type", None) or "").lower()

        # Merge default + project-type-specific templates
        templates = list(RISK_TEMPLATES["default"])
        if project_type in RISK_TEMPLATES:
            templates = templates + RISK_TEMPLATES[project_type]

        items = []
        for tmpl in templates:
            severity = tmpl.get("severity", "medium")
            pct = _SEVERITY_PCT.get(severity, 0.03)
            impact_cost = round(direct_cost * pct, 2)

            item = RiskItem(
                project_id=project.id,
                name=tmpl["name"],
                category=tmpl.get("category"),
                probability=tmpl.get("probability", 0.5),
                impact_cost=impact_cost,
                severity=severity,
                source="risk_template",
            )
            self.db.add(item)
            items.append(item)

        self.db.commit()
        return items
