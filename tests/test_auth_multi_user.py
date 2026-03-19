from __future__ import annotations


def _bootstrap_admin(client) -> dict[str, object]:
    response = client.post(
        "/api/v1/auth/bootstrap-admin",
        json={
            "email": "admin@example.com",
            "password": "supersecret123",
            "display_name": "Admin",
        },
    )
    assert response.status_code == 200
    return response.json()


def _issue_token(client, *, email: str, password: str, name: str) -> str:
    login_response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login_response.status_code == 200
    token_response = client.post("/api/v1/auth/tokens", json={"name": name})
    assert token_response.status_code == 200
    plain_text_token = token_response.json()["plain_text_token"]
    client.post("/api/v1/auth/logout")
    return plain_text_token


def test_multi_user_token_flow_and_query_isolation(client):
    admin_payload = _bootstrap_admin(client)
    admin_id = admin_payload["user"]["id"]

    admin_token_response = client.post("/api/v1/auth/tokens", json={"name": "admin-cli"})
    assert admin_token_response.status_code == 200
    admin_token = admin_token_response.json()["plain_text_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    member_a_response = client.post(
        "/api/v1/auth/users",
        json={
            "email": "alice@example.com",
            "password": "alicepass123",
            "display_name": "Alice",
            "role": "member",
        },
    )
    assert member_a_response.status_code == 200

    member_b_response = client.post(
        "/api/v1/auth/users",
        json={
            "email": "bob@example.com",
            "password": "bobpass12345",
            "display_name": "Bob",
            "role": "member",
        },
    )
    assert member_b_response.status_code == 200

    member_a_token = _issue_token(client, email="alice@example.com", password="alicepass123", name="alice-cli")
    member_b_token = _issue_token(client, email="bob@example.com", password="bobpass12345", name="bob-cli")
    member_a_headers = {"Authorization": f"Bearer {member_a_token}"}
    member_b_headers = {"Authorization": f"Bearer {member_b_token}"}

    me_response = client.get("/api/v1/auth/me", headers=member_a_headers)
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "alice@example.com"

    member_a_query = client.post(
        "/api/v1/queries",
        json={"theme": "Corpus Alice", "keywords": ["alice", "europe"]},
        headers=member_a_headers,
    )
    assert member_a_query.status_code == 200
    query_a_id = member_a_query.json()["id"]
    assert member_a_query.json()["owner_user_id"] == member_a_response.json()["id"]

    member_b_query = client.post(
        "/api/v1/queries",
        json={"theme": "Corpus Bob", "keywords": ["bob", "france"]},
        headers=member_b_headers,
    )
    assert member_b_query.status_code == 200
    query_b_id = member_b_query.json()["id"]
    assert member_b_query.json()["owner_user_id"] == member_b_response.json()["id"]

    forbidden = client.get(f"/api/v1/queries/{query_a_id}", headers=member_b_headers)
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "forbidden"

    admin_can_read_a = client.get(f"/api/v1/queries/{query_a_id}", headers=admin_headers)
    admin_can_read_b = client.get(f"/api/v1/queries/{query_b_id}", headers=admin_headers)
    assert admin_can_read_a.status_code == 200
    assert admin_can_read_b.status_code == 200

    resources_a = client.get("/api/v1/resources", headers=member_a_headers)
    assert resources_a.status_code == 200
    resource_ids_a = {resource["resource_id"] for resource in resources_a.json()}
    assert f"query:{query_a_id}" in resource_ids_a
    assert f"query:{query_b_id}" not in resource_ids_a

    resources_admin = client.get("/api/v1/resources", headers=admin_headers)
    assert resources_admin.status_code == 200
    resource_ids_admin = {resource["resource_id"] for resource in resources_admin.json()}
    assert f"query:{query_a_id}" in resource_ids_admin
    assert f"query:{query_b_id}" in resource_ids_admin

    users_response = client.get("/api/v1/auth/users", headers=member_a_headers)
    assert users_response.status_code == 403

    deactivate_last_admin = client.post(f"/api/v1/auth/users/{admin_id}:deactivate", headers=admin_headers)
    assert deactivate_last_admin.status_code == 409
