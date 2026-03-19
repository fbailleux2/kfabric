from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from kfabric.domain.enums import (
    CandidateStatus,
    CorpusStatus,
    DocumentDecisionStatus,
    FragmentType,
    QueryStatus,
    SessionStatus,
    ToolRunStatus,
    UserRole,
    VerificationStatus,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Query(Base, TimestampMixin):
    __tablename__ = "queries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("qry"))
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    theme: Mapped[str | None] = mapped_column(String(255), nullable=True)
    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    language: Mapped[str] = mapped_column(String(8), default="fr")
    period: Mapped[str | None] = mapped_column(String(64), nullable=True)
    document_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_domains: Mapped[list[str]] = mapped_column(JSON, default=list)
    excluded_domains: Mapped[list[str]] = mapped_column(JSON, default=list)
    quality_target: Mapped[str] = mapped_column(String(32), default="balanced")
    expansion_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=QueryStatus.CREATED.value)
    trace_id: Mapped[str] = mapped_column(String(64), default=lambda: new_id("tr"))

    owner: Mapped[User | None] = relationship(back_populates="queries")
    expansions: Mapped[list[QueryExpansion]] = relationship(back_populates="query", cascade="all, delete-orphan")
    candidates: Mapped[list[CandidateDocument]] = relationship(back_populates="query", cascade="all, delete-orphan")
    fragment_clusters: Mapped[list[FragmentCluster]] = relationship(back_populates="query", cascade="all, delete-orphan")
    syntheses: Mapped[list[FragmentSynthesis]] = relationship(back_populates="query", cascade="all, delete-orphan")
    corpora: Mapped[list[Corpus]] = relationship(back_populates="query", cascade="all, delete-orphan")


class QueryExpansion(Base):
    __tablename__ = "query_expansions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("qexp"))
    query_id: Mapped[str] = mapped_column(ForeignKey("queries.id", ondelete="CASCADE"))
    original_query: Mapped[str] = mapped_column(Text)
    expanded_query: Mapped[str] = mapped_column(Text)
    expansion_terms: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    query: Mapped[Query] = relationship(back_populates="expansions")


class CandidateDocument(Base):
    __tablename__ = "candidate_documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("cand"))
    query_id: Mapped[str] = mapped_column(ForeignKey("queries.id", ondelete="CASCADE"))
    source_url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    snippet: Mapped[str] = mapped_column(Text, default="")
    domain: Mapped[str] = mapped_column(String(255), default="")
    document_type: Mapped[str] = mapped_column(String(64), default="web")
    language: Mapped[str] = mapped_column(String(8), default="fr")
    discovery_rank: Mapped[int] = mapped_column(Integer, default=0)
    discovery_source: Mapped[str] = mapped_column(String(64), default="heuristic")
    status: Mapped[str] = mapped_column(String(32), default=CandidateStatus.DISCOVERED.value)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    query: Mapped[Query] = relationship(back_populates="candidates")
    collected_document: Mapped[CollectedDocument | None] = relationship(back_populates="candidate", cascade="all, delete-orphan", uselist=False)


class CollectedDocument(Base):
    __tablename__ = "collected_documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("coldoc"))
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidate_documents.id", ondelete="CASCADE"), unique=True)
    raw_content: Mapped[str] = mapped_column(Text)
    raw_hash: Mapped[str] = mapped_column(String(64))
    content_type: Mapped[str] = mapped_column(String(128), default="text/plain")
    collection_method: Mapped[str] = mapped_column(String(64), default="synthetic")
    status: Mapped[str] = mapped_column(String(32), default="collected")
    trace_id: Mapped[str] = mapped_column(String(64), default=lambda: new_id("tr"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    candidate: Mapped[CandidateDocument] = relationship(back_populates="collected_document")
    parsed_document: Mapped[ParsedDocument | None] = relationship(back_populates="collected_document", cascade="all, delete-orphan", uselist=False)


class ParsedDocument(Base):
    __tablename__ = "parsed_documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("doc"))
    collected_document_id: Mapped[str] = mapped_column(ForeignKey("collected_documents.id", ondelete="CASCADE"), unique=True)
    normalized_text: Mapped[str] = mapped_column(Text)
    normalized_hash: Mapped[str] = mapped_column(String(64))
    extracted_title: Mapped[str] = mapped_column(Text, default="")
    headings: Mapped[list[str]] = mapped_column(JSON, default=list)
    text_length: Mapped[int] = mapped_column(Integer, default=0)
    extraction_method: Mapped[str] = mapped_column(String(64), default="heuristic")
    trace_id: Mapped[str] = mapped_column(String(64), default=lambda: new_id("tr"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    collected_document: Mapped[CollectedDocument] = relationship(back_populates="parsed_document")
    score: Mapped[DocumentScore | None] = relationship(back_populates="parsed_document", cascade="all, delete-orphan", uselist=False)
    decision: Mapped[DocumentDecision | None] = relationship(back_populates="parsed_document", cascade="all, delete-orphan", uselist=False)
    fragments: Mapped[list[SalvagedFragment]] = relationship(back_populates="parsed_document", cascade="all, delete-orphan")


class DocumentScore(Base):
    __tablename__ = "document_scores"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("score"))
    parsed_document_id: Mapped[str] = mapped_column(ForeignKey("parsed_documents.id", ondelete="CASCADE"), unique=True)
    global_score: Mapped[int] = mapped_column(Integer)
    relevance_score: Mapped[int] = mapped_column(Integer)
    source_quality_score: Mapped[int] = mapped_column(Integer)
    documentary_value_score: Mapped[int] = mapped_column(Integer)
    freshness_score: Mapped[int] = mapped_column(Integer)
    exploitability_score: Mapped[int] = mapped_column(Integer)
    originality_score: Mapped[int] = mapped_column(Integer)
    scoring_notes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    parsed_document: Mapped[ParsedDocument] = relationship(back_populates="score")


class DocumentDecision(Base):
    __tablename__ = "document_decisions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("decision"))
    parsed_document_id: Mapped[str] = mapped_column(ForeignKey("parsed_documents.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String(32), default=DocumentDecisionStatus.REJECTED.value)
    threshold_applied: Mapped[int] = mapped_column(Integer, default=75)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    justification: Mapped[str] = mapped_column(Text, default="")
    has_salvaged_fragments: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    parsed_document: Mapped[ParsedDocument] = relationship(back_populates="decision")


class FragmentCluster(Base):
    __tablename__ = "fragment_clusters"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("cluster"))
    query_id: Mapped[str] = mapped_column(ForeignKey("queries.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(255))
    cluster_summary: Mapped[str] = mapped_column(Text, default="")
    contribution_score: Mapped[float] = mapped_column(Float, default=0.0)
    fragment_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    query: Mapped[Query] = relationship(back_populates="fragment_clusters")


class SalvagedFragment(Base):
    __tablename__ = "salvaged_fragments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("frag"))
    parsed_document_id: Mapped[str] = mapped_column(ForeignKey("parsed_documents.id", ondelete="CASCADE"))
    query_id: Mapped[str] = mapped_column(ForeignKey("queries.id", ondelete="CASCADE"))
    fragment_text: Mapped[str] = mapped_column(Text)
    fragment_type: Mapped[str] = mapped_column(String(32), default=FragmentType.SIGNAL.value)
    fragment_score: Mapped[int] = mapped_column(Integer, default=0)
    confidence_level: Mapped[float] = mapped_column(Float, default=0.5)
    verification_status: Mapped[str] = mapped_column(String(32), default=VerificationStatus.TO_CONFIRM.value)
    included_in_synthesis: Mapped[bool] = mapped_column(Boolean, default=False)
    start_offset: Mapped[int] = mapped_column(Integer, default=0)
    end_offset: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    parsed_document: Mapped[ParsedDocument] = relationship(back_populates="fragments")


class FragmentSynthesis(Base):
    __tablename__ = "fragment_syntheses"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("syn"))
    query_id: Mapped[str] = mapped_column(ForeignKey("queries.id", ondelete="CASCADE"))
    theme: Mapped[str] = mapped_column(String(255), default="")
    synthesis_markdown: Mapped[str] = mapped_column(Text)
    generated_from_n_fragments: Mapped[int] = mapped_column(Integer, default=0)
    generated_from_n_rejected_docs: Mapped[int] = mapped_column(Integer, default=0)
    overall_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    index_priority: Mapped[float] = mapped_column(Float, default=0.25)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    query: Mapped[Query] = relationship(back_populates="syntheses")


class Corpus(Base, TimestampMixin):
    __tablename__ = "corpora"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("corpus"))
    query_id: Mapped[str] = mapped_column(ForeignKey("queries.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255))
    corpus_markdown: Mapped[str] = mapped_column(Text)
    accepted_document_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    synthesis_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default=CorpusStatus.DRAFT.value)
    index_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    query: Mapped[Query] = relationship(back_populates="corpora")


class ToolRun(Base, TimestampMixin):
    __tablename__ = "tool_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("run"))
    tool_name: Mapped[str] = mapped_column(String(255))
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=ToolRunStatus.QUEUED.value)
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    output_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    trace_id: Mapped[str] = mapped_column(String(64), default=lambda: new_id("tr"))


class MCPSession(Base):
    __tablename__ = "mcp_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("sess"))
    client_name: Mapped[str] = mapped_column(String(255))
    client_version: Mapped[str] = mapped_column(String(64))
    protocol_version: Mapped[str] = mapped_column(String(64))
    requested_capabilities: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    granted_capabilities: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    tenant_id: Mapped[str] = mapped_column(String(64), default="default")
    status: Mapped[str] = mapped_column(String(32), default=SessionStatus.INITIALIZED.value)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: utcnow() + timedelta(hours=1))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("audit"))
    event_type: Mapped[str] = mapped_column(String(128))
    entity_type: Mapped[str] = mapped_column(String(128))
    entity_id: Mapped[str] = mapped_column(String(64))
    trace_id: Mapped[str] = mapped_column(String(64), default=lambda: new_id("tr"))
    actor: Mapped[str] = mapped_column(String(128), default="system")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("usr"))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255), default="")
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(32), default=UserRole.MEMBER.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    queries: Mapped[list[Query]] = relationship(back_populates="owner")
    api_tokens: Mapped[list[UserAPIToken]] = relationship(back_populates="user", cascade="all, delete-orphan")
    web_sessions: Mapped[list[UserWebSession]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserAPIToken(Base, TimestampMixin):
    __tablename__ = "user_api_tokens"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("tok"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    token_prefix: Mapped[str] = mapped_column(String(32))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="api_tokens")


class UserWebSession(Base):
    __tablename__ = "user_web_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("wsess"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    session_token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="web_sessions")
