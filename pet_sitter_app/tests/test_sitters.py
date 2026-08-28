from .conftest import auth_headers, register


def test_new_sitter_has_empty_profile(client):
    _, sitter = register(client, "sitter@example.com", "sitter", city="Denver")
    resp = client.get(f"/api/sitters/{sitter['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["hourly_rate"] == 0.0
    assert data["services"] == []
    assert data["review_count"] == 0


def test_sitter_updates_own_profile_and_appears_in_search(client):
    sitter_token, sitter = register(client, "sitter2@example.com", "sitter", city="Denver")

    resp = client.put(
        "/api/sitters/me",
        headers=auth_headers(sitter_token),
        json={
            "bio": "I love dogs!",
            "hourly_rate": 25,
            "years_experience": 3,
            "services": ["dog_walking", "boarding"],
            "accepted_pet_types": ["Dog", "Cat"],
            "city": "Denver",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["hourly_rate"] == 25
    assert data["accepted_pet_types"] == ["dog", "cat"]

    resp = client.get("/api/sitters", params={"city": "denver", "service": "dog_walking", "pet_type": "dog"})
    assert resp.status_code == 200
    results = resp.json()
    assert any(s["user"]["id"] == sitter["id"] for s in results)

    resp = client.get("/api/sitters", params={"max_rate": 10})
    assert all(s["hourly_rate"] <= 10 for s in resp.json())


def test_owner_cannot_update_sitter_profile(client):
    owner_token, _ = register(client, "owner2@example.com", "owner")
    resp = client.put(
        "/api/sitters/me",
        headers=auth_headers(owner_token),
        json={"bio": "nope", "hourly_rate": 10},
    )
    assert resp.status_code == 403
