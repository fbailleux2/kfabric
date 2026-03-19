"""initial schema

Revision ID: 20260318_0001
Revises:
Create Date: 2026-03-18 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260318_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "queries",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("theme", sa.String(length=255), nullable=True),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("period", sa.String(length=64), nullable=True),
        sa.Column("document_types", sa.JSON(), nullable=False),
        sa.Column("preferred_domains", sa.JSON(), nullable=False),
        sa.Column("excluded_domains", sa.JSON(), nullable=False),
        sa.Column("quality_target", sa.String(length=32), nullable=False),
        sa.Column("expansion_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "query_expansions",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("query_id", sa.String(length=32), nullable=False),
        sa.Column("original_query", sa.Text(), nullable=False),
        sa.Column("expanded_query", sa.Text(), nullable=False),
        sa.Column("expansion_terms", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["query_id"], ["queries.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "candidate_documents",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("query_id", sa.String(length=32), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("document_type", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("discovery_rank", sa.Integer(), nullable=False),
        sa.Column("discovery_source", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["query_id"], ["queries.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "collected_documents",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("candidate_id", sa.String(length=32), nullable=False),
        sa.Column("raw_content", sa.Text(), nullable=False),
        sa.Column("raw_hash", sa.String(length=64), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("collection_method", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidate_documents.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("candidate_id"),
    )
    op.create_table(
        "parsed_documents",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("collected_document_id", sa.String(length=32), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("normalized_hash", sa.String(length=64), nullable=False),
        sa.Column("extracted_title", sa.Text(), nullable=False),
        sa.Column("headings", sa.JSON(), nullable=False),
        sa.Column("text_length", sa.Integer(), nullable=False),
        sa.Column("extraction_method", sa.String(length=64), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["collected_document_id"], ["collected_documents.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("collected_document_id"),
    )
    op.create_table(
        "document_scores",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("parsed_document_id", sa.String(length=32), nullable=False),
        sa.Column("global_score", sa.Integer(), nullable=False),
        sa.Column("relevance_score", sa.Integer(), nullable=False),
        sa.Column("source_quality_score", sa.Integer(), nullable=False),
        sa.Column("documentary_value_score", sa.Integer(), nullable=False),
        sa.Column("freshness_score", sa.Integer(), nullable=False),
        sa.Column("exploitability_score", sa.Integer(), nullable=False),
        sa.Column("originality_score", sa.Integer(), nullable=False),
        sa.Column("scoring_notes", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["parsed_document_id"], ["parsed_documents.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("parsed_document_id"),
    )
    op.create_table(
        "document_decisions",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("parsed_document_id", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("threshold_applied", sa.Integer(), nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("has_salvaged_fragments", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["parsed_document_id"], ["parsed_documents.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("parsed_document_id"),
    )
    op.create_table(
        "fragment_clusters",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("query_id", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("cluster_summary", sa.Text(), nullable=False),
        sa.Column("contribution_score", sa.Float(), nullable=False),
        sa.Column("fragment_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["query_id"], ["queries.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "salvaged_fragments",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("parsed_document_id", sa.String(length=32), nullable=False),
        sa.Column("query_id", sa.String(length=32), nullable=False),
        sa.Column("fragment_text", sa.Text(), nullable=False),
        sa.Column("fragment_type", sa.String(length=32), nullable=False),
        sa.Column("fragment_score", sa.Integer(), nullable=False),
        sa.Column("confidence_level", sa.Float(), nullable=False),
        sa.Column("verification_status", sa.String(length=32), nullable=False),
        sa.Column("included_in_synthesis", sa.Boolean(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["parsed_document_id"], ["parsed_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["query_id"], ["queries.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "fragment_syntheses",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("query_id", sa.String(length=32), nullable=False),
        sa.Column("theme", sa.String(length=255), nullable=False),
        sa.Column("synthesis_markdown", sa.Text(), nullable=False),
        sa.Column("generated_from_n_fragments", sa.Integer(), nullable=False),
        sa.Column("generated_from_n_rejected_docs", sa.Integer(), nullable=False),
        sa.Column("overall_confidence", sa.Float(), nullable=False),
        sa.Column("index_priority", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["query_id"], ["queries.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "corpora",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("query_id", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("corpus_markdown", sa.Text(), nullable=False),
        sa.Column("accepted_document_ids", sa.JSON(), nullable=False),
        sa.Column("synthesis_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("index_ready", sa.Boolean(), nullable=False),
        sa.Column("artifact_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["query_id"], ["queries.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "tool_runs",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("tool_name", sa.String(length=255), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("input_payload", sa.JSON(), nullable=False),
        sa.Column("output_payload", sa.JSON(), nullable=True),
        sa.Column("error_payload", sa.JSON(), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "mcp_sessions",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("client_name", sa.String(length=255), nullable=False),
        sa.Column("client_version", sa.String(length=64), nullable=False),
        sa.Column("protocol_version", sa.String(length=64), nullable=False),
        sa.Column("requested_capabilities", sa.JSON(), nullable=False),
        sa.Column("granted_capabilities", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("entity_type", sa.String(length=128), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_index("ix_candidate_documents_query_id", "candidate_documents", ["query_id"])
    op.create_index("ix_query_expansions_query_id", "query_expansions", ["query_id"])
    op.create_index("ix_fragment_clusters_query_id", "fragment_clusters", ["query_id"])
    op.create_index("ix_salvaged_fragments_query_id", "salvaged_fragments", ["query_id"])
    op.create_index("ix_salvaged_fragments_parsed_document_id", "salvaged_fragments", ["parsed_document_id"])
    op.create_index("ix_fragment_syntheses_query_id", "fragment_syntheses", ["query_id"])
    op.create_index("ix_corpora_query_id", "corpora", ["query_id"])
    op.create_index("ix_tool_runs_tool_name", "tool_runs", ["tool_name"])
    op.create_index("ix_audit_events_entity_id", "audit_events", ["entity_id"])
    op.create_index("ix_audit_events_trace_id", "audit_events", ["trace_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_trace_id", table_name="audit_events")
    op.drop_index("ix_audit_events_entity_id", table_name="audit_events")
    op.drop_index("ix_tool_runs_tool_name", table_name="tool_runs")
    op.drop_index("ix_corpora_query_id", table_name="corpora")
    op.drop_index("ix_fragment_syntheses_query_id", table_name="fragment_syntheses")
    op.drop_index("ix_salvaged_fragments_parsed_document_id", table_name="salvaged_fragments")
    op.drop_index("ix_salvaged_fragments_query_id", table_name="salvaged_fragments")
    op.drop_index("ix_fragment_clusters_query_id", table_name="fragment_clusters")
    op.drop_index("ix_query_expansions_query_id", table_name="query_expansions")
    op.drop_index("ix_candidate_documents_query_id", table_name="candidate_documents")

    op.drop_table("audit_events")
    op.drop_table("mcp_sessions")
    op.drop_table("tool_runs")
    op.drop_table("corpora")
    op.drop_table("fragment_syntheses")
    op.drop_table("salvaged_fragments")
    op.drop_table("fragment_clusters")
    op.drop_table("document_decisions")
    op.drop_table("document_scores")
    op.drop_table("parsed_documents")
    op.drop_table("collected_documents")
    op.drop_table("candidate_documents")
    op.drop_table("query_expansions")
    op.drop_table("queries")
