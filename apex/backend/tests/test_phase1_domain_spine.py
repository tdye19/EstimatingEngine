"""Phase 1 domain spine integration tests.

Covers:
- Project creation with trade_focus / scope_type / client_name
- ScopePackage CRUD
- PlanSet + PlanSheet lifecycle
- TakeoffLayer + PlanTakeoffItem lifecycle with review state transitions
"""

import pytest


# ---------------------------------------------------------------------------
# Projects — new Phase 1 fields
# ---------------------------------------------------------------------------


class TestProjectPhase1Fields:
    def test_create_project_with_trade_focus(self, client, auth_headers):
        res = client.post(
            "/api/projects",
            json={
                "name": "Concrete Bid",
                "project_number": "CB-001",
                "trade_focus": "concrete",
                "scope_type": "bid_package",
                "client_name": "Christman Constructors",
            },
            headers=auth_headers,
        )
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["trade_focus"] == "concrete"
        assert data["scope_type"] == "bid_package"
        assert data["client_name"] == "Christman Constructors"

    def test_update_project_trade_focus(self, client, auth_headers, test_project):
        res = client.put(
            f"/api/projects/{test_project.id}",
            json={"trade_focus": "earthwork", "client_name": "Acme GC"},
            headers=auth_headers,
        )
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["trade_focus"] == "earthwork"
        assert data["client_name"] == "Acme GC"

    def test_get_project_exposes_phase1_fields(self, client, auth_headers, test_project):
        res = client.get(f"/api/projects/{test_project.id}", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()["data"]
        # Fields exist in response even if null
        assert "trade_focus" in data
        assert "scope_type" in data
        assert "client_name" in data


# ---------------------------------------------------------------------------
# ScopePackage
# ---------------------------------------------------------------------------


class TestScopePackage:
    def test_create_scope_package(self, client, auth_headers, test_project):
        res = client.post(
            f"/api/projects/{test_project.id}/scope-packages",
            json={
                "name": "Foundations & SOG",
                "code": "03-FOUND",
                "trade_focus": "concrete",
                "csi_division": "03",
            },
            headers=auth_headers,
        )
        assert res.status_code == 201
        pkg = res.json()
        assert pkg["name"] == "Foundations & SOG"
        assert pkg["project_id"] == test_project.id
        assert pkg["status"] == "active"
        return pkg["id"]

    def test_list_scope_packages(self, client, auth_headers, test_project):
        # Create two packages
        for i in range(2):
            client.post(
                f"/api/projects/{test_project.id}/scope-packages",
                json={"name": f"Package {i}", "trade_focus": "concrete"},
                headers=auth_headers,
            )
        res = client.get(f"/api/projects/{test_project.id}/scope-packages", headers=auth_headers)
        assert res.status_code == 200
        pkgs = res.json()
        assert len(pkgs) >= 2

    def test_update_scope_package(self, client, auth_headers, test_project):
        create = client.post(
            f"/api/projects/{test_project.id}/scope-packages",
            json={"name": "Initial Name"},
            headers=auth_headers,
        )
        pkg_id = create.json()["id"]
        res = client.patch(
            f"/api/projects/{test_project.id}/scope-packages/{pkg_id}",
            json={"name": "Updated Name", "status": "inactive"},
            headers=auth_headers,
        )
        assert res.status_code == 200
        assert res.json()["name"] == "Updated Name"
        assert res.json()["status"] == "inactive"

    def test_delete_scope_package(self, client, auth_headers, test_project):
        create = client.post(
            f"/api/projects/{test_project.id}/scope-packages",
            json={"name": "To Delete"},
            headers=auth_headers,
        )
        pkg_id = create.json()["id"]
        res = client.delete(
            f"/api/projects/{test_project.id}/scope-packages/{pkg_id}",
            headers=auth_headers,
        )
        assert res.status_code == 204
        # Soft-deleted — should not appear in list
        listing = client.get(
            f"/api/projects/{test_project.id}/scope-packages",
            headers=auth_headers,
        )
        ids = [p["id"] for p in listing.json()]
        assert pkg_id not in ids

    def test_scope_package_requires_auth(self, client, test_project):
        res = client.get(f"/api/projects/{test_project.id}/scope-packages")
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# PlanSet + PlanSheet
# ---------------------------------------------------------------------------


class TestPlanSetAndSheets:
    def _create_plan_set(self, client, auth_headers, project_id):
        res = client.post(
            f"/api/projects/{project_id}/plan-sets",
            json={"version_label": "SD-01", "source_filename": "drawings.pdf"},
            headers=auth_headers,
        )
        assert res.status_code == 201
        return res.json()

    def test_create_plan_set(self, client, auth_headers, test_project):
        ps = self._create_plan_set(client, auth_headers, test_project.id)
        assert ps["project_id"] == test_project.id
        assert ps["version_label"] == "SD-01"
        assert ps["status"] == "queued"
        assert ps["sheet_count"] == 0

    def test_list_plan_sets(self, client, auth_headers, test_project):
        self._create_plan_set(client, auth_headers, test_project.id)
        res = client.get(f"/api/projects/{test_project.id}/plan-sets", headers=auth_headers)
        assert res.status_code == 200
        assert len(res.json()) >= 1

    def test_get_plan_set(self, client, auth_headers, test_project):
        ps = self._create_plan_set(client, auth_headers, test_project.id)
        res = client.get(f"/api/plan-sets/{ps['id']}", headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["id"] == ps["id"]

    def test_plan_sheets_empty_initially(self, client, auth_headers, test_project):
        ps = self._create_plan_set(client, auth_headers, test_project.id)
        res = client.get(f"/api/plan-sets/{ps['id']}/sheets", headers=auth_headers)
        assert res.status_code == 200
        assert res.json() == []

    def test_plan_set_404(self, client, auth_headers):
        res = client.get("/api/plan-sets/99999", headers=auth_headers)
        assert res.status_code == 404

    def test_plan_sheet_written_directly_and_patchable(self, client, auth_headers, test_project, db_session):
        """Simulate ingestion agent writing a PlanSheet, then confirm PATCH works."""
        from apex.backend.models.plan_set import PlanSet, PlanSheet

        plan_set = PlanSet(
            project_id=test_project.id,
            version_label="v1",
            source_filename="test.pdf",
            sheet_count=1,
            status="ready",
        )
        db_session.add(plan_set)
        db_session.flush()

        sheet = PlanSheet(
            project_id=test_project.id,
            plan_set_id=plan_set.id,
            page_index=0,
            sheet_number="S-101",
            sheet_name="Foundation Plan",
            discipline="S",
        )
        db_session.add(sheet)
        db_session.commit()

        # Retrieve via API
        res = client.get(f"/api/plan-sets/{plan_set.id}/sheets", headers=auth_headers)
        assert res.status_code == 200
        sheets = res.json()
        assert len(sheets) == 1
        assert sheets[0]["sheet_number"] == "S-101"

        sheet_id = sheets[0]["id"]
        # Confirm scale via PATCH
        patch = client.patch(
            f"/api/plan-sheets/{sheet_id}",
            json={"confirmed_scale": '1"=20\''},
            headers=auth_headers,
        )
        assert patch.status_code == 200
        assert patch.json()["confirmed_scale"] == '1"=20\''

    def test_sheet_region_create_and_list(self, client, auth_headers, test_project, db_session):
        from apex.backend.models.plan_set import PlanSet, PlanSheet

        plan_set = PlanSet(
            project_id=test_project.id, version_label="v2", source_filename="r.pdf", sheet_count=1, status="ready"
        )
        db_session.add(plan_set)
        db_session.flush()
        sheet = PlanSheet(
            project_id=test_project.id, plan_set_id=plan_set.id, page_index=0
        )
        db_session.add(sheet)
        db_session.commit()

        res = client.post(
            f"/api/plan-sheets/{sheet.id}/regions",
            json={"region_type": "callout", "label": "TYP FOOTING", "source_method": "ai"},
            headers=auth_headers,
        )
        assert res.status_code == 201
        region = res.json()
        assert region["label"] == "TYP FOOTING"
        assert region["review_status"] == "pending"

        listing = client.get(f"/api/plan-sheets/{sheet.id}/regions", headers=auth_headers)
        assert listing.status_code == 200
        assert len(listing.json()) == 1


# ---------------------------------------------------------------------------
# TakeoffLayer + PlanTakeoffItem
# ---------------------------------------------------------------------------


class TestTakeoffLayerAndItems:
    def _seed_sheet(self, db_session, project_id):
        from apex.backend.models.plan_set import PlanSet, PlanSheet

        ps = PlanSet(project_id=project_id, version_label="v1", source_filename="x.pdf", sheet_count=1, status="ready")
        db_session.add(ps)
        db_session.flush()
        sheet = PlanSheet(project_id=project_id, plan_set_id=ps.id, page_index=0)
        db_session.add(sheet)
        db_session.commit()
        return sheet

    def test_create_takeoff_layer_on_sheet(self, client, auth_headers, test_project, db_session):
        sheet = self._seed_sheet(db_session, test_project.id)
        res = client.post(
            f"/api/plan-sheets/{sheet.id}/takeoff-layers",
            json={"name": "Slab on Grade", "layer_type": "area", "trade_focus": "concrete"},
            headers=auth_headers,
        )
        assert res.status_code == 201
        layer = res.json()
        assert layer["name"] == "Slab on Grade"
        assert layer["project_id"] == test_project.id
        assert layer["plan_sheet_id"] == sheet.id

    def test_list_takeoff_layers(self, client, auth_headers, test_project, db_session):
        sheet = self._seed_sheet(db_session, test_project.id)
        client.post(
            f"/api/plan-sheets/{sheet.id}/takeoff-layers",
            json={"name": "Footings"},
            headers=auth_headers,
        )
        res = client.get(f"/api/projects/{test_project.id}/takeoff-layers", headers=auth_headers)
        assert res.status_code == 200
        assert any(l["name"] == "Footings" for l in res.json())

    def test_create_takeoff_item_manual(self, client, auth_headers, test_project, db_session):
        sheet = self._seed_sheet(db_session, test_project.id)
        layer_res = client.post(
            f"/api/plan-sheets/{sheet.id}/takeoff-layers",
            json={"name": "SOG Layer", "layer_type": "area"},
            headers=auth_headers,
        )
        layer_id = layer_res.json()["id"]

        res = client.post(
            f"/api/takeoff-layers/{layer_id}/items",
            json={
                "label": "SOG Area 1",
                "measurement_type": "area",
                "quantity": 4500.0,
                "unit": "SF",
                "source_method": "manual",
                "geometry_geojson": '{"type":"Polygon","coordinates":[[[0,0],[100,0],[100,45],[0,45],[0,0]]]}',
            },
            headers=auth_headers,
        )
        assert res.status_code == 201
        item = res.json()
        assert item["quantity"] == 4500.0
        assert item["unit"] == "SF"
        assert item["review_status"] == "unreviewed"
        assert item["source_method"] == "manual"
        return item["id"], layer_id

    def test_confirm_takeoff_item(self, client, auth_headers, test_project, db_session):
        item_id, _ = self.test_create_takeoff_item_manual(client, auth_headers, test_project, db_session)
        res = client.post(f"/api/takeoff-items/{item_id}/confirm", headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["review_status"] == "confirmed"

    def test_reject_takeoff_item(self, client, auth_headers, test_project, db_session):
        item_id, _ = self.test_create_takeoff_item_manual(client, auth_headers, test_project, db_session)
        res = client.post(f"/api/takeoff-items/{item_id}/reject", headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["review_status"] == "rejected"

    def test_patch_takeoff_item_quantity(self, client, auth_headers, test_project, db_session):
        item_id, _ = self.test_create_takeoff_item_manual(client, auth_headers, test_project, db_session)
        res = client.patch(
            f"/api/takeoff-items/{item_id}",
            json={"quantity": 5200.0, "review_status": "changed"},
            headers=auth_headers,
        )
        assert res.status_code == 200
        assert res.json()["quantity"] == 5200.0
        assert res.json()["review_status"] == "changed"

    def test_list_takeoff_items_with_filter(self, client, auth_headers, test_project, db_session):
        sheet = self._seed_sheet(db_session, test_project.id)
        layer_res = client.post(
            f"/api/plan-sheets/{sheet.id}/takeoff-layers",
            json={"name": "Filter Test Layer"},
            headers=auth_headers,
        )
        layer_id = layer_res.json()["id"]
        for _ in range(3):
            client.post(
                f"/api/takeoff-layers/{layer_id}/items",
                json={"quantity": 100.0, "unit": "SF", "source_method": "ai"},
                headers=auth_headers,
            )
        all_items = client.get(
            f"/api/projects/{test_project.id}/takeoff-items",
            headers=auth_headers,
        )
        assert all_items.status_code == 200
        by_layer = client.get(
            f"/api/projects/{test_project.id}/takeoff-items?layer_id={layer_id}",
            headers=auth_headers,
        )
        assert by_layer.status_code == 200
        assert len(by_layer.json()) == 3

    def test_ai_item_starts_unreviewed(self, client, auth_headers, test_project, db_session):
        sheet = self._seed_sheet(db_session, test_project.id)
        layer_res = client.post(
            f"/api/plan-sheets/{sheet.id}/takeoff-layers",
            json={"name": "AI Layer"},
            headers=auth_headers,
        )
        layer_id = layer_res.json()["id"]
        res = client.post(
            f"/api/takeoff-layers/{layer_id}/items",
            json={"source_method": "ai", "quantity": 800.0, "unit": "LF", "confidence": 0.72},
            headers=auth_headers,
        )
        assert res.status_code == 201
        item = res.json()
        assert item["source_method"] == "ai"
        assert item["review_status"] == "unreviewed"
        assert item["confidence"] == pytest.approx(0.72)
