from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta, timezone
import json
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from kfabric import __version__
from kfabric.config import AppSettings
from kfabric.domain.enums import SessionStatus, ToolRunStatus
from kfabric.infra.models import (
    CandidateDocument,
    CollectedDocument,
    Corpus,
    FragmentSynthesis,
    MCPSession,
    ParsedDocument,
    Query,
    SalvagedFragment,
    ToolRun,
    utcnow,
)
from kfabric.services.auth_service import AuthContext, build_visibility_clause, can_access_query
from kfabric.services.orchestrator import Orchestrator


ToolHandler = Callable[[Orchestrator, Session, AppSettings, dict[str, Any]], Any]
PromptRenderer = Callable[[Session, AuthContext, dict[str, Any]], list[dict[str, str]]]
ResourceResolver = Callable[[Session, AuthContext, str], tuple[str, str]]


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    title: str
    description: str
    version: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    security: dict[str, Any]
    handler: ToolHandler


@dataclass(frozen=True, slots=True)
class PromptDefinition:
    name: str
    title: str
    description: str
    arguments_schema: dict[str, Any]
    renderer: PromptRenderer


@dataclass(frozen=True, slots=True)
class ResourceDefinition:
    resource_id: str
    uri: str
    name: str
    title: str
    mime_type: str
    version: str
    tags: list[str]
    permissions: list[str]
    resolver: ResourceResolver


SUPPORTED_CAPABILITIES = {
    "tools": True,
    "resources": True,
    "prompts": True,
    "logging": True,
}


def create_session(db: Session, settings: AppSettings, payload) -> MCPSession:
    granted = {
        capability: bool(payload.requested_capabilities.get(capability, True) and supported)
        for capability, supported in SUPPORTED_CAPABILITIES.items()
    }
    session = MCPSession(
        client_name=payload.client_name,
        client_version=payload.client_version,
        protocol_version=payload.protocol_version,
        requested_capabilities=payload.requested_capabilities,
        granted_capabilities=granted,
        tenant_id=payload.tenant_id or "default",
        status=SessionStatus.ACTIVE.value,
        expires_at=utcnow() + timedelta(seconds=settings.session_ttl_seconds),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def close_session(db: Session, session_id: str) -> MCPSession:
    session = db.get(MCPSession, session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")
    session.status = SessionStatus.CLOSED.value
    db.commit()
    db.refresh(session)
    return session


def get_session(db: Session, session_id: str) -> MCPSession:
    session = db.get(MCPSession, session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < utcnow():
        session.status = SessionStatus.EXPIRED.value
        db.commit()
        raise ValueError(f"Session {session_id} expired")
    return session


def get_capabilities() -> dict[str, Any]:
    return {
        "server": {"name": "KFabric MCP", "version": __version__},
        "protocol_version": "2025-06-18",
        "capabilities": SUPPORTED_CAPABILITIES,
    }


def _discover_documents(orchestrator: Orchestrator, _db: Session, _settings: AppSettings, arguments: dict[str, Any]) -> Any:
    query_id = arguments["query_id"]
    return [{"id": candidate.id, "title": candidate.title} for candidate in orchestrator.discover(query_id)]


def _list_candidates(orchestrator: Orchestrator, _db: Session, _settings: AppSettings, arguments: dict[str, Any]) -> Any:
    query_id = arguments["query_id"]
    return [
        {
            "id": candidate.id,
            "title": candidate.title,
            "status": candidate.status,
            "domain": candidate.domain,
            "source_url": candidate.source_url,
        }
        for candidate in orchestrator.list_candidates(query_id)
    ]


def _analyze_document(orchestrator: Orchestrator, _db: Session, _settings: AppSettings, arguments: dict[str, Any]) -> Any:
    result = orchestrator.analyze_document(arguments["document_id"])
    return {
        "parsed_document_id": result["parsed_document"].id,
        "decision_status": result["decision"].status,
        "global_score": result["score"].global_score,
        "salvaged_fragment_ids": [fragment.id for fragment in result["fragments"]],
    }


def _accept_document(orchestrator: Orchestrator, _db: Session, _settings: AppSettings, arguments: dict[str, Any]) -> Any:
    decision = orchestrator.override_decision(arguments["document_id"], accepted=True)
    return {"parsed_document_id": arguments["document_id"], "decision_status": decision.status}


def _reject_document(orchestrator: Orchestrator, _db: Session, _settings: AppSettings, arguments: dict[str, Any]) -> Any:
    decision = orchestrator.override_decision(arguments["document_id"], accepted=False)
    return {"parsed_document_id": arguments["document_id"], "decision_status": decision.status}


def _list_salvaged_fragments(orchestrator: Orchestrator, _db: Session, _settings: AppSettings, arguments: dict[str, Any]) -> Any:
    return [
        {
            "id": fragment.id,
            "fragment_text": fragment.fragment_text,
            "fragment_score": fragment.fragment_score,
            "fragment_type": fragment.fragment_type,
        }
        for fragment in orchestrator.list_fragments(arguments.get("query_id"))
    ]


def _generate_fragment_synthesis(orchestrator: Orchestrator, _db: Session, _settings: AppSettings, arguments: dict[str, Any]) -> Any:
    synthesis = orchestrator.create_synthesis(arguments["query_id"], arguments.get("fragment_ids"))
    return {"synthesis_id": synthesis.id, "overall_confidence": synthesis.overall_confidence}


def _get_corpus_status(orchestrator: Orchestrator, db: Session, _settings: AppSettings, arguments: dict[str, Any]) -> Any:
    corpus_id = arguments.get("corpus_id")
    if corpus_id:
        corpus = orchestrator.get_corpus(corpus_id)
    else:
        query_id = arguments["query_id"]
        query = orchestrator.get_query(query_id)
        corpus = db.scalars(select(Corpus).where(Corpus.query_id == query.id).order_by(Corpus.created_at.desc())).first()
    if not corpus:
        raise ValueError("Corpus not found")
    return {
        "corpus_id": corpus.id,
        "status": corpus.status,
        "index_ready": corpus.index_ready,
        "artifact_path": corpus.artifact_path,
    }


def get_tool_definitions() -> list[ToolDefinition]:
    common_security = {"authentication": "user_session_or_api_token", "audit": True}
    return [
        ToolDefinition(
            name="discover_documents",
            title="Discover Documents",
            description="Launch discovery for an existing KFabric query.",
            version="1.0.0",
            input_schema={"type": "object", "properties": {"query_id": {"type": "string"}}, "required": ["query_id"]},
            output_schema={"type": "array"},
            security=common_security,
            handler=_discover_documents,
        ),
        ToolDefinition(
            name="list_candidates",
            title="List Candidates",
            description="List candidate documents for a query.",
            version="1.0.0",
            input_schema={"type": "object", "properties": {"query_id": {"type": "string"}}, "required": ["query_id"]},
            output_schema={"type": "array"},
            security=common_security,
            handler=_list_candidates,
        ),
        ToolDefinition(
            name="analyze_document",
            title="Analyze Document",
            description="Parse, score and decide on a collected document.",
            version="1.0.0",
            input_schema={"type": "object", "properties": {"document_id": {"type": "string"}}, "required": ["document_id"]},
            output_schema={"type": "object"},
            security=common_security,
            handler=_analyze_document,
        ),
        ToolDefinition(
            name="accept_document",
            title="Accept Document",
            description="Force a manual accept decision for a parsed document.",
            version="1.0.0",
            input_schema={"type": "object", "properties": {"document_id": {"type": "string"}}, "required": ["document_id"]},
            output_schema={"type": "object"},
            security=common_security,
            handler=_accept_document,
        ),
        ToolDefinition(
            name="reject_document",
            title="Reject Document",
            description="Force a manual reject decision for a parsed document.",
            version="1.0.0",
            input_schema={"type": "object", "properties": {"document_id": {"type": "string"}}, "required": ["document_id"]},
            output_schema={"type": "object"},
            security=common_security,
            handler=_reject_document,
        ),
        ToolDefinition(
            name="list_salvaged_fragments",
            title="List Salvaged Fragments",
            description="List salvaged fragments optionally filtered by query.",
            version="1.0.0",
            input_schema={"type": "object", "properties": {"query_id": {"type": "string"}}},
            output_schema={"type": "array"},
            security=common_security,
            handler=_list_salvaged_fragments,
        ),
        ToolDefinition(
            name="generate_fragment_synthesis",
            title="Generate Fragment Synthesis",
            description="Create a synthesis from salvaged fragments.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "query_id": {"type": "string"},
                    "fragment_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["query_id"],
            },
            output_schema={"type": "object"},
            security=common_security,
            handler=_generate_fragment_synthesis,
        ),
        ToolDefinition(
            name="get_corpus_status",
            title="Get Corpus Status",
            description="Read the latest corpus status for a query or corpus id.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "query_id": {"type": "string"},
                    "corpus_id": {"type": "string"},
                },
            },
            output_schema={"type": "object"},
            security=common_security,
            handler=_get_corpus_status,
        ),
    ]


def get_tool_definition(name: str) -> ToolDefinition:
    for tool in get_tool_definitions():
        if tool.name == name:
            return tool
    raise ValueError(f"Tool {name} not found")


def _resolve_document_resource(db: Session, principal: AuthContext, resource_id: str) -> tuple[str, str]:
    _, document_id = resource_id.split(":", maxsplit=1)
    document = db.get(ParsedDocument, document_id)
    if not document:
        raise ValueError(f"Resource {resource_id} not found")
    _ensure_query_access(principal, document.collected_document.candidate.query)
    return "text/markdown", document.normalized_text


def _resolve_synthesis_resource(db: Session, principal: AuthContext, resource_id: str) -> tuple[str, str]:
    _, synthesis_id = resource_id.split(":", maxsplit=1)
    synthesis = db.get(FragmentSynthesis, synthesis_id)
    if not synthesis:
        raise ValueError(f"Resource {resource_id} not found")
    _ensure_query_access(principal, synthesis.query)
    return "text/markdown", synthesis.synthesis_markdown


def _resolve_corpus_resource(db: Session, principal: AuthContext, resource_id: str) -> tuple[str, str]:
    _, corpus_id = resource_id.split(":", maxsplit=1)
    corpus = db.get(Corpus, corpus_id)
    if not corpus:
        raise ValueError(f"Resource {resource_id} not found")
    _ensure_query_access(principal, corpus.query)
    return "text/markdown", corpus.corpus_markdown


def _resolve_query_resource(db: Session, principal: AuthContext, resource_id: str) -> tuple[str, str]:
    _, query_id = resource_id.split(":", maxsplit=1)
    query = db.get(Query, query_id)
    if not query:
        raise ValueError(f"Resource {resource_id} not found")
    _ensure_query_access(principal, query)
    return (
        "application/json",
        json.dumps(
            {
                "id": query.id,
                "theme": query.theme,
                "question": query.question,
                "keywords": query.keywords,
                "status": query.status,
                "trace_id": query.trace_id,
            },
            ensure_ascii=True,
            indent=2,
        ),
    )


def get_resource_definitions(db: Session, principal: AuthContext) -> list[ResourceDefinition]:
    resources: list[ResourceDefinition] = []
    document_stmt = (
        select(ParsedDocument)
        .join(ParsedDocument.collected_document)
        .join(CollectedDocument.candidate)
        .join(CandidateDocument.query)
        .order_by(ParsedDocument.created_at.desc())
        .limit(20)
    )
    visibility_clause = build_visibility_clause(principal)
    if visibility_clause is not None:
        document_stmt = document_stmt.where(visibility_clause)
    for document in db.scalars(document_stmt):
        resources.append(
            ResourceDefinition(
                resource_id=f"document:{document.id}",
                uri=f"kfabric://documents/{document.id}",
                name="document",
                title=document.extracted_title or document.id,
                mime_type="text/markdown",
                version="1.0.0",
                tags=["document", "normalized"],
                permissions=["read"],
                resolver=_resolve_document_resource,
            )
        )
    query_stmt = select(Query).order_by(Query.created_at.desc()).limit(10)
    if visibility_clause is not None:
        query_stmt = query_stmt.where(visibility_clause)
    for fragment_query in db.scalars(query_stmt):
        resources.append(
            ResourceDefinition(
                resource_id=f"query:{fragment_query.id}",
                uri=f"kfabric://queries/{fragment_query.id}",
                name="query",
                title=fragment_query.theme or fragment_query.question or fragment_query.id,
                mime_type="application/json",
                version="1.0.0",
                tags=["query", "metadata"],
                permissions=["read"],
                resolver=_resolve_query_resource,
            )
        )
    synthesis_stmt = select(FragmentSynthesis).join(Query).order_by(FragmentSynthesis.created_at.desc()).limit(20)
    if visibility_clause is not None:
        synthesis_stmt = synthesis_stmt.where(visibility_clause)
    for synthesis in db.scalars(synthesis_stmt):
        resources.append(
            ResourceDefinition(
                resource_id=f"synthesis:{synthesis.id}",
                uri=f"kfabric://syntheses/{synthesis.id}",
                name="synthesis",
                title=synthesis.theme,
                mime_type="text/markdown",
                version="1.0.0",
                tags=["synthesis", "fragments"],
                permissions=["read"],
                resolver=_resolve_synthesis_resource,
            )
        )
    corpus_stmt = select(Corpus).join(Query).order_by(Corpus.created_at.desc()).limit(20)
    if visibility_clause is not None:
        corpus_stmt = corpus_stmt.where(visibility_clause)
    for corpus in db.scalars(corpus_stmt):
        resources.append(
            ResourceDefinition(
                resource_id=f"corpus:{corpus.id}",
                uri=f"kfabric://corpora/{corpus.id}",
                name="corpus",
                title=corpus.title,
                mime_type="text/markdown",
                version="1.0.0",
                tags=["corpus", "final"],
                permissions=["read"],
                resolver=_resolve_corpus_resource,
            )
        )
    return resources


def get_resource_definition(db: Session, principal: AuthContext, resource_id: str) -> ResourceDefinition:
    for resource in get_resource_definitions(db, principal):
        if resource.resource_id == resource_id:
            return resource
    raise ValueError(f"Resource {resource_id} not found")


def _render_document_summary(db: Session, principal: AuthContext, arguments: dict[str, Any]) -> list[dict[str, str]]:
    document = db.get(ParsedDocument, arguments["document_id"])
    if not document:
        raise ValueError(f"Document {arguments['document_id']} not found")
    _ensure_query_access(principal, document.collected_document.candidate.query)
    return [
        {
            "role": "user",
            "content": (
                "Resume ce document KFabric en insistant sur la pertinence, la source, "
                "les signaux factuels et les limites de confiance.\n\n"
                f"{document.normalized_text[:1800]}"
            ),
        }
    ]


def _render_fragment_synthesis(db: Session, principal: AuthContext, arguments: dict[str, Any]) -> list[dict[str, str]]:
    query = db.get(Query, arguments["query_id"])
    if not query:
        raise ValueError(f"Query {arguments['query_id']} not found")
    _ensure_query_access(principal, query)
    fragments = list(
        db.scalars(
            select(SalvagedFragment)
            .where(SalvagedFragment.query_id == arguments["query_id"])
            .order_by(SalvagedFragment.fragment_score.desc())
            .limit(12)
        )
    )
    joined = "\n".join(f"- {fragment.fragment_text}" for fragment in fragments)
    return [
        {
            "role": "user",
            "content": (
                "Produis une synthese prudente, attribuee et non reconstructive a partir des fragments suivants:\n"
                f"{joined}"
            ),
        }
    ]


def _render_corpus_review(db: Session, principal: AuthContext, arguments: dict[str, Any]) -> list[dict[str, str]]:
    corpus = db.get(Corpus, arguments["corpus_id"])
    if not corpus:
        raise ValueError(f"Corpus {arguments['corpus_id']} not found")
    _ensure_query_access(principal, corpus.query)
    return [
        {
            "role": "user",
            "content": (
                "Evalue la qualite de ce corpus final. Indique les angles morts, la confiance et "
                "les risques de redondance.\n\n"
                f"{corpus.corpus_markdown[:2400]}"
            ),
        }
    ]


def get_prompt_definitions() -> list[PromptDefinition]:
    return [
        PromptDefinition(
            name="summarize_document",
            title="Resume Documentaire",
            description="Construit un prompt de resume prudent pour un document normalise.",
            arguments_schema={"type": "object", "properties": {"document_id": {"type": "string"}}, "required": ["document_id"]},
            renderer=_render_document_summary,
        ),
        PromptDefinition(
            name="synthesize_fragments",
            title="Synthese de Fragments",
            description="Construit un prompt de synthese pour des fragments recuperes.",
            arguments_schema={"type": "object", "properties": {"query_id": {"type": "string"}}, "required": ["query_id"]},
            renderer=_render_fragment_synthesis,
        ),
        PromptDefinition(
            name="review_corpus",
            title="Revue de Corpus",
            description="Construit un prompt de revue qualitative du corpus final.",
            arguments_schema={"type": "object", "properties": {"corpus_id": {"type": "string"}}, "required": ["corpus_id"]},
            renderer=_render_corpus_review,
        ),
    ]


def get_prompt_definition(name: str) -> PromptDefinition:
    for prompt in get_prompt_definitions():
        if prompt.name == name:
            return prompt
    raise ValueError(f"Prompt {name} not found")


def invoke_tool(
    db: Session,
    settings: AppSettings,
    principal: AuthContext,
    tool_name: str,
    arguments: dict[str, Any],
    session_id: str | None = None,
) -> ToolRun:
    if session_id:
        get_session(db, session_id)
    tool = get_tool_definition(tool_name)
    tool_run = ToolRun(
        tool_name=tool_name,
        session_id=session_id,
        status=ToolRunStatus.RUNNING.value,
        input_payload=arguments,
    )
    db.add(tool_run)
    db.flush()
    orchestrator = Orchestrator(session=db, settings=settings, principal=principal)
    try:
        output = tool.handler(orchestrator, db, settings, arguments)
        tool_run.status = ToolRunStatus.SUCCEEDED.value
        tool_run.output_payload = {"result": output}
    except Exception as exc:
        tool_run.status = ToolRunStatus.FAILED.value
        tool_run.error_payload = {"message": str(exc)}
        db.commit()
        raise
    db.commit()
    db.refresh(tool_run)
    return tool_run


def _ensure_query_access(principal: AuthContext, query: Query) -> None:
    if can_access_query(principal, query):
        return
    raise PermissionError("Access denied to this query")
