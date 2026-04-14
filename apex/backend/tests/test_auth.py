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
