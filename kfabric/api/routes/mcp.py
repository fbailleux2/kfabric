from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from kfabric import __version__
from kfabric.api.deps import get_db, get_runtime_settings, require_api_key
from kfabric.api.serializers import (
    serialize_mcp_session,
    serialize_prompt,
    serialize_prompt_render,
    serialize_resource,
    serialize_resource_content,
    serialize_tool_run,
    serialize_tool_schema,
)
from kfabric.config import AppSettings
from kfabric.domain.schemas import (
    MCPSessionCreateRequest,
    MCPSessionResponse,
    PromptRenderRequest,
    PromptRenderResponse,
    PromptResponse,
    ResourceContentResponse,
    ResourceResponse,
    ToolInvokeRequest,
    ToolRunResponse,
    ToolSchemaResponse,
)
from kfabric.mcp.registry import (
    close_session,
    create_session,
    get_capabilities,
    get_prompt_definition,
    get_prompt_definitions,
    get_resource_definition,
    get_resource_definitions,
    get_session,
    get_tool_definition,
    get_tool_definitions,
    invoke_tool,
)


router = APIRouter(tags=["mcp"], dependencies=[Depends(require_api_key)])


@router.post("/mcp/sessions", response_model=MCPSessionResponse)
def create_mcp_session(
    payload: MCPSessionCreateRequest,
    db: Session = Depends(get_db),
    settings: AppSettings = Depends(get_runtime_settings),
) -> MCPSessionResponse:
    session = create_session(db, settings, payload)
    return serialize_mcp_session(session, settings.app_name, __version__)


@router.get("/mcp/sessions/{session_id}", response_model=MCPSessionResponse)
def read_mcp_session(
    session_id: str,
    db: Session = Depends(get_db),
    settings: AppSettings = Depends(get_runtime_settings),
) -> MCPSessionResponse:
    session = get_session(db, session_id)
    return serialize_mcp_session(session, settings.app_name, __version__)


@router.delete("/mcp/sessions/{session_id}", response_model=MCPSessionResponse)
def delete_mcp_session(
    session_id: str,
    db: Session = Depends(get_db),
    settings: AppSettings = Depends(get_runtime_settings),
) -> MCPSessionResponse:
    session = close_session(db, session_id)
    return serialize_mcp_session(session, settings.app_name, __version__)


@router.get("/mcp/capabilities")
def capabilities() -> dict[str, object]:
    return get_capabilities()


@router.get("/tools", response_model=list[ToolSchemaResponse])
def list_tools() -> list[ToolSchemaResponse]:
    return [serialize_tool_schema(tool) for tool in get_tool_definitions()]


@router.get("/tools/{tool_name}", response_model=ToolSchemaResponse)
def get_tool(tool_name: str) -> ToolSchemaResponse:
    return serialize_tool_schema(get_tool_definition(tool_name))


@router.get("/tools/{tool_name}/schema", response_model=ToolSchemaResponse)
def get_tool_schema(tool_name: str) -> ToolSchemaResponse:
    return serialize_tool_schema(get_tool_definition(tool_name))


@router.post("/tools/{tool_name}:invoke", response_model=ToolRunResponse)
def call_tool(
    tool_name: str,
    payload: ToolInvokeRequest,
    db: Session = Depends(get_db),
    settings: AppSettings = Depends(get_runtime_settings),
) -> ToolRunResponse:
    run = invoke_tool(db, settings, tool_name, payload.arguments, payload.session_id)
    return serialize_tool_run(run)


@router.get("/resources", response_model=list[ResourceResponse])
def list_resources(db: Session = Depends(get_db)) -> list[ResourceResponse]:
    return [serialize_resource(resource) for resource in get_resource_definitions(db)]


@router.get("/resources/{resource_id}", response_model=ResourceResponse)
def get_resource(resource_id: str, db: Session = Depends(get_db)) -> ResourceResponse:
    return serialize_resource(get_resource_definition(db, resource_id))


@router.get("/resources/{resource_id}/content", response_model=ResourceContentResponse)
def get_resource_content(resource_id: str, db: Session = Depends(get_db)) -> ResourceContentResponse:
    resource = get_resource_definition(db, resource_id)
    mime_type, content = resource.resolver(db, resource_id)
    return serialize_resource_content(resource_id, mime_type, content)


@router.get("/prompts", response_model=list[PromptResponse])
def list_prompts() -> list[PromptResponse]:
    return [serialize_prompt(prompt) for prompt in get_prompt_definitions()]


@router.get("/prompts/{prompt_name}", response_model=PromptResponse)
def get_prompt(prompt_name: str) -> PromptResponse:
    return serialize_prompt(get_prompt_definition(prompt_name))


@router.post("/prompts/{prompt_name}:render", response_model=PromptRenderResponse)
def render_prompt(
    prompt_name: str,
    payload: PromptRenderRequest,
    db: Session = Depends(get_db),
) -> PromptRenderResponse:
    prompt = get_prompt_definition(prompt_name)
    return serialize_prompt_render(prompt, prompt.renderer(db, payload.arguments))
