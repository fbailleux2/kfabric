from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from kfabric.config import AppSettings
from kfabric.domain.enums import (
    CandidateStatus,
    CorpusStatus,
    DocumentDecisionStatus,
    QueryStatus,
)
from kfabric.domain.schemas import QueryCreate
from kfabric.infra.models import (
    CandidateDocument,
    CollectedDocument,
    Corpus,
    DocumentDecision,
    DocumentScore,
    FragmentCluster,
    FragmentSynthesis,
    ParsedDocument,
    Query,
    QueryExpansion,
    SalvagedFragment,
)
from kfabric.services.audit_trail import record_audit_event
from kfabric.services.corpus_builder import build_corpus_markdown
from kfabric.services.deduplication import cluster_fragments
from kfabric.services.discovery_engine import discover_candidates
from kfabric.services.document_collector import collect_document
from kfabric.services.document_parser import parse_document
from kfabric.services.document_scoring import score_document
from kfabric.services.fragment_salvage import salvage_fragments
from kfabric.services.fragment_synthesis import synthesize_fragments
from kfabric.services.marginal_contribution import marginal_contribution
from kfabric.services.query_expansion import expand_query
from kfabric.services.rag_prep import prepare_index_artifact


@dataclass
class Orchestrator:
    session: Session
    settings: AppSettings

    def create_query(self, payload: QueryCreate) -> Query:
        expansion = expand_query(payload.theme, payload.question, payload.keywords)
        query = Query(
            theme=payload.theme,
            question=payload.question,
            keywords=payload.keywords,
            language=payload.language,
            period=payload.period,
            document_types=payload.document_types,
            preferred_domains=payload.preferred_domains,
            excluded_domains=payload.excluded_domains,
            quality_target=payload.quality_target,
            expansion_text=str(expansion["expanded_query"]),
            status=QueryStatus.CREATED.value,
        )
        self.session.add(query)
        self.session.flush()
        query_expansion = QueryExpansion(
            query_id=query.id,
            original_query=str(expansion["original_query"]),
            expanded_query=str(expansion["expanded_query"]),
            expansion_terms=list(expansion["expansion_terms"]),
        )
        self.session.add(query_expansion)
        record_audit_event(
            self.session,
            event_type="query.created",
            entity_type="query",
            entity_id=query.id,
            trace_id=query.trace_id,
            payload={"keywords": payload.keywords},
        )
        self.session.commit()
        self.session.refresh(query)
        return query

    def get_query(self, query_id: str) -> Query:
        query = self.session.get(Query, query_id)
        if not query:
            raise ValueError(f"Query {query_id} not found")
        return query

    def discover(self, query_id: str) -> list[CandidateDocument]:
        query = self.get_query(query_id)
        created_candidates: list[CandidateDocument] = []
        for candidate_payload in discover_candidates(query, settings=self.settings):
            candidate = CandidateDocument(query_id=query.id, **candidate_payload)
            self.session.add(candidate)
            created_candidates.append(candidate)
        query.status = QueryStatus.DISCOVERED.value
        record_audit_event(
            self.session,
            event_type="query.discovered",
            entity_type="query",
            entity_id=query.id,
            trace_id=query.trace_id,
            payload={"candidate_count": len(created_candidates)},
        )
        self.session.commit()
        return created_candidates

    def list_candidates(self, query_id: str) -> list[CandidateDocument]:
        return list(self.session.scalars(select(CandidateDocument).where(CandidateDocument.query_id == query_id).order_by(CandidateDocument.discovery_rank)))

    def collect_candidate(self, candidate_id: str) -> CollectedDocument:
        candidate = self.session.get(CandidateDocument, candidate_id)
        if not candidate:
            raise ValueError(f"Candidate {candidate_id} not found")
        query = self.session.get(Query, candidate.query_id)
        if not query:
            raise ValueError(f"Query {candidate.query_id} not found")
        payload = collect_document(candidate, query, self.settings)
        collected = CollectedDocument(candidate_id=candidate.id, **payload)
        self.session.add(collected)
        candidate.status = CandidateStatus.COLLECTED.value
        candidate.collected_at = collected.created_at
        record_audit_event(
            self.session,
            event_type="candidate.collected",
            entity_type="candidate_document",
            entity_id=candidate.id,
            trace_id=collected.trace_id,
            payload={"collection_method": collected.collection_method},
        )
        self.session.commit()
        self.session.refresh(collected)
        return collected

    def analyze_document(self, document_id: str) -> dict[str, Any]:
        collected = self.session.get(CollectedDocument, document_id)
        if not collected:
            raise ValueError(f"Collected document {document_id} not found")
        candidate = collected.candidate
        query = candidate.query
        parsed_payload = parse_document(collected.raw_content, collected.content_type, candidate)
        parsed = ParsedDocument(collected_document_id=collected.id, **parsed_payload)
        self.session.add(parsed)
        self.session.flush()

        query_terms = query.expansion_text.split() if query.expansion_text else []
        score_payload = score_document(parsed.normalized_text, candidate.domain, query_terms, parsed.headings, self.settings)
        score = DocumentScore(parsed_document_id=parsed.id, **score_payload)
        self.session.add(score)
        self.session.flush()

        fragments_payload = salvage_fragments(parsed.normalized_text, query_terms, self.settings)
        saved_fragments: list[SalvagedFragment] = []
        for fragment_payload in fragments_payload:
            fragment = SalvagedFragment(
                parsed_document_id=parsed.id,
                query_id=query.id,
                **fragment_payload,
            )
            self.session.add(fragment)
            saved_fragments.append(fragment)
        self.session.flush()

        decision_status, rejection_reason = self._decide_document(score.global_score, saved_fragments)
        decision = DocumentDecision(
            parsed_document_id=parsed.id,
            status=decision_status,
            threshold_applied=self.settings.accept_threshold,
            rejection_reason=rejection_reason,
            justification=self._build_justification(score.global_score, decision_status, saved_fragments),
            has_salvaged_fragments=bool(saved_fragments),
        )
        self.session.add(decision)
        query.status = QueryStatus.PROCESSING.value
        record_audit_event(
            self.session,
            event_type="document.analyzed",
            entity_type="parsed_document",
            entity_id=parsed.id,
            trace_id=parsed.trace_id,
            payload={
                "decision_status": decision_status,
                "global_score": score.global_score,
                "fragments": len(saved_fragments),
            },
        )
        self.session.commit()
        return {
            "parsed_document": parsed,
            "score": score,
            "decision": decision,
            "fragments": saved_fragments,
        }

    def override_decision(self, parsed_document_id: str, accepted: bool) -> DocumentDecision:
        parsed = self.session.get(ParsedDocument, parsed_document_id)
        if not parsed or not parsed.decision:
            raise ValueError(f"Parsed document {parsed_document_id} not found")
        parsed.decision.status = (
            DocumentDecisionStatus.MANUAL_ACCEPTED.value if accepted else DocumentDecisionStatus.MANUAL_REJECTED.value
        )
        parsed.decision.justification = "Manual override requested via API"
        record_audit_event(
            self.session,
            event_type="document.override",
            entity_type="parsed_document",
            entity_id=parsed.id,
            trace_id=parsed.trace_id,
            payload={"accepted": accepted},
        )
        self.session.commit()
        self.session.refresh(parsed.decision)
        return parsed.decision

    def list_fragments(self, query_id: str | None = None) -> list[SalvagedFragment]:
        stmt = select(SalvagedFragment)
        if query_id:
            stmt = stmt.where(SalvagedFragment.query_id == query_id)
        return list(self.session.scalars(stmt.order_by(SalvagedFragment.created_at.desc())))

    def consolidate_fragments(self, query_id: str) -> list[FragmentCluster]:
        fragments = self.list_fragments(query_id)
        fragment_dicts = [
            {
                "id": fragment.id,
                "fragment_text": fragment.fragment_text,
                "fragment_type": fragment.fragment_type,
                "fragment_score": fragment.fragment_score,
            }
            for fragment in fragments
        ]
        clusters_payload = cluster_fragments(fragment_dicts)
        existing = list(self.session.scalars(select(FragmentCluster).where(FragmentCluster.query_id == query_id)))
        for cluster in existing:
            self.session.delete(cluster)
        query = self.get_query(query_id)
        accepted_texts = [
            parsed.normalized_text
            for parsed in self.session.scalars(
                select(ParsedDocument)
                .join(DocumentDecision)
                .join(CollectedDocument)
                .join(CandidateDocument)
                .where(
                    CandidateDocument.query_id == query_id,
                    DocumentDecision.status.in_(
                        [
                            DocumentDecisionStatus.ACCEPTED.value,
                            DocumentDecisionStatus.MANUAL_ACCEPTED.value,
                        ]
                    ),
                )
            )
        ]
        created_clusters: list[FragmentCluster] = []
        for payload in clusters_payload:
            texts = [item["fragment_text"] for item in payload["items"]]
            summary = " ".join(texts[:2])[:220]
            contribution = marginal_contribution(summary, accepted_texts)
            cluster = FragmentCluster(
                query_id=query_id,
                label=payload["label"],
                cluster_summary=summary,
                contribution_score=contribution,
                fragment_ids=[item["id"] for item in payload["items"]],
            )
            self.session.add(cluster)
            created_clusters.append(cluster)
        record_audit_event(
            self.session,
            event_type="fragments.consolidated",
            entity_type="query",
            entity_id=query.id,
            trace_id=query.trace_id,
            payload={"cluster_count": len(created_clusters)},
        )
        self.session.commit()
        return created_clusters

    def create_synthesis(self, query_id: str, fragment_ids: list[str] | None = None) -> FragmentSynthesis:
        query = self.get_query(query_id)
        stmt = select(SalvagedFragment).where(SalvagedFragment.query_id == query_id)
        if fragment_ids:
            stmt = stmt.where(SalvagedFragment.id.in_(fragment_ids))
        fragments = list(self.session.scalars(stmt))
        synthesis_markdown, overall_confidence = synthesize_fragments(query.theme or query.question or query.id, [
            {
                "fragment_text": fragment.fragment_text,
                "fragment_type": fragment.fragment_type,
                "fragment_score": fragment.fragment_score,
                "confidence_level": fragment.confidence_level,
                "verification_status": fragment.verification_status,
            }
            for fragment in fragments
        ])
        rejected_docs = {
            fragment.parsed_document_id
            for fragment in fragments
            if fragment.parsed_document.decision
            and fragment.parsed_document.decision.status
            in [DocumentDecisionStatus.REJECTED.value, DocumentDecisionStatus.REJECTED_WITH_SALVAGE.value]
        }
        synthesis = FragmentSynthesis(
            query_id=query.id,
            theme=query.theme or query.question or "Synthese documentaire",
            synthesis_markdown=synthesis_markdown,
            generated_from_n_fragments=len(fragments),
            generated_from_n_rejected_docs=len(rejected_docs),
            overall_confidence=overall_confidence,
            index_priority=0.25 if self.settings.secure_mode else 0.4,
        )
        self.session.add(synthesis)
        for fragment in fragments:
            fragment.included_in_synthesis = True
        record_audit_event(
            self.session,
            event_type="synthesis.created",
            entity_type="query",
            entity_id=query.id,
            trace_id=query.trace_id,
            payload={"fragment_count": len(fragments)},
        )
        self.session.commit()
        self.session.refresh(synthesis)
        return synthesis

    def build_corpus(self, query_id: str) -> Corpus:
        query = self.get_query(query_id)
        accepted_documents = []
        accepted_ids = []
        stmt = (
            select(ParsedDocument, DocumentScore, DocumentDecision, CandidateDocument)
            .join(DocumentScore, DocumentScore.parsed_document_id == ParsedDocument.id)
            .join(DocumentDecision, DocumentDecision.parsed_document_id == ParsedDocument.id)
            .join(CollectedDocument, CollectedDocument.id == ParsedDocument.collected_document_id)
            .join(CandidateDocument, CandidateDocument.id == CollectedDocument.candidate_id)
            .where(
                CandidateDocument.query_id == query_id,
                DocumentDecision.status.in_(
                    [DocumentDecisionStatus.ACCEPTED.value, DocumentDecisionStatus.MANUAL_ACCEPTED.value]
                ),
            )
        )
        for parsed, score, _decision, candidate in self.session.execute(stmt):
            accepted_documents.append(
                {
                    "id": parsed.id,
                    "title": parsed.extracted_title or candidate.title,
                    "source_url": candidate.source_url,
                    "score": str(score.global_score),
                }
            )
            accepted_ids.append(parsed.id)
        syntheses = list(self.session.scalars(select(FragmentSynthesis).where(FragmentSynthesis.query_id == query_id)))
        synthesis_payload = [
            {"id": synthesis.id, "theme": synthesis.theme, "overall_confidence": str(synthesis.overall_confidence)}
            for synthesis in syntheses
        ]
        corpus_markdown = build_corpus_markdown(query.theme or query.question or query.id, accepted_documents, synthesis_payload)
        corpus = Corpus(
            query_id=query_id,
            title=query.theme or query.question or f"Corpus {query.id}",
            corpus_markdown=corpus_markdown,
            accepted_document_ids=accepted_ids,
            synthesis_ids=[synthesis.id for synthesis in syntheses],
            status=CorpusStatus.READY.value,
        )
        self.session.add(corpus)
        query.status = QueryStatus.CONSOLIDATED.value
        record_audit_event(
            self.session,
            event_type="corpus.created",
            entity_type="query",
            entity_id=query.id,
            trace_id=query.trace_id,
            payload={"accepted_documents": len(accepted_ids), "syntheses": len(syntheses)},
        )
        self.session.commit()
        self.session.refresh(corpus)
        return corpus

    def prepare_index(self, corpus_id: str) -> dict[str, Any]:
        corpus = self.session.get(Corpus, corpus_id)
        if not corpus:
            raise ValueError(f"Corpus {corpus_id} not found")
        result = prepare_index_artifact(corpus.id, corpus.corpus_markdown, self.settings)
        corpus.status = CorpusStatus.INDEX_PREPARED.value
        corpus.index_ready = True
        corpus.artifact_path = str(result["artifact_path"])
        query = self.get_query(corpus.query_id)
        query.status = QueryStatus.INDEX_READY.value
        record_audit_event(
            self.session,
            event_type="corpus.index_prepared",
            entity_type="corpus",
            entity_id=corpus.id,
            trace_id=query.trace_id,
            payload=result,
        )
        self.session.commit()
        return result

    def _decide_document(self, global_score: int, fragments: list[SalvagedFragment]) -> tuple[str, str | None]:
        if global_score >= self.settings.accept_threshold:
            return DocumentDecisionStatus.ACCEPTED.value, None
        if global_score >= self.settings.salvage_threshold and fragments:
            return DocumentDecisionStatus.REJECTED_WITH_SALVAGE.value, "Global quality below acceptance threshold but useful fragments detected"
        if fragments:
            return DocumentDecisionStatus.REJECTED_WITH_SALVAGE.value, "Fragments retained from weak document"
        return DocumentDecisionStatus.REJECTED.value, "Low quality and no useful fragment found"

    @staticmethod
    def _build_justification(global_score: int, decision_status: str, fragments: list[SalvagedFragment]) -> str:
        if decision_status == DocumentDecisionStatus.ACCEPTED.value:
            return f"Document accepted with score {global_score}/100"
        if fragments:
            return f"Document rejected globally ({global_score}/100) but {len(fragments)} fragments were salvaged"
        return f"Document rejected with score {global_score}/100 and no salvageable fragment"
