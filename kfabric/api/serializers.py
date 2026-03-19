from __future__ import annotations

from kfabric.domain.enums import SessionStatus, ToolRunStatus
from kfabric.domain.schemas import (
    AnalyzeDocumentResponse,
    AuditEventResponse,
    CandidateResponse,
    CollectCandidateResponse,
    CorpusResponse,
    DecisionOverrideResponse,
    FragmentClusterResponse,
    FragmentResponse,
    MCPSessionResponse,
    PrepareIndexResponse,
    PromptResponse,
    PromptRenderResponse,
    QueryResponse,
    ResourceContentResponse,
    ResourceResponse,
    ScoreBreakdown,
    SynthesisResponse,
    ToolRunResponse,
    ToolSchemaResponse,
    VersionResponse,
)
from kfabric.infra.models import (
    AuditEvent,
    CandidateDocument,
    Corpus,
    DocumentDecision,
    DocumentScore,
    FragmentCluster,
    FragmentSynthesis,
    MCPSession,
    ParsedDocument,
    SalvagedFragment,
    ToolRun,
)


def serialize_query(query) -> QueryResponse:
    return QueryResponse.model_validate(query)


def serialize_candidate(candidate: CandidateDocument) -> CandidateResponse:
    return CandidateResponse(
        id=candidate.id,
        query_id=candidate.query_id,
        title=candidate.title,
        source_url=candidate.source_url,
        snippet=candidate.snippet,
        domain=candidate.domain,
        document_type=candidate.document_type,
        language=candidate.language,
        discovery_rank=candidate.discovery_rank,
        discovery_source=candidate.discovery_source,
        status=candidate.status,
        collected_document_id=candidate.collected_document.id if candidate.collected_document else None,
    )


def serialize_collect(candidate_id: str, collected) -> CollectCandidateResponse:
    return CollectCandidateResponse(
        candidate_id=candidate_id,
        collected_document_id=collected.id,
        raw_hash=collected.raw_hash,
        content_type=collected.content_type,
        status=collected.candidate.status,
    )


def serialize_analysis(parsed: ParsedDocument, score: DocumentScore, decision: DocumentDecision, fragments: list[SalvagedFragment]) -> AnalyzeDocumentResponse:
    return AnalyzeDocumentResponse(
        parsed_document_id=parsed.id,
        decision_id=decision.id,
        decision_status=decision.status,
        global_score=score.global_score,
        breakdown=ScoreBreakdown(
            relevance_score=score.relevance_score,
            source_quality_score=score.source_quality_score,
            documentary_value_score=score.documentary_value_score,
            freshness_score=score.freshness_score,
            exploitability_score=score.exploitability_score,
            originality_score=score.originality_score,
        ),
        salvaged_fragment_ids=[fragment.id for fragment in fragments],
        trace_id=parsed.trace_id,
    )


def serialize_decision_override(parsed_document_id: str, decision: DocumentDecision) -> DecisionOverrideResponse:
    return DecisionOverrideResponse(
        parsed_document_id=parsed_document_id,
        decision_status=decision.status,
        justification=decision.justification,
    )


def serialize_fragment(fragment: SalvagedFragment) -> FragmentResponse:
    return FragmentResponse(
        id=fragment.id,
        source_document_id=fragment.parsed_document_id,
        query_id=fragment.query_id,
        fragment_text=fragment.fragment_text,
        fragment_type=fragment.fragment_type,
        fragment_score=fragment.fragment_score,
        confidence_level=fragment.confidence_level,
        verification_status=fragment.verification_status,
        included_in_synthesis=fragment.included_in_synthesis,
    )


def serialize_cluster(cluster: FragmentCluster) -> FragmentClusterResponse:
    return FragmentClusterResponse.model_validate(cluster)


def serialize_synthesis(synthesis: FragmentSynthesis) -> SynthesisResponse:
    return SynthesisResponse.model_validate(synthesis)


def serialize_corpus(corpus: Corpus) -> CorpusResponse:
    return CorpusResponse.model_validate(corpus)


def serialize_prepare_index(corpus: Corpus, payload: dict[str, object]) -> PrepareIndexResponse:
    return PrepareIndexResponse(
        corpus_id=corpus.id,
        index_ready=corpus.index_ready,
        chunk_count=int(payload["chunk_count"]),
        vector_dimensions=int(payload["vector_dimensions"]),
        artifact_path=str(payload["artifact_path"]),
    )


def serialize_mcp_session(session: MCPSession, server_name: str, server_version: str) -> MCPSessionResponse:
    return MCPSessionResponse(
        session_id=session.id,
        server_name=server_name,
        server_version=server_version,
        protocol_version=session.protocol_version,
        granted_capabilities=session.granted_capabilities,
        status=session.status or SessionStatus.INITIALIZED,
    )


def serialize_tool_schema(tool_def) -> ToolSchemaResponse:
    return ToolSchemaResponse(
        name=tool_def.name,
        title=tool_def.title,
        description=tool_def.description,
        version=tool_def.version,
        input_schema=tool_def.input_schema,
        output_schema=tool_def.output_schema,
        security=tool_def.security,
    )


def serialize_tool_run(tool_run: ToolRun) -> ToolRunResponse:
    return ToolRunResponse(
        run_id=tool_run.id,
        tool_name=tool_run.tool_name,
        status=tool_run.status or ToolRunStatus.QUEUED,
        output=tool_run.output_payload,
        trace_id=tool_run.trace_id,
    )


def serialize_resource(resource_def) -> ResourceResponse:
    return ResourceResponse(
        resource_id=resource_def.resource_id,
        uri=resource_def.uri,
        name=resource_def.name,
        title=resource_def.title,
        mime_type=resource_def.mime_type,
        version=resource_def.version,
        tags=resource_def.tags,
        permissions=resource_def.permissions,
    )


def serialize_resource_content(resource_id: str, mime_type: str, content: str) -> ResourceContentResponse:
    return ResourceContentResponse(resource_id=resource_id, mime_type=mime_type, content=content)


def serialize_prompt(prompt_def) -> PromptResponse:
    return PromptResponse(
        name=prompt_def.name,
        title=prompt_def.title,
        description=prompt_def.description,
        arguments_schema=prompt_def.arguments_schema,
    )


def serialize_prompt_render(prompt_def, messages: list[dict[str, str]]) -> PromptRenderResponse:
    return PromptRenderResponse(name=prompt_def.name, messages=messages)


def serialize_version(service: str, version: str, environment: str, secure_mode: bool) -> VersionResponse:
    return VersionResponse(service=service, version=version, environment=environment, secure_mode=secure_mode)


def serialize_audit_event(event: AuditEvent) -> AuditEventResponse:
    return AuditEventResponse.model_validate(event)
