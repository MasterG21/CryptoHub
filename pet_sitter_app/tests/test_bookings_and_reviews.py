from .conftest import auth_headers, register


def _setup_owner_and_sitter(client):
    owner_token, owner = register(client, "owner3@example.com", "owner", city="Seattle")
    sitter_token, sitter = register(client, "sitter3@example.com", "sitter", city="Seattle")
    client.put(
        "/api/sitters/me",
        headers=auth_headers(sitter_token),
        json={"bio": "Pro sitter", "hourly_rate": 20, "years_experience": 2, "services": ["boarding"], "accepted_pet_types": ["dog"]},
    )
    pet_resp = client.post(
        "/api/pets",
        headers=auth_headers(owner_token),
        json={"name": "Rex", "species": "dog", "breed": "Lab", "notes": "Friendly"},
    )
    assert pet_resp.status_code == 201
    pet = pet_resp.json()
    return owner_token, owner, sitter_token, sitter, pet


def test_full_booking_lifecycle_with_messages_and_review(client):
    owner_token, owner, sitter_token, sitter, pet = _setup_owner_and_sitter(client)

    resp = client.post(
        "/api/bookings",
        headers=auth_headers(owner_token),
        json={
            "sitter_id": sitter["id"],
            "pet_id": pet["id"],
            "service_type": "boarding",
            "start_date": "2026-09-01",
            "end_date": "2026-09-05",
            "notes": "Please walk twice a day",
        },
    )
    assert resp.status_code == 201, resp.text
    booking = resp.json()
    assert booking["status"] == "pending"

    # Owner cannot accept their own request
    resp = client.patch(
        f"/api/bookings/{booking['id']}", headers=auth_headers(owner_token), json={"status": "accepted"}
    )
    assert resp.status_code == 403

    resp = client.patch(
        f"/api/bookings/{booking['id']}", headers=auth_headers(sitter_token), json={"status": "accepted"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"

    # Messaging back and forth
    resp = client.post(
        f"/api/bookings/{booking['id']}/messages", headers=auth_headers(owner_token), json={"body": "Thanks!"}
    )
    assert resp.status_code == 201
    resp = client.post(
        f"/api/bookings/{booking['id']}/messages", headers=auth_headers(sitter_token), json={"body": "See you then."}
    )
    assert resp.status_code == 201

    resp = client.get(f"/api/bookings/{booking['id']}/messages", headers=auth_headers(owner_token))
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    # Reviewing before completion is rejected
    resp = client.post(
        f"/api/bookings/{booking['id']}/review", headers=auth_headers(owner_token), json={"rating": 5}
    )
    assert resp.status_code == 400

    resp = client.patch(
        f"/api/bookings/{booking['id']}", headers=auth_headers(sitter_token), json={"status": "completed"}
    )
    assert resp.status_code == 200

    resp = client.post(
        f"/api/bookings/{booking['id']}/review",
        headers=auth_headers(owner_token),
        json={"rating": 5, "comment": "Great sitter!"},
    )
    assert resp.status_code == 201

    # Duplicate review rejected
    resp = client.post(
        f"/api/bookings/{booking['id']}/review", headers=auth_headers(owner_token), json={"rating": 4}
    )
    assert resp.status_code == 400

    # Sitter profile now reflects the rating
    resp = client.get(f"/api/sitters/{sitter['id']}")
    data = resp.json()
    assert data["average_rating"] == 5.0
    assert data["review_count"] == 1


def test_sitter_can_decline_booking(client):
    owner_token, owner, sitter_token, sitter, pet = _setup_owner_and_sitter(client)
    resp = client.post(
        "/api/bookings",
        headers=auth_headers(owner_token),
        json={
            "sitter_id": sitter["id"],
            "service_type": "dog_walking",
            "start_date": "2026-09-01",
            "end_date": "2026-09-01",
        },
    )
    booking = resp.json()
    resp = client.patch(
        f"/api/bookings/{booking['id']}", headers=auth_headers(sitter_token), json={"status": "declined"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "declined"

    # No further transitions allowed once declined
    resp = client.patch(
        f"/api/bookings/{booking['id']}", headers=auth_headers(sitter_token), json={"status": "accepted"}
    )
    assert resp.status_code == 400


def test_stranger_cannot_view_booking(client):
    owner_token, owner, sitter_token, sitter, pet = _setup_owner_and_sitter(client)
    stranger_token, _ = register(client, "stranger@example.com", "owner")

    resp = client.post(
        "/api/bookings",
        headers=auth_headers(owner_token),
        json={
            "sitter_id": sitter["id"],
            "service_type": "dog_walking",
            "start_date": "2026-09-01",
            "end_date": "2026-09-01",
        },
    )
    booking = resp.json()

    resp = client.get(f"/api/bookings/{booking['id']}", headers=auth_headers(stranger_token))
    assert resp.status_code == 403


def test_end_date_before_start_date_rejected(client):
    owner_token, owner, sitter_token, sitter, pet = _setup_owner_and_sitter(client)
    resp = client.post(
        "/api/bookings",
        headers=auth_headers(owner_token),
        json={
            "sitter_id": sitter["id"],
            "service_type": "dog_walking",
            "start_date": "2026-09-05",
            "end_date": "2026-09-01",
        },
    )
    assert resp.status_code == 400
