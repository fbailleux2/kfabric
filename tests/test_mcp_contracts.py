from __future__ import annotations

import time


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
    assert "create_query" in tool_names
    assert "collect_candidate" in tool_names
    assert "consolidate_fragments" in tool_names
    assert "build_corpus" in tool_names
    assert "prepare_index" in tool_names
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


def test_mcp_async_tool_invocation_and_status_polling(client):
    _bootstrap_admin(client)
    create_query = client.post(
        "/api/v1/queries",
        json={"theme": "Corpus async", "keywords": ["async", "pipeline"]},
    )
    query_id = create_query.json()["id"]

    invoke_response = client.post(
        "/api/v1/tools/discover_documents:invoke",
        json={"arguments": {"query_id": query_id}, "async": True},
    )
    assert invoke_response.status_code == 200
    run_payload = invoke_response.json()
    assert run_payload["status"] in {"queued", "running", "succeeded"}

    final_payload = run_payload
    deadline = time.time() + 5
    while final_payload["status"] not in {"succeeded", "failed"} and time.time() < deadline:
        time.sleep(0.05)
        poll_response = client.get(f"/api/v1/tool-runs/{run_payload['run_id']}")
        assert poll_response.status_code == 200
        final_payload = poll_response.json()

    assert final_payload["status"] == "succeeded"
    assert final_payload["output"]["result"][0]["title"]


def test_mcp_async_tool_invocation_fails_when_broker_dispatch_fails(client, monkeypatch):
    _bootstrap_admin(client)
    create_query = client.post(
        "/api/v1/queries",
        json={"theme": "Corpus broker", "keywords": ["broker", "failure"]},
    )
    query_id = create_query.json()["id"]

    from kfabric.workers import tasks as tasks_module

    def fail_delay(*args, **kwargs):
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr(tasks_module.run_tool, "delay", fail_delay)

    invoke_response = client.post(
        "/api/v1/tools/discover_documents:invoke",
        json={"arguments": {"query_id": query_id}, "async": True},
    )
    assert invoke_response.status_code == 200
    payload = invoke_response.json()
    assert payload["status"] == "failed"
    assert payload["error"] is not None
    assert "broker dispatch failed" in payload["error"]["message"].lower()
