"""Decision risk engine — deterministic risk item generation.

No LLM touches money. All math is Python.
"""

from sqlalchemy.orm import Session

from apex.backend.models.decision_models import RiskItem

_SEVERITY_PCT = {
    "low":      0.01,
    "medium":   0.03,
    "high":     0.06,
    "critical": 0.10,
}


class DecisionRiskEngine:
    RISK_TEMPLATES = {
        "default": [
            ("Scope ambiguity",               "scope_ambiguity",         0.4, "medium"),
            ("Design incompleteness",          "design_incompleteness",   0.3, "medium"),
            ("Market volatility",              "market_volatility",       0.5, "medium"),
            ("Labor availability",             "labor_availability",      0.3, "medium"),
            ("Permit/utility coordination",    "permit_utility",          0.2, "low"),
        ],
        "industrial": [
            ("Equipment lead time",            "equipment_lead_time",     0.4, "high"),
            ("Hazardous material handling",    "hazmat",                  0.2, "high"),
        ],
        "energy": [
            ("Regulatory compliance",          "regulatory",              0.3, "high"),
            ("Utility coordination complexity","utility_coord",           0.4, "medium"),
        ],
        "commercial": [
            ("Tenant coordination",            "tenant_coord",            0.3, "low"),
            ("Phased construction impacts",    "phased_construction",     0.25, "medium"),
        ],
        "healthcare": [
            ("Infection control requirements", "icra",                    0.4, "high"),
            ("Operational continuity",         "operational_continuity",  0.3, "high"),
        ],
    }

    def __init__(self, db: Session):
        self.db = db

    def generate_risks(self, project, direct_cost: float) -> list:
        """Generate risk items for a project based on project type and defaults."""
        project_type = getattr(project, "project_type", None) or "default"
        market_sector = getattr(project, "market_sector", None) or ""

        templates = list(self.RISK_TEMPLATES["default"])
        if project_type in self.RISK_TEMPLATES:
            templates += self.RISK_TEMPLATES[project_type]
        if market_sector in self.RISK_TEMPLATES and market_sector != project_type:
            templates += self.RISK_TEMPLATES[market_sector]

        # Delete existing risk items for this project
        self.db.query(RiskItem).filter(
            RiskItem.project_id == project.id
        ).delete(synchronize_session=False)

        items = []
        for name, category, probability, severity in templates:
            severity_pct = _SEVERITY_PCT.get(severity, 0.03)
            impact_cost = round(direct_cost * severity_pct, 2)
            item = RiskItem(
                project_id=project.id,
                name=name,
                category=category,
                probability=probability,
                impact_cost=impact_cost,
                severity=severity,
                source="template",
            )
            self.db.add(item)
            items.append(item)

        self.db.flush()
        return items
