"""Tests for authentication endpoints."""


class TestRegister:
    def test_register_success(self, client):
        res = client.post(
            "/api/auth/register",
            json={
                "email": "new@example.com",
                "password": "newpass123",
                "full_name": "New User",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["data"]["email"] == "new@example.com"

    def test_register_duplicate_email(self, client, test_user):
        res = client.post(
            "/api/auth/register",
            json={
                "email": test_user.email,
                "password": "anypass",
                "full_name": "Duplicate",
            },
        )
        assert res.status_code == 400

    def test_register_missing_fields(self, client):
        res = client.post("/api/auth/register", json={})
        assert res.status_code == 422


class TestLogin:
    def test_login_success(self, client, test_user):
        res = client.post(
            "/api/auth/login",
            json={
                "email": test_user.email,
                "password": "testpass123",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data

    def test_login_wrong_password(self, client, test_user):
        res = client.post(
            "/api/auth/login",
            json={
                "email": test_user.email,
                "password": "wrongpass",
            },
        )
        assert res.status_code == 401

    def test_login_nonexistent_user(self, client):
        res = client.post(
            "/api/auth/login",
            json={
                "email": "nobody@example.com",
                "password": "anything",
            },
        )
        assert res.status_code == 401


class TestRegisterPrivilegeEscalation:
    def test_role_field_ignored(self, client):
        """role='admin' in body is silently ignored; created user gets estimator."""
        res = client.post(
            "/api/auth/register",
            json={
                "email": "escalate@example.com",
                "password": "pass123",
                "full_name": "Escalator",
                "role": "admin",
            },
        )
        assert res.status_code == 200
        assert res.json()["data"]["role"] == "estimator"

    def test_organization_id_ignored(self, client):
        """organization_id in body is silently ignored; created user gets None."""
        res = client.post(
            "/api/auth/register",
            json={
                "email": "orgtest@example.com",
                "password": "pass123",
                "full_name": "OrgTest",
                "organization_id": 999,
            },
        )
        assert res.status_code == 200
        assert res.json()["data"]["organization_id"] is None


class TestAdminCreate:
    def test_no_auth_401(self, client):
        res = client.post(
            "/api/users/admin/create",
            json={"email": "x@example.com", "password": "pass", "full_name": "X", "role": "admin"},
        )
        assert res.status_code == 401

    def test_estimator_auth_403(self, client, auth_headers):
        res = client.post(
            "/api/users/admin/create",
            json={"email": "x@example.com", "password": "pass", "full_name": "X", "role": "admin"},
            headers=auth_headers,
        )
        assert res.status_code == 403

    def test_admin_creates_admin_role(self, client, admin_headers):
        res = client.post(
            "/api/users/admin/create",
            json={
                "email": "created-admin@example.com",
                "password": "pass123",
                "full_name": "Created Admin",
                "role": "admin",
            },
            headers=admin_headers,
        )
        assert res.status_code == 200
        assert res.json()["data"]["role"] == "admin"

    def test_invalid_role_422(self, client, admin_headers):
        res = client.post(
            "/api/users/admin/create",
            json={
                "email": "hacker@example.com",
                "password": "pass123",
                "full_name": "Hacker",
                "role": "hacker",
            },
            headers=admin_headers,
        )
        assert res.status_code == 422

    def test_duplicate_email_400(self, client, admin_headers, admin_user):
        res = client.post(
            "/api/users/admin/create",
            json={
                "email": admin_user.email,
                "password": "pass123",
                "full_name": "Duplicate",
                "role": "estimator",
            },
            headers=admin_headers,
        )
        assert res.status_code == 400


class TestMe:
    def test_me_authenticated(self, client, test_user, auth_headers):
        res = client.get("/api/auth/me", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["data"]["email"] == test_user.email

    def test_me_unauthenticated(self, client):
        res = client.get("/api/auth/me")
        assert res.status_code == 401

    def test_me_invalid_token(self, client):
        res = client.get("/api/auth/me", headers={"Authorization": "Bearer invalid"})
        assert res.status_code == 401
