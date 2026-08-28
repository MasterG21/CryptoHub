from .conftest import auth_headers, register


def test_report_a_message(client):
    owner_token, owner = register(client, "owner4@example.com", "owner")
    sitter_token, sitter = register(client, "sitter4@example.com", "sitter")
    client.put(
        "/api/sitters/me",
        headers=auth_headers(sitter_token),
        json={"bio": "x", "hourly_rate": 10, "years_experience": 1, "services": [], "accepted_pet_types": []},
    )
    booking = client.post(
        "/api/bookings",
        headers=auth_headers(owner_token),
        json={
            "sitter_id": sitter["id"],
            "service_type": "dog_walking",
            "start_date": "2026-09-01",
            "end_date": "2026-09-01",
        },
    ).json()
    message = client.post(
        f"/api/bookings/{booking['id']}/messages", headers=auth_headers(sitter_token), json={"body": "rude message"}
    ).json()

    resp = client.post(
        "/api/reports",
        headers=auth_headers(owner_token),
        json={"target_type": "message", "target_id": message["id"], "reason": "harassment", "details": "was rude"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "open"

    resp = client.get("/api/reports/me", headers=auth_headers(owner_token))
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_report_requires_existing_target(client):
    owner_token, _ = register(client, "owner5@example.com", "owner")
    resp = client.post(
        "/api/reports",
        headers=auth_headers(owner_token),
        json={"target_type": "message", "target_id": 999999, "reason": "spam"},
    )
    assert resp.status_code == 404


def test_report_requires_auth(client):
    resp = client.post("/api/reports", json={"target_type": "user", "target_id": 1, "reason": "spam"})
    assert resp.status_code == 401
