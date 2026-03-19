from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from kfabric.api.serializers import serialize_prompt, serialize_resource, serialize_tool_schema
from kfabric.config import get_settings
from kfabric.infra.db import get_session_factory, init_db
from kfabric.mcp.registry import (
    get_capabilities,
    get_prompt_definition,
    get_prompt_definitions,
    get_resource_definition,
    get_resource_definitions,
    get_tool_definition,
    get_tool_definitions,
    invoke_tool,
)


def _db_session():
    settings = get_settings()
    init_db(settings)
    return get_session_factory(settings.database_url)()


async def _fallback_stdio_loop() -> None:
    settings = get_settings()
    session = _db_session()
    try:
        for raw_line in sys.stdin:
            line = raw_line.strip()
            if not line:
                continue
            request = json.loads(line)
            action = request.get("action")
            payload = request.get("payload", {})
            response: dict[str, Any]
            try:
                if action == "capabilities":
                    response = {"result": get_capabilities()}
                elif action == "tools/list":
                    response = {"result": [serialize_tool_schema(tool).model_dump() for tool in get_tool_definitions()]}
                elif action == "tools/call":
                    run = invoke_tool(session, settings, payload["tool_name"], payload.get("arguments", {}), payload.get("session_id"))
                    response = {"result": run.output_payload}
                elif action == "resources/list":
                    response = {"result": [serialize_resource(resource).model_dump() for resource in get_resource_definitions(session)]}
                elif action == "resources/read":
                    resource = get_resource_definition(session, payload["resource_id"])
                    mime_type, content = resource.resolver(session, payload["resource_id"])
                    response = {"result": {"resource_id": resource.resource_id, "mime_type": mime_type, "content": content}}
                elif action == "prompts/list":
                    response = {"result": [serialize_prompt(prompt).model_dump() for prompt in get_prompt_definitions()]}
                elif action == "prompts/get":
                    prompt = get_prompt_definition(payload["prompt_name"])
                    response = {"result": {"name": prompt.name, "messages": prompt.renderer(session, payload.get("arguments", {}))}}
                elif action == "ping":
                    response = {"result": {"ok": True}}
                else:
                    response = {"error": {"message": f"Unknown action {action}"}}
            except Exception as exc:
                response = {"error": {"message": str(exc)}}
            sys.stdout.write(json.dumps(response, ensure_ascii=True) + "\n")
            sys.stdout.flush()
    finally:
        session.close()


def run_stdio_server() -> None:
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        asyncio.run(_fallback_stdio_loop())
        return

    settings = get_settings()
    session = _db_session()
    server = FastMCP(f"{settings.app_name} MCP")

    def _tool_call(name: str, arguments: dict[str, Any]) -> Any:
        run = invoke_tool(session, settings, name, arguments)
        return run.output_payload

    for definition in get_tool_definitions():
        def _make_tool(tool_name: str):
            def _runner(**kwargs: Any) -> Any:
                return _tool_call(tool_name, kwargs)

            _runner.__name__ = tool_name
            _runner.__doc__ = definition.description
            return _runner

        server.tool(name=definition.name)(_make_tool(definition.name))

    for prompt in get_prompt_definitions():
        def _make_prompt(prompt_name: str):
            def _runner(**kwargs: Any) -> str:
                definition = get_prompt_definition(prompt_name)
                messages = definition.renderer(session, kwargs)
                return "\n\n".join(message["content"] for message in messages)

            _runner.__name__ = prompt_name
            _runner.__doc__ = prompt.description
            return _runner

        server.prompt(name=prompt.name)(_make_prompt(prompt.name))

    for resource in get_resource_definitions(session):
        def _make_resource(resource_id: str):
            def _runner() -> str:
                definition = get_resource_definition(session, resource_id)
                return definition.resolver(session, resource_id)[1]

            _runner.__name__ = resource_id.replace(":", "_")
            _runner.__doc__ = resource.title
            return _runner

        server.resource(resource.uri)(_make_resource(resource.resource_id))

    try:
        server.run(transport="stdio")
    finally:
        session.close()
