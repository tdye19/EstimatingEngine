"""Business logic layer for Productivity Brain."""

import hashlib
import os
from difflib import SequenceMatcher

from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from apex.backend.services.library.productivity_brain.models import PBLineItem, PBProject
from apex.backend.services.library.productivity_brain.parser import (
    compute_file_hash,
    detect_format,
    parse_21col,
    parse_26col,
    parse_averaged_rates,
)
from apex.backend.services.library.productivity_brain.parsers import (
    MultiProjectRatesParser,
    ParsedProject,
)

_PARSERS = {
    "26col_civil": parse_26col,
    "21col_estimate": parse_21col,
    "averaged_rates": parse_averaged_rates,
}


class LoadResult(BaseModel):
    projects_upserted_new: int = 0
    projects_upserted_existing: int = 0
    line_items_inserted: int = 0
    line_items_updated: int = 0
    line_items_skipped_empty: int = 0
    pb_project_ids: list[int] = []
    metadata_applied: dict = {}
    warnings: list[str] = []


def _project_file_hash(file_md5: str, source_project: str) -> str:
    """Per-project synthetic hash that (a) fits String(32) and (b) keeps
    PBProject.file_hash UNIQUE when one file yields multiple PBProjects.
    Also supports file-level idempotency: recomputing the same pair is
    deterministic, so DATA-1.2 can ask 'has this file been loaded?' by
    re-hashing each parsed project and checking for any hit."""
    return hashlib.md5(f"{file_md5}||{source_project}".encode()).hexdigest()


class ProductivityBrainService:
    def __init__(self, db: Session):
        self.db = db

    # ── Ingestion ──

    def ingest_file(self, filepath: str, filename: str) -> dict:
        """Ingest a single file. Returns summary dict."""
        fhash = compute_file_hash(filepath)

        # Dedup by hash
        existing = self.db.query(PBProject).filter_by(file_hash=fhash).first()
        if existing:
            return {
                "status": "skipped",
                "reason": "duplicate",
                "project_id": existing.id,
                "name": existing.name,
            }

        fmt = detect_format(filepath)
        if fmt == "unknown":
            return {"status": "error", "reason": f"unknown format: {filename}"}

        parser = _PARSERS[fmt]
        rows = parser(filepath)

        project = PBProject(
            name=filename,
            source_file=filename,
            file_hash=fhash,
            format_type=fmt,
            project_count=1 if fmt != "averaged_rates" else self._count_projects(rows),
            total_line_items=len(rows),
        )
        self.db.add(project)
        self.db.flush()  # get project.id

        for row in rows:
            item = PBLineItem(project_id=project.id, **row)
            self.db.add(item)

        self.db.commit()

        return {
            "status": "ingested",
            "project_id": project.id,
            "name": project.name,
            "format": fmt,
            "line_items": len(rows),
        }

    def batch_ingest(self, filepaths: list[tuple[str, str]]) -> list[dict]:
        """Ingest multiple files. Each tuple is (filepath, filename)."""
        return [self.ingest_file(fp, fn) for fp, fn in filepaths]

    # ── Multi-project (DATA-1.1) ──

    def load_multi_project_file(
        self,
        db: Session,
        file_path: str,
        metadata_overrides: dict | None = None,
    ) -> LoadResult:
        """Parse a multi-project rates file and upsert one PBProject per
        per-project column, with PBLineItems keyed on
        (project_id, activity, unit).

        Re-running is safe: same (project_name) → existing PBProject is
        updated in place; same (project_id, activity, unit) → existing
        PBLineItem is updated. No duplicate rows.
        """
        if db is not self.db:
            # Caller passed a different session — honour it but use ours for
            # query convenience via a temporary swap.
            self.db = db

        parser = MultiProjectRatesParser()
        if not parser.detect(file_path):
            raise ValueError(
                f"File format not recognised as multi-project rates: {file_path}"
            )

        file_md5 = compute_file_hash(file_path)
        parse_result = parser.parse(file_path, metadata_overrides=metadata_overrides)

        result = LoadResult(
            warnings=list(parse_result.warnings),
            metadata_applied=dict(metadata_overrides or {}),
        )
        file_basename = os.path.basename(file_path)

        for parsed in parse_result.parsed_projects:
            self._upsert_project(
                parsed=parsed,
                file_md5=file_md5,
                file_basename=file_basename,
                result=result,
            )

        self.db.commit()
        return result

    def _upsert_project(
        self,
        *,
        parsed: ParsedProject,
        file_md5: str,
        file_basename: str,
        result: LoadResult,
    ) -> None:
        synthetic_hash = _project_file_hash(file_md5, parsed.source_project)
        pb_proj = (
            self.db.query(PBProject)
            .filter(PBProject.name == parsed.project_name)
            .first()
        )

        if pb_proj is None:
            pb_proj = PBProject(
                name=parsed.project_name,
                source_file=file_basename,
                file_hash=synthetic_hash,
                format_type="multi_project_rates",
                project_count=1,
                total_line_items=len(parsed.line_items),
            )
            self.db.add(pb_proj)
            self.db.flush()
            result.projects_upserted_new += 1
        else:
            pb_proj.source_file = file_basename
            pb_proj.file_hash = synthetic_hash
            pb_proj.format_type = "multi_project_rates"
            pb_proj.total_line_items = len(parsed.line_items)
            result.projects_upserted_existing += 1

        if len(parsed.line_items) == 0:
            result.line_items_skipped_empty += 1

        existing = {
            (li.activity, li.unit): li
            for li in self.db.query(PBLineItem).filter(PBLineItem.project_id == pb_proj.id).all()
        }
        seen_keys: set[tuple[str, str]] = set()

        for item in parsed.line_items:
            key = (item.activity_description, item.unit)
            seen_keys.add(key)
            existing_row = existing.get(key)
            if existing_row is None:
                self.db.add(
                    PBLineItem(
                        project_id=pb_proj.id,
                        wbs_area=item.wbs_area,
                        activity=item.activity_description,
                        unit=item.unit,
                        crew_trade=item.crew,
                        production_rate=item.production_rate,
                        labor_cost_per_unit=item.labor_cost_per_unit,
                        material_cost_per_unit=item.material_cost_per_unit,
                        csi_code=item.csi_code,
                        source_project=parsed.source_project,
                    )
                )
                result.line_items_inserted += 1
            else:
                existing_row.wbs_area = item.wbs_area
                existing_row.crew_trade = item.crew
                existing_row.production_rate = item.production_rate
                existing_row.labor_cost_per_unit = item.labor_cost_per_unit
                existing_row.material_cost_per_unit = item.material_cost_per_unit
                existing_row.source_project = parsed.source_project
                result.line_items_updated += 1

        result.pb_project_ids.append(pb_proj.id)

    # ── Querying ──

    def get_rates(
        self,
        activity: str | None = None,
        wbs: str | None = None,
        unit: str | None = None,
    ) -> list[dict]:
        """Averaged rates grouped by activity+unit. All math is deterministic Python."""
        q = self.db.query(
            PBLineItem.activity,
            PBLineItem.unit,
            func.count(PBLineItem.id).label("occurrences"),
            func.count(func.distinct(PBLineItem.project_id)).label("project_count"),
            func.avg(PBLineItem.production_rate).label("avg_rate"),
            func.min(PBLineItem.production_rate).label("min_rate"),
            func.max(PBLineItem.production_rate).label("max_rate"),
            func.avg(PBLineItem.labor_cost_per_unit).label("avg_labor_cost"),
            func.avg(PBLineItem.material_cost_per_unit).label("avg_material_cost"),
        ).filter(
            PBLineItem.production_rate.isnot(None),
        )

        if activity:
            q = q.filter(PBLineItem.activity.ilike(f"%{activity}%"))
        if wbs:
            q = q.filter(PBLineItem.wbs_area.ilike(f"%{wbs}%"))
        if unit:
            q = q.filter(PBLineItem.unit == unit)

        q = q.group_by(PBLineItem.activity, PBLineItem.unit)
        q = q.order_by(PBLineItem.activity)

        return [
            {
                "activity": r.activity,
                "unit": r.unit,
                "occurrences": r.occurrences,
                "project_count": r.project_count,
                "avg_rate": round(r.avg_rate, 2) if r.avg_rate else None,
                "min_rate": round(r.min_rate, 2) if r.min_rate else None,
                "max_rate": round(r.max_rate, 2) if r.max_rate else None,
                "avg_labor_cost_per_unit": round(r.avg_labor_cost, 2) if r.avg_labor_cost else None,
                "avg_material_cost_per_unit": round(r.avg_material_cost, 2) if r.avg_material_cost else None,
            }
            for r in q.all()
        ]

    def compare_estimate(self, estimate_items: list[dict]) -> list[dict]:
        """Compare line items against historical averages.

        Each input dict needs: activity, production_rate.
        Returns items with historical_avg, delta_pct, flag.
        All percentages computed in deterministic Python.
        """
        results = []
        for item in estimate_items:
            activity = item.get("activity", "")
            current_rate = item.get("production_rate")

            hist = (
                self.db.query(
                    func.avg(PBLineItem.production_rate).label("avg"),
                    func.count(PBLineItem.id).label("cnt"),
                )
                .filter(
                    PBLineItem.activity == activity,
                    PBLineItem.production_rate.isnot(None),
                )
                .first()
            )

            if hist and hist.cnt > 0 and current_rate:
                avg = round(hist.avg, 2)
                delta_pct = round(((avg - current_rate) / current_rate) * 100, 1) if current_rate != 0 else 0.0

                if abs(delta_pct) < 5:
                    flag = "OK"
                elif abs(delta_pct) < 20:
                    flag = "REVIEW"
                else:
                    flag = "UPDATE"

                results.append(
                    {
                        **item,
                        "historical_avg": avg,
                        "historical_count": hist.cnt,
                        "delta_pct": delta_pct,
                        "flag": flag,
                    }
                )
            else:
                results.append(
                    {
                        **item,
                        "historical_avg": None,
                        "historical_count": 0,
                        "delta_pct": None,
                        "flag": "NO DATA",
                    }
                )

        return results

    def get_stats(self) -> dict:
        """Summary statistics for the PB database."""
        total_projects = self.db.query(func.count(PBProject.id)).scalar() or 0
        total_items = self.db.query(func.count(PBLineItem.id)).scalar() or 0
        total_activities = (
            self.db.query(func.count(func.distinct(PBLineItem.activity)))
            .filter(PBLineItem.production_rate.isnot(None))
            .scalar()
            or 0
        )

        format_breakdown = dict(
            self.db.query(PBProject.format_type, func.count(PBProject.id)).group_by(PBProject.format_type).all()
        )

        return {
            "total_projects": total_projects,
            "total_line_items": total_items,
            "total_activities": total_activities,
            "format_breakdown": format_breakdown,
        }

    def get_projects(self) -> list[dict]:
        """List all ingested projects with summary info."""
        projects = self.db.query(PBProject).order_by(PBProject.name).all()
        return [
            {
                "id": p.id,
                "name": p.name,
                "source_file": p.source_file,
                "format_type": p.format_type,
                "project_count": p.project_count,
                "total_line_items": p.total_line_items,
                "ingested_at": p.ingested_at.isoformat() if p.ingested_at else None,
            }
            for p in projects
        ]

    def match_activity(
        self,
        csi_code: str | None,
        description: str | None,
        unit: str | None,
    ) -> dict | None:
        """Find the best matching PB activity for Agent 4.

        Priority:
          1. Exact CSI code match
          2. Fuzzy description match (SequenceMatcher >= 0.6)
          3. Unit + crew tiebreaker among fuzzy matches

        Returns averaged rate data or None.
        """
        # 1) Exact CSI match
        if csi_code:
            match = self._rates_for_filter(PBLineItem.csi_code == csi_code)
            if match:
                return match[0]

        if not description:
            return None

        # 2) Fuzzy description match — pull distinct activities then score
        distinct_activities = (
            self.db.query(PBLineItem.activity).filter(PBLineItem.production_rate.isnot(None)).distinct().all()
        )

        desc_lower = description.lower()
        scored = []
        for (act,) in distinct_activities:
            ratio = SequenceMatcher(None, desc_lower, act.lower()).ratio()
            if ratio >= 0.6:
                scored.append((ratio, act))

        if not scored:
            return None

        scored.sort(key=lambda x: x[0], reverse=True)

        # 3) Unit tiebreaker among top matches
        if unit:
            for _ratio, act in scored:
                match = self._rates_for_filter(
                    PBLineItem.activity == act,
                    PBLineItem.unit == unit,
                )
                if match:
                    return match[0]

        # Fallback: best fuzzy match regardless of unit
        best_act = scored[0][1]
        match = self._rates_for_filter(PBLineItem.activity == best_act)
        return match[0] if match else None

    # ── Private helpers ──

    def _rates_for_filter(self, *filters) -> list[dict]:
        """Aggregate rates for given filter criteria."""
        q = (
            self.db.query(
                PBLineItem.activity,
                PBLineItem.unit,
                PBLineItem.crew_trade,
                func.count(PBLineItem.id).label("occurrences"),
                func.count(func.distinct(PBLineItem.project_id)).label("project_count"),
                func.avg(PBLineItem.production_rate).label("avg_rate"),
                func.min(PBLineItem.production_rate).label("min_rate"),
                func.max(PBLineItem.production_rate).label("max_rate"),
                func.avg(PBLineItem.labor_cost_per_unit).label("avg_labor_cost"),
                func.avg(PBLineItem.material_cost_per_unit).label("avg_material_cost"),
            )
            .filter(
                PBLineItem.production_rate.isnot(None),
                *filters,
            )
            .group_by(
                PBLineItem.activity,
                PBLineItem.unit,
                PBLineItem.crew_trade,
            )
        )

        return [
            {
                "activity": r.activity,
                "unit": r.unit,
                "crew_trade": r.crew_trade,
                "occurrences": r.occurrences,
                "project_count": r.project_count,
                "avg_rate": round(r.avg_rate, 2) if r.avg_rate else None,
                "min_rate": round(r.min_rate, 2) if r.min_rate else None,
                "max_rate": round(r.max_rate, 2) if r.max_rate else None,
                "avg_labor_cost_per_unit": round(r.avg_labor_cost, 2) if r.avg_labor_cost else None,
                "avg_material_cost_per_unit": round(r.avg_material_cost, 2) if r.avg_material_cost else None,
            }
            for r in q.all()
        ]

    @staticmethod
    def _count_projects(rows: list[dict]) -> int:
        """Count unique source_project values in parsed rows."""
        sources = {r.get("source_project") for r in rows if r.get("source_project")}
        sources.discard("_averaged")
        return max(len(sources), 1)
