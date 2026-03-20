from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from kfabric import __version__
from kfabric.api.deps import (
    get_db,
    get_request_principal,
    get_runtime_settings,
    require_admin_principal,
    require_authenticated_principal,
)
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
    enqueue_tool,
    get_capabilities,
    get_prompt_definition,
    get_prompt_definitions,
    get_resource_definition,
    get_resource_definitions,
    get_session,
    get_tool_run,
    list_tool_runs,
    get_tool_definition,
    get_tool_definitions,
    invoke_tool,
)


router = APIRouter(tags=["mcp"], dependencies=[Depends(require_authenticated_principal)])


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
    principal=Depends(get_request_principal),
) -> ToolRunResponse:
    if payload.async_run:
        run = enqueue_tool(db, settings, principal, tool_name, payload.arguments, payload.session_id)
    else:
        run = invoke_tool(db, settings, principal, tool_name, payload.arguments, payload.session_id)
    return serialize_tool_run(run)


@router.get("/tool-runs", response_model=list[ToolRunResponse], dependencies=[Depends(require_admin_principal)])
def recent_tool_runs(limit: int = 20, db: Session = Depends(get_db)) -> list[ToolRunResponse]:
    return [serialize_tool_run(tool_run) for tool_run in list_tool_runs(db, limit)]


@router.get("/tool-runs/{run_id}", response_model=ToolRunResponse)
def read_tool_run(run_id: str, db: Session = Depends(get_db)) -> ToolRunResponse:
    return serialize_tool_run(get_tool_run(db, run_id))


@router.get("/resources", response_model=list[ResourceResponse])
def list_resources(db: Session = Depends(get_db), principal=Depends(get_request_principal)) -> list[ResourceResponse]:
    return [serialize_resource(resource) for resource in get_resource_definitions(db, principal)]


@router.get("/resources/{resource_id}", response_model=ResourceResponse)
def get_resource(resource_id: str, db: Session = Depends(get_db), principal=Depends(get_request_principal)) -> ResourceResponse:
    return serialize_resource(get_resource_definition(db, principal, resource_id))


@router.get("/resources/{resource_id}/content", response_model=ResourceContentResponse)
def get_resource_content(resource_id: str, db: Session = Depends(get_db), principal=Depends(get_request_principal)) -> ResourceContentResponse:
    resource = get_resource_definition(db, principal, resource_id)
    mime_type, content = resource.resolver(db, principal, resource_id)
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
    principal=Depends(get_request_principal),
) -> PromptRenderResponse:
    prompt = get_prompt_definition(prompt_name)
    return serialize_prompt_render(prompt, prompt.renderer(db, principal, payload.arguments))
