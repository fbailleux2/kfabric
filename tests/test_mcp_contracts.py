from __future__ import annotations


def _bootstrap_admin(client) -> None:
    response = client.post(
        "/api/v1/auth/bootstrap-admin",
        json={
            "email": "admin@example.com",
            "password": "supersecret123",
            "display_name": "Admin",
        },
    )
    assert response.status_code == 200


def test_mcp_rest_catalog_and_tool_invocation(client):
    _bootstrap_admin(client)
    create_query = client.post(
        "/api/v1/queries",
        json={"theme": "Corpus juridique", "keywords": ["reglementation", "europe"]},
    )
    query_id = create_query.json()["id"]

    session_response = client.post(
        "/api/v1/mcp/sessions",
        json={
            "client_name": "pytest",
            "client_version": "1.0.0",
            "requested_capabilities": {"tools": True, "resources": True, "prompts": True},
        },
    )
    assert session_response.status_code == 200
    session_id = session_response.json()["session_id"]

    tools_response = client.get("/api/v1/tools")
    assert tools_response.status_code == 200
    tool_names = {tool["name"] for tool in tools_response.json()}
    assert "discover_documents" in tool_names

    invoke_response = client.post(
        "/api/v1/tools/discover_documents:invoke",
        json={"session_id": session_id, "arguments": {"query_id": query_id}},
    )
    assert invoke_response.status_code == 200
    assert invoke_response.json()["status"] == "succeeded"

    prompts_response = client.get("/api/v1/prompts")
    assert prompts_response.status_code == 200
    assert any(prompt["name"] == "summarize_document" for prompt in prompts_response.json())

    resources_response = client.get("/api/v1/resources")
    assert resources_response.status_code == 200
    assert any(resource["resource_id"].startswith("query:") for resource in resources_response.json())
