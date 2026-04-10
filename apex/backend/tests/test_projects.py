"""Tests for project CRUD endpoints."""


class TestProjectCRUD:
    def test_create_project(self, client, auth_headers):
        res = client.post("/api/projects", json={
            "name": "New Project",
            "project_number": "NP-001",
        }, headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["data"]["name"] == "New Project"

    def test_list_projects(self, client, auth_headers, test_project):
        res = client.get("/api/projects", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)

    def test_get_project(self, client, auth_headers, test_project):
        res = client.get(f"/api/projects/{test_project.id}", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["data"]["name"] == test_project.name

    def test_update_project(self, client, auth_headers, test_project):
        res = client.put(f"/api/projects/{test_project.id}", json={
            "name": "Updated Name",
        }, headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True

    def test_delete_project(self, client, auth_headers, test_project):
        res = client.delete(f"/api/projects/{test_project.id}", headers=auth_headers)
        assert res.status_code == 204

    def test_unauthenticated_access(self, client):
        res = client.get("/api/projects")
        assert res.status_code == 401
