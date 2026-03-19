from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from kfabric.domain.enums import (
    CandidateStatus,
    CorpusStatus,
    DocumentDecisionStatus,
    FragmentType,
    QueryStatus,
    SessionStatus,
    ToolRunStatus,
    VerificationStatus,
)


class SchemaModel(BaseModel):
    model_config = {"from_attributes": True}


class QueryCreate(SchemaModel):
    theme: str | None = None
    question: str | None = None
    keywords: list[str] = Field(default_factory=list)
    language: str = "fr"
    period: str | None = None
    document_types: list[str] = Field(default_factory=list)
    preferred_domains: list[str] = Field(default_factory=list)
    excluded_domains: list[str] = Field(default_factory=list)
    quality_target: str = "balanced"


class QueryResponse(SchemaModel):
    id: str
    theme: str | None
    question: str | None
    keywords: list[str]
    expansion_text: str | None
    status: QueryStatus
    trace_id: str
    created_at: datetime
    updated_at: datetime


class CandidateResponse(SchemaModel):
    id: str
    query_id: str
    title: str
    source_url: str
    snippet: str
    domain: str
    document_type: str
    language: str
    discovery_rank: int
    discovery_source: str
    status: CandidateStatus
    collected_document_id: str | None = None


class CollectCandidateResponse(SchemaModel):
    candidate_id: str
    collected_document_id: str
    raw_hash: str
    content_type: str
    status: CandidateStatus


class ScoreBreakdown(SchemaModel):
    relevance_score: int
    source_quality_score: int
    documentary_value_score: int
    freshness_score: int
    exploitability_score: int
    originality_score: int


class AnalyzeDocumentResponse(SchemaModel):
    parsed_document_id: str
    decision_id: str
    decision_status: DocumentDecisionStatus
    global_score: int
    breakdown: ScoreBreakdown
    salvaged_fragment_ids: list[str] = Field(default_factory=list)
    trace_id: str


class DecisionOverrideResponse(SchemaModel):
    parsed_document_id: str
    decision_status: DocumentDecisionStatus
    justification: str


class FragmentResponse(SchemaModel):
    id: str
    source_document_id: str
    query_id: str
    fragment_text: str
    fragment_type: FragmentType
    fragment_score: int
    confidence_level: float
    verification_status: VerificationStatus
    included_in_synthesis: bool


class FragmentConsolidateRequest(SchemaModel):
    query_id: str


class FragmentClusterResponse(SchemaModel):
    id: str
    query_id: str
    label: str
    cluster_summary: str
    contribution_score: float
    fragment_ids: list[str]


class SynthesisCreateRequest(SchemaModel):
    query_id: str
    fragment_ids: list[str] | None = None


class SynthesisResponse(SchemaModel):
    id: str
    query_id: str
    theme: str
    synthesis_markdown: str
    generated_from_n_fragments: int
    generated_from_n_rejected_docs: int
    overall_confidence: float
    index_priority: float
    created_at: datetime


class CorpusResponse(SchemaModel):
    id: str
    query_id: str
    title: str
    corpus_markdown: str
    status: CorpusStatus
    index_ready: bool
    created_at: datetime
    updated_at: datetime


class PrepareIndexResponse(SchemaModel):
    corpus_id: str
    index_ready: bool
    chunk_count: int
    vector_dimensions: int
    artifact_path: str


class MCPSessionCreateRequest(SchemaModel):
    client_name: str
    client_version: str
    protocol_version: str = "2025-06-18"
    requested_capabilities: dict[str, bool] = Field(default_factory=dict)
    tenant_id: str | None = "default"


class MCPSessionResponse(SchemaModel):
    session_id: str
    server_name: str
    server_version: str
    protocol_version: str
    granted_capabilities: dict[str, bool]
    status: SessionStatus


class ToolInvokeRequest(SchemaModel):
    session_id: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    async_run: bool = Field(default=False, alias="async")

    model_config = {"populate_by_name": True}


class ToolRunResponse(SchemaModel):
    run_id: str
    tool_name: str
    status: ToolRunStatus
    output: Any | None = None
    trace_id: str


class ToolSchemaResponse(SchemaModel):
    name: str
    title: str
    description: str
    version: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    security: dict[str, Any]


class ResourceResponse(SchemaModel):
    resource_id: str
    uri: str
    name: str
    title: str
    mime_type: str
    version: str
    tags: list[str]
    permissions: list[str]


class PromptResponse(SchemaModel):
    name: str
    title: str
    description: str
    arguments_schema: dict[str, Any]


class PromptRenderRequest(SchemaModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


class PromptRenderResponse(SchemaModel):
    name: str
    messages: list[dict[str, str]]


class HealthResponse(SchemaModel):
    status: str
    service: str
    version: str


class VersionResponse(SchemaModel):
    service: str
    version: str
    environment: str
    secure_mode: bool


class AuditEventResponse(SchemaModel):
    id: str
    event_type: str
    entity_type: str
    entity_id: str
    trace_id: str
    actor: str
    payload: dict[str, Any]
    created_at: datetime


class ResourceContentResponse(SchemaModel):
    resource_id: str
    mime_type: str
    content: str


class ErrorBody(SchemaModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    trace_id: str


class ErrorEnvelope(SchemaModel):
    error: ErrorBody
