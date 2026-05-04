"""Tests for persistence adapters (agent_1 and agent_4 bridges)."""

import pytest


# ---------------------------------------------------------------------------
# Agent 1 adapter: adapt_agent1_plan_sets
# ---------------------------------------------------------------------------


class TestAgent1PlanSetAdapter:
    def _run(self, db_session, project, result, run_log_id=None):
        from apex.backend.services.persistence_adapters import adapt_agent1_plan_sets

        adapt_agent1_plan_sets(db_session, project.id, result, run_log_id)

    def test_creates_plan_set_and_sheets_for_pdf(self, db_session, test_project):
        from apex.backend.models.plan_set import PlanSet, PlanSheet

        result = {
            "results": [
                {"status": "success", "document_id": 999, "filename": "drawings.pdf", "pages": 3, "chars": 5000}
            ]
        }
        self._run(db_session, test_project, result, run_log_id=1)

        plan_set = db_session.query(PlanSet).filter(PlanSet.upload_id == 999).first()
        assert plan_set is not None
        assert plan_set.project_id == test_project.id
        assert plan_set.sheet_count == 3
        assert plan_set.status == "ready"
        assert plan_set.source_filename == "drawings.pdf"

        sheets = db_session.query(PlanSheet).filter(PlanSheet.plan_set_id == plan_set.id).all()
        assert len(sheets) == 3
        page_indices = sorted(s.page_index for s in sheets)
        assert page_indices == [0, 1, 2]

    def test_skips_winest_docs_with_zero_pages(self, db_session, test_project):
        from apex.backend.models.plan_set import PlanSet

        result = {
            "results": [
                {"status": "success", "document_id": 888, "filename": "takeoff.xlsx", "pages": 0, "chars": 0}
            ]
        }
        self._run(db_session, test_project, result)

        plan_set = db_session.query(PlanSet).filter(PlanSet.upload_id == 888).first()
        assert plan_set is None

    def test_skips_failed_documents(self, db_session, test_project):
        from apex.backend.models.plan_set import PlanSet

        result = {
            "results": [
                {"status": "error", "document_id": 777, "filename": "corrupt.pdf", "pages": 5, "chars": 0}
            ]
        }
        self._run(db_session, test_project, result)
        assert db_session.query(PlanSet).filter(PlanSet.upload_id == 777).first() is None

    def test_idempotent_on_second_run(self, db_session, test_project):
        from apex.backend.models.plan_set import PlanSet, PlanSheet

        result = {
            "results": [
                {"status": "success", "document_id": 666, "filename": "plans.pdf", "pages": 2, "chars": 1000}
            ]
        }
        self._run(db_session, test_project, result)
        self._run(db_session, test_project, result)  # second run must not duplicate

        sets = db_session.query(PlanSet).filter(PlanSet.upload_id == 666).all()
        assert len(sets) == 1
        sheets = db_session.query(PlanSheet).filter(PlanSheet.plan_set_id == sets[0].id).all()
        assert len(sheets) == 2

    def test_multiple_docs_in_one_run(self, db_session, test_project):
        from apex.backend.models.plan_set import PlanSet

        result = {
            "results": [
                {"status": "success", "document_id": 501, "filename": "arch.pdf", "pages": 10, "chars": 9000},
                {"status": "success", "document_id": 502, "filename": "struct.pdf", "pages": 5, "chars": 4000},
            ]
        }
        self._run(db_session, test_project, result)

        assert db_session.query(PlanSet).filter(PlanSet.upload_id == 501).first() is not None
        assert db_session.query(PlanSet).filter(PlanSet.upload_id == 502).first() is not None

    def test_empty_results_is_noop(self, db_session, test_project):
        from apex.backend.models.plan_set import PlanSet

        before_count = db_session.query(PlanSet).filter(PlanSet.project_id == test_project.id).count()
        self._run(db_session, test_project, {"results": []})
        after_count = db_session.query(PlanSet).filter(PlanSet.project_id == test_project.id).count()
        assert before_count == after_count


# ---------------------------------------------------------------------------
# Agent 4 adapter: adapt_agent4_takeoff_items
# ---------------------------------------------------------------------------


class TestAgent4TakeoffAdapter:
    def _run(self, db_session, project, result, run_log_id=None):
        from apex.backend.services.persistence_adapters import adapt_agent4_takeoff_items

        adapt_agent4_takeoff_items(db_session, project.id, result, run_log_id)

    def _make_result(self, recs):
        return {"recommendations": recs}

    def _rec(self, activity="Pour SOG", quantity=4500.0, unit="SF", confidence="medium"):
        return {
            "line_item_row": 1,
            "activity": activity,
            "quantity": quantity,
            "unit": unit,
            "confidence": confidence,
            "flag": "OK",
        }

    def test_creates_layer_and_items(self, db_session, test_project):
        from apex.backend.models.plan_takeoff import PlanTakeoffItem, TakeoffLayer

        result = self._make_result([self._rec(), self._rec("Footings", 200.0, "CY", "high")])
        self._run(db_session, test_project, result, run_log_id=42)

        layer = (
            db_session.query(TakeoffLayer)
            .filter(TakeoffLayer.project_id == test_project.id, TakeoffLayer.name == "Rate Intelligence")
            .first()
        )
        assert layer is not None

        items = db_session.query(PlanTakeoffItem).filter(PlanTakeoffItem.takeoff_layer_id == layer.id).all()
        assert len(items) == 2

        sog = next(i for i in items if i.label == "Pour SOG")
        assert sog.source_method == "ai"
        assert sog.review_status == "unreviewed"
        assert sog.quantity == pytest.approx(4500.0)
        assert sog.unit == "SF"
        assert sog.measurement_type == "area"
        assert sog.confidence == pytest.approx(0.65)
        assert sog.agent_run_log_id == 42

        ftg = next(i for i in items if i.label == "Footings")
        assert ftg.unit == "CY"
        assert ftg.measurement_type == "volume"
        assert ftg.confidence == pytest.approx(0.9)

    def test_each_run_creates_separate_layer(self, db_session, test_project):
        from apex.backend.models.plan_takeoff import TakeoffLayer

        result = self._make_result([self._rec()])
        self._run(db_session, test_project, result)
        self._run(db_session, test_project, result)

        layers = (
            db_session.query(TakeoffLayer)
            .filter(TakeoffLayer.project_id == test_project.id, TakeoffLayer.name == "Rate Intelligence")
            .all()
        )
        assert len(layers) == 2

    def test_confidence_mapping(self, db_session, test_project):
        from apex.backend.models.plan_takeoff import PlanTakeoffItem, TakeoffLayer

        result = self._make_result([
            self._rec("A", confidence="high"),
            self._rec("B", confidence="medium"),
            self._rec("C", confidence="low"),
            self._rec("D", confidence="none"),
        ])
        self._run(db_session, test_project, result)

        layer = (
            db_session.query(TakeoffLayer)
            .filter(TakeoffLayer.project_id == test_project.id)
            .order_by(TakeoffLayer.id.desc())
            .first()
        )
        items = {i.label: i for i in db_session.query(PlanTakeoffItem).filter(PlanTakeoffItem.takeoff_layer_id == layer.id).all()}
        assert items["A"].confidence == pytest.approx(0.9)
        assert items["B"].confidence == pytest.approx(0.65)
        assert items["C"].confidence == pytest.approx(0.3)
        assert items["D"].confidence is None

    def test_empty_recommendations_is_noop(self, db_session, test_project):
        from apex.backend.models.plan_takeoff import TakeoffLayer

        before = db_session.query(TakeoffLayer).filter(TakeoffLayer.project_id == test_project.id).count()
        self._run(db_session, test_project, {"recommendations": []})
        after = db_session.query(TakeoffLayer).filter(TakeoffLayer.project_id == test_project.id).count()
        assert before == after

    def test_unknown_unit_passthrough(self, db_session, test_project):
        from apex.backend.models.plan_takeoff import PlanTakeoffItem, TakeoffLayer

        result = self._make_result([self._rec(unit="GAL")])
        self._run(db_session, test_project, result)
        layer = (
            db_session.query(TakeoffLayer)
            .filter(TakeoffLayer.project_id == test_project.id)
            .order_by(TakeoffLayer.id.desc())
            .first()
        )
        item = db_session.query(PlanTakeoffItem).filter(PlanTakeoffItem.takeoff_layer_id == layer.id).first()
        assert item.unit == "GAL"
        assert item.measurement_type is None

    def test_all_items_start_unreviewed(self, db_session, test_project):
        from apex.backend.models.plan_takeoff import PlanTakeoffItem, TakeoffLayer

        result = self._make_result([self._rec() for _ in range(5)])
        self._run(db_session, test_project, result)
        layer = (
            db_session.query(TakeoffLayer)
            .filter(TakeoffLayer.project_id == test_project.id)
            .order_by(TakeoffLayer.id.desc())
            .first()
        )
        items = db_session.query(PlanTakeoffItem).filter(PlanTakeoffItem.takeoff_layer_id == layer.id).all()
        assert all(i.review_status == "unreviewed" for i in items)
        assert all(i.source_method == "ai" for i in items)
