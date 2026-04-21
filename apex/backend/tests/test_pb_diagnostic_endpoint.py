"""Tests for DATA-1.0.5 — PB diagnostic sampling endpoint."""

import pytest

from apex.backend.services.library.productivity_brain.models import PBLineItem, PBProject

URL = "/api/library/productivity-brain/diagnostic/sample"


@pytest.fixture(autouse=True)
def _clean_pb_tables(db_session):
    """Truncate PB tables before each test. The shared in-memory engine persists
    commits across tests; conftest's rollback doesn't undo them."""
    db_session.query(PBLineItem).delete()
    db_session.query(PBProject).delete()
    db_session.commit()
    yield


@pytest.fixture
def seeded_pb(db_session):
    """Two PB projects, 5 line items each. Shared activity names across projects.

    Project A: 5 items, all csi_code NULL, source_project='Flint'
    Project B: 5 items, first 2 with csi_code set, source_project='Bancroft'
    Three activity strings are shared between A and B (=> 5+5 rows but 7 distinct activities).
    """
    proj_a = PBProject(
        name="CCI CityGate Flint",
        source_file="CityGate_Master_Productivity_Rates.xlsx",
        file_hash="a" * 32,
        format_type="multi_project_rates",
        project_count=1,
        total_line_items=5,
    )
    proj_b = PBProject(
        name="CCI CityGate Bancroft",
        source_file="CityGate_Master_Productivity_Rates.xlsx",
        file_hash="b" * 32,
        format_type="multi_project_rates",
        project_count=1,
        total_line_items=5,
    )
    db_session.add_all([proj_a, proj_b])
    db_session.flush()

    shared = ["Field Layout Engineering/Survey", "Rough Grade", "Fine Grade"]
    a_only = ["Strip Topsoil", "Site Fencing"]
    b_only = ["Dewatering", "Erosion Control"]

    for act in shared + a_only:
        db_session.add(
            PBLineItem(
                project_id=proj_a.id,
                activity=act,
                unit="week",
                crew_trade="Laborer",
                production_rate=0.04,
                source_project="Flint",
            )
        )
    for i, act in enumerate(shared + b_only):
        db_session.add(
            PBLineItem(
                project_id=proj_b.id,
                activity=act,
                unit="week",
                crew_trade="Laborer",
                production_rate=0.05,
                csi_code="31 23 16" if i < 2 else None,
                source_project="Bancroft",
            )
        )
    db_session.commit()
    return proj_a, proj_b


class TestDiagnosticSample:
    def test_requires_auth(self, client):
        assert client.get(URL).status_code == 401

    def test_summary_counts(self, client, auth_headers, seeded_pb):
        res = client.get(URL, headers=auth_headers)
        assert res.status_code == 200
        body = res.json()
        assert body["success"] is True

        summary = body["data"]["summary"]
        assert summary["total_projects"] == 2
        assert summary["total_line_items"] == 10
        # shared(3) + a_only(2) + b_only(2) = 7 distinct activities
        assert summary["total_distinct_activities"] == 7
        # project B has csi_code set on 2 rows → 1 project non-null
        assert summary["projects_with_csi_code_nonnull"] == 1
        assert summary["projects_with_csi_code_null"] == 1

    def test_projects_rollup(self, client, auth_headers, seeded_pb):
        proj_a, proj_b = seeded_pb
        res = client.get(URL, headers=auth_headers)
        projects = res.json()["data"]["projects"]
        # ordered by id DESC
        assert [p["id"] for p in projects] == [proj_b.id, proj_a.id]

        by_id = {p["id"]: p for p in projects}
        assert by_id[proj_a.id]["project_name"] == "CCI CityGate Flint"
        assert by_id[proj_a.id]["source_project"] == "Flint"
        assert by_id[proj_a.id]["line_item_count"] == 5
        assert by_id[proj_a.id]["created_at"] is not None

        assert by_id[proj_b.id]["source_project"] == "Bancroft"
        assert by_id[proj_b.id]["line_item_count"] == 5

    def test_default_limit_five(self, client, auth_headers, seeded_pb):
        res = client.get(URL, headers=auth_headers)
        assert len(res.json()["data"]["sample_line_items"]) == 5

    def test_sample_includes_full_row(self, client, auth_headers, seeded_pb):
        res = client.get(URL, headers=auth_headers)
        row = res.json()["data"]["sample_line_items"][0]
        expected_keys = {
            "id", "project_id", "wbs_area", "activity", "quantity", "unit",
            "crew_trade", "production_rate", "labor_hours", "labor_cost_per_unit",
            "material_cost_per_unit", "equipment_cost", "sub_cost", "total_cost",
            "csi_code", "source_project",
        }
        assert set(row.keys()) == expected_keys

    def test_sample_order_is_id_desc(self, client, auth_headers, seeded_pb):
        res = client.get(URL + "?limit=50", headers=auth_headers)
        ids = [r["id"] for r in res.json()["data"]["sample_line_items"]]
        assert ids == sorted(ids, reverse=True)

    def test_project_id_filter(self, client, auth_headers, seeded_pb):
        proj_a, _ = seeded_pb
        res = client.get(f"{URL}?project_id={proj_a.id}&limit=50", headers=auth_headers)
        rows = res.json()["data"]["sample_line_items"]
        assert len(rows) == 5
        assert all(r["project_id"] == proj_a.id for r in rows)
        # summary is global, not filtered
        assert res.json()["data"]["summary"]["total_line_items"] == 10

    def test_limit_clamps_to_50(self, client, auth_headers, db_session):
        """Seed 60 line items in one project; limit=999 must return at most 50."""
        proj = PBProject(
            name="Big Project",
            source_file="big.xlsx",
            file_hash="c" * 32,
            format_type="multi_project_rates",
        )
        db_session.add(proj)
        db_session.flush()
        for i in range(60):
            db_session.add(
                PBLineItem(
                    project_id=proj.id,
                    activity=f"activity-{i}",
                    unit="ea",
                    production_rate=1.0,
                )
            )
        db_session.commit()

        res = client.get(f"{URL}?limit=999", headers=auth_headers)
        assert res.status_code == 200
        assert len(res.json()["data"]["sample_line_items"]) == 50

    def test_empty_state(self, client, auth_headers):
        res = client.get(URL, headers=auth_headers)
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["summary"]["total_projects"] == 0
        assert data["summary"]["total_line_items"] == 0
        assert data["summary"]["total_distinct_activities"] == 0
        assert data["summary"]["projects_with_csi_code_nonnull"] == 0
        assert data["summary"]["projects_with_csi_code_null"] == 0
        assert data["projects"] == []
        assert data["sample_line_items"] == []

    def test_limit_below_one_rejected(self, client, auth_headers):
        res = client.get(f"{URL}?limit=0", headers=auth_headers)
        assert res.status_code == 422
