from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from kfabric.api.deps import get_db, get_orchestrator, require_api_key
from kfabric.api.serializers import (
    serialize_analysis,
    serialize_candidate,
    serialize_collect,
    serialize_corpus,
    serialize_cluster,
    serialize_decision_override,
    serialize_fragment,
    serialize_prepare_index,
    serialize_query,
    serialize_synthesis,
)
from kfabric.domain.schemas import (
    AnalyzeDocumentResponse,
    CandidateResponse,
    CollectCandidateResponse,
    CorpusResponse,
    DecisionOverrideResponse,
    FragmentClusterResponse,
    FragmentConsolidateRequest,
    FragmentResponse,
    PrepareIndexResponse,
    QueryCreate,
    QueryResponse,
    SynthesisCreateRequest,
    SynthesisResponse,
)
from kfabric.infra.models import Corpus
from kfabric.services.orchestrator import Orchestrator


router = APIRouter(tags=["queries"], dependencies=[Depends(require_api_key)])


@router.post("/queries", response_model=QueryResponse)
def create_query(payload: QueryCreate, orchestrator: Orchestrator = Depends(get_orchestrator)) -> QueryResponse:
    return serialize_query(orchestrator.create_query(payload))


@router.get("/queries/{query_id}", response_model=QueryResponse)
def get_query(query_id: str, orchestrator: Orchestrator = Depends(get_orchestrator)) -> QueryResponse:
    return serialize_query(orchestrator.get_query(query_id))


@router.post("/queries/{query_id}:discover", response_model=list[CandidateResponse])
def discover_query(query_id: str, orchestrator: Orchestrator = Depends(get_orchestrator)) -> list[CandidateResponse]:
    return [serialize_candidate(candidate) for candidate in orchestrator.discover(query_id)]


@router.get("/queries/{query_id}/candidates", response_model=list[CandidateResponse])
def list_candidates(query_id: str, orchestrator: Orchestrator = Depends(get_orchestrator)) -> list[CandidateResponse]:
    return [serialize_candidate(candidate) for candidate in orchestrator.list_candidates(query_id)]


@router.post("/candidates/{candidate_id}:collect", response_model=CollectCandidateResponse)
def collect_candidate(candidate_id: str, orchestrator: Orchestrator = Depends(get_orchestrator)) -> CollectCandidateResponse:
    collected = orchestrator.collect_candidate(candidate_id)
    return serialize_collect(candidate_id, collected)


@router.post("/documents/{document_id}:analyze", response_model=AnalyzeDocumentResponse)
def analyze_document(document_id: str, orchestrator: Orchestrator = Depends(get_orchestrator)) -> AnalyzeDocumentResponse:
    result = orchestrator.analyze_document(document_id)
    return serialize_analysis(result["parsed_document"], result["score"], result["decision"], result["fragments"])


@router.post("/documents/{document_id}:accept", response_model=DecisionOverrideResponse)
def accept_document(document_id: str, orchestrator: Orchestrator = Depends(get_orchestrator)) -> DecisionOverrideResponse:
    decision = orchestrator.override_decision(document_id, accepted=True)
    return serialize_decision_override(document_id, decision)


@router.post("/documents/{document_id}:reject", response_model=DecisionOverrideResponse)
def reject_document(document_id: str, orchestrator: Orchestrator = Depends(get_orchestrator)) -> DecisionOverrideResponse:
    decision = orchestrator.override_decision(document_id, accepted=False)
    return serialize_decision_override(document_id, decision)


@router.get("/fragments", response_model=list[FragmentResponse])
def list_fragments(query_id: str | None = None, orchestrator: Orchestrator = Depends(get_orchestrator)) -> list[FragmentResponse]:
    return [serialize_fragment(fragment) for fragment in orchestrator.list_fragments(query_id)]


@router.post("/fragments:consolidate", response_model=list[FragmentClusterResponse])
def consolidate_fragments(
    payload: FragmentConsolidateRequest,
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> list[FragmentClusterResponse]:
    clusters = orchestrator.consolidate_fragments(payload.query_id)
    return [serialize_cluster(cluster) for cluster in clusters]


@router.post("/syntheses", response_model=SynthesisResponse)
def create_synthesis(
    payload: SynthesisCreateRequest,
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> SynthesisResponse:
    return serialize_synthesis(orchestrator.create_synthesis(payload.query_id, payload.fragment_ids))


@router.post("/queries/{query_id}:build-corpus", response_model=CorpusResponse)
def build_corpus(query_id: str, orchestrator: Orchestrator = Depends(get_orchestrator)) -> CorpusResponse:
    return serialize_corpus(orchestrator.build_corpus(query_id))


@router.get("/corpora/{corpus_id}", response_model=CorpusResponse)
def get_corpus(corpus_id: str, db: Session = Depends(get_db)) -> CorpusResponse:
    corpus = db.get(Corpus, corpus_id)
    if not corpus:
        raise ValueError(f"Corpus {corpus_id} not found")
    return serialize_corpus(corpus)


@router.post("/corpora/{corpus_id}:prepare-index", response_model=PrepareIndexResponse)
def prepare_index(corpus_id: str, orchestrator: Orchestrator = Depends(get_orchestrator), db: Session = Depends(get_db)) -> PrepareIndexResponse:
    payload = orchestrator.prepare_index(corpus_id)
    corpus = db.get(Corpus, corpus_id)
    if not corpus:
        raise ValueError(f"Corpus {corpus_id} not found")
    return serialize_prepare_index(corpus, payload)
