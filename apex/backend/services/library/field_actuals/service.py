"""Field Actuals Service — manages what crews actually produced on completed projects.

ALL MATH IS DETERMINISTIC PYTHON. No LLM.

Data flow:
  - Ingest WinEst close-out exports (same 26-col/21-col format as PB)
  - Store in field_actuals_projects + field_actuals_line_items tables
  - Query averaged field rates for comparison against estimating rates

Key distinction:
  - PB stores estimating rates (what estimators predicted)
  - Field Actuals stores production rates (what crews actually did)
  - The delta is the calibration signal
"""

import hashlib
from difflib import SequenceMatcher

from sqlalchemy import func
from sqlalchemy.orm import Session

from apex.backend.models.field_actuals import FieldActualsLineItem, FieldActualsProject
from apex.backend.services.takeoff_parser.parser import parse_takeoff


def _compute_file_hash(filepath: str) -> str:
    """MD5 hash of file contents for dedup."""
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


class FieldActualsService:
    """Manages field actuals data — what crews actually produced on completed projects."""

    def __init__(self, db: Session):
        self.db = db

    def ingest_file(
        self,
        filepath: str,
        filename: str,
        project_name: str = None,
        region: str = None,
    ) -> dict:
        """Ingest a WinEst close-out export.

        Reuses takeoff_parser for format detection and parsing (same 26-col/21-col
        format), but stores results in field_actuals tables instead of PB tables.

        Returns {status, project_id, line_items_count} or {status, reason}.
        """
        fhash = _compute_file_hash(filepath)

        # Dedup by hash
        existing = self.db.query(FieldActualsProject).filter_by(file_hash=fhash).first()
        if existing:
            return {
                "status": "skipped",
                "reason": "duplicate",
                "project_id": existing.id,
                "name": existing.name,
            }

        # Parse using shared takeoff parser
        items, fmt = parse_takeoff(filepath)
        if not items:
            return {
                "status": "error",
                "reason": f"No line items parsed from {filename} (format={fmt})",
            }

        # Create project record
        project = FieldActualsProject(
            name=project_name or filename,
            source_file=filename,
            file_hash=fhash,
            project_type="completed",
            region=region,
        )
        self.db.add(project)
        self.db.flush()

        # Create line item records
        for item in items:
            li = FieldActualsLineItem(
                project_id=project.id,
                wbs_area=item.wbs_area,
                activity=item.activity,
                quantity=item.quantity,
                unit=item.unit,
                crew_trade=item.crew,
                actual_production_rate=item.production_rate,
                actual_labor_hours=None,  # Not in takeoff format
                actual_labor_cost=item.labor_cost_per_unit,
                actual_material_cost=item.material_cost_per_unit,
                csi_code=item.csi_code,
            )
            self.db.add(li)

        self.db.commit()

        return {
            "status": "ingested",
            "project_id": project.id,
            "name": project.name,
            "format": fmt,
            "line_items_count": len(items),
        }

    def get_field_rates(
        self,
        activity: str = None,
        unit: str = None,
    ) -> list[dict]:
        """Query averaged field rates grouped by activity + unit.

        Returns list of dicts with avg/min/max actual_production_rate, count, projects.
        All math is deterministic Python.
        """
        q = self.db.query(
            FieldActualsLineItem.activity,
            FieldActualsLineItem.unit,
            func.count(FieldActualsLineItem.id).label("sample_count"),
            func.count(func.distinct(FieldActualsLineItem.project_id)).label("project_count"),
            func.avg(FieldActualsLineItem.actual_production_rate).label("avg_rate"),
            func.min(FieldActualsLineItem.actual_production_rate).label("min_rate"),
            func.max(FieldActualsLineItem.actual_production_rate).label("max_rate"),
        ).filter(
            FieldActualsLineItem.actual_production_rate.isnot(None),
        )

        if activity:
            q = q.filter(FieldActualsLineItem.activity.ilike(f"%{activity}%"))
        if unit:
            q = q.filter(FieldActualsLineItem.unit == unit)

        q = q.group_by(FieldActualsLineItem.activity, FieldActualsLineItem.unit)
        q = q.order_by(FieldActualsLineItem.activity)

        results = []
        for r in q.all():
            # Get project names for this activity+unit
            projects = (
                self.db.query(func.distinct(FieldActualsProject.name))
                .join(FieldActualsLineItem, FieldActualsLineItem.project_id == FieldActualsProject.id)
                .filter(
                    FieldActualsLineItem.activity == r.activity,
                    FieldActualsLineItem.unit == r.unit,
                    FieldActualsLineItem.actual_production_rate.isnot(None),
                )
                .all()
            )
            project_names = [p[0] for p in projects if p[0]]

            results.append(
                {
                    "activity": r.activity,
                    "unit": r.unit,
                    "sample_count": r.sample_count,
                    "project_count": r.project_count,
                    "avg_rate": round(r.avg_rate, 4) if r.avg_rate else None,
                    "min_rate": round(r.min_rate, 4) if r.min_rate else None,
                    "max_rate": round(r.max_rate, 4) if r.max_rate else None,
                    "projects": project_names,
                }
            )

        return results

    def match_field_data(
        self,
        activity: str,
        unit: str = None,
    ) -> dict | None:
        """Find field actuals for a specific activity.

        Uses fuzzy matching (same approach as rate_engine) when exact match unavailable.
        Returns {avg_rate, min_rate, max_rate, sample_count, projects} or None.
        """
        # Try exact match first
        exact = self._query_rates(activity, unit)
        if exact:
            return exact

        # Fuzzy match — get distinct activities with field data
        distinct_activities = (
            self.db.query(FieldActualsLineItem.activity)
            .filter(FieldActualsLineItem.actual_production_rate.isnot(None))
            .distinct()
            .all()
        )

        activity_lower = activity.lower().strip()
        best_score = 0.0
        best_activity = None

        for (act,) in distinct_activities:
            score = SequenceMatcher(None, activity_lower, act.lower()).ratio()
            if score > best_score and score >= 0.6:
                best_score = score
                best_activity = act

        if best_activity is None:
            return None

        return self._query_rates(best_activity, unit)

    def _query_rates(self, activity: str, unit: str = None) -> dict | None:
        """Query aggregated field rates for exact activity match."""
        q = self.db.query(
            func.avg(FieldActualsLineItem.actual_production_rate).label("avg_rate"),
            func.min(FieldActualsLineItem.actual_production_rate).label("min_rate"),
            func.max(FieldActualsLineItem.actual_production_rate).label("max_rate"),
            func.count(FieldActualsLineItem.id).label("sample_count"),
        ).filter(
            FieldActualsLineItem.activity == activity,
            FieldActualsLineItem.actual_production_rate.isnot(None),
        )

        if unit:
            q = q.filter(FieldActualsLineItem.unit == unit)

        r = q.first()
        if not r or not r.sample_count:
            return None

        # Get project names
        projects = (
            self.db.query(func.distinct(FieldActualsProject.name))
            .join(FieldActualsLineItem, FieldActualsLineItem.project_id == FieldActualsProject.id)
            .filter(
                FieldActualsLineItem.activity == activity,
                FieldActualsLineItem.actual_production_rate.isnot(None),
            )
            .all()
        )
        project_names = [p[0] for p in projects if p[0]]

        return {
            "avg_rate": round(r.avg_rate, 4),
            "min_rate": round(r.min_rate, 4),
            "max_rate": round(r.max_rate, 4),
            "sample_count": r.sample_count,
            "projects": project_names,
        }

    def get_stats(self) -> dict:
        """Summary statistics for field actuals database."""
        total_projects = self.db.query(func.count(FieldActualsProject.id)).scalar() or 0
        total_items = self.db.query(func.count(FieldActualsLineItem.id)).scalar() or 0
        total_activities = (
            self.db.query(func.count(func.distinct(FieldActualsLineItem.activity)))
            .filter(FieldActualsLineItem.actual_production_rate.isnot(None))
            .scalar()
            or 0
        )

        return {
            "total_projects": total_projects,
            "total_line_items": total_items,
            "total_activities": total_activities,
        }

    def get_projects(self) -> list[dict]:
        """List all ingested field actuals projects."""
        projects = self.db.query(FieldActualsProject).order_by(FieldActualsProject.name).all()
        return [
            {
                "id": p.id,
                "name": p.name,
                "source_file": p.source_file,
                "project_type": p.project_type,
                "completion_date": p.completion_date.isoformat() if p.completion_date else None,
                "region": p.region,
                "ingested_at": p.ingested_at.isoformat() if p.ingested_at else None,
            }
            for p in projects
        ]
