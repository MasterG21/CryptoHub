from .conftest import auth_headers, register


def test_register_and_login(client):
    token, user = register(client, "owner@example.com", "owner", city="Austin")
    assert user["role"] == "owner"
    assert token

    resp = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "supersecret1"})
    assert resp.status_code == 200
    login_token = resp.json()["access_token"]

    resp = client.get("/api/auth/me", headers=auth_headers(login_token))
    assert resp.status_code == 200
    assert resp.json()["email"] == "owner@example.com"


def test_login_wrong_password(client):
    register(client, "a@example.com", "owner")
    resp = client.post("/api/auth/login", json={"email": "a@example.com", "password": "wrong-password"})
    assert resp.status_code == 401


def test_duplicate_email_rejected(client):
    register(client, "dup@example.com", "owner")
    resp = client.post(
        "/api/auth/register",
        json={"email": "dup@example.com", "password": "supersecret1", "full_name": "D", "role": "owner"},
    )
    assert resp.status_code == 400


def test_me_requires_auth(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401
