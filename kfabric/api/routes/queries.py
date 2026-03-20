from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from kfabric.api.deps import get_db, get_orchestrator, get_runtime_settings, require_authenticated_principal
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
    serialize_tool_run,
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
    ToolRunResponse,
)
from kfabric.mcp.registry import enqueue_tool
from kfabric.services.corpus_export import export_filename, render_corpus_html
from kfabric.services.orchestrator import Orchestrator


router = APIRouter(tags=["queries"], dependencies=[Depends(require_authenticated_principal)])


@router.post("/queries", response_model=QueryResponse)
def create_query(payload: QueryCreate, orchestrator: Orchestrator = Depends(get_orchestrator)) -> QueryResponse:
    return serialize_query(orchestrator.create_query(payload))


@router.get("/queries/{query_id}", response_model=QueryResponse)
def get_query(query_id: str, orchestrator: Orchestrator = Depends(get_orchestrator)) -> QueryResponse:
    return serialize_query(orchestrator.get_query(query_id))


@router.post("/queries/{query_id}:discover", response_model=list[CandidateResponse])
def discover_query(query_id: str, orchestrator: Orchestrator = Depends(get_orchestrator)) -> list[CandidateResponse]:
    return [serialize_candidate(candidate) for candidate in orchestrator.discover(query_id)]


@router.post("/queries/{query_id}:discover-async", response_model=ToolRunResponse)
def discover_query_async(
    query_id: str,
    db=Depends(get_db),
    settings=Depends(get_runtime_settings),
    principal=Depends(require_authenticated_principal),
) -> ToolRunResponse:
    run = enqueue_tool(db, settings, principal, "discover_documents", {"query_id": query_id})
    return serialize_tool_run(run)


@router.get("/queries/{query_id}/candidates", response_model=list[CandidateResponse])
def list_candidates(query_id: str, orchestrator: Orchestrator = Depends(get_orchestrator)) -> list[CandidateResponse]:
    return [serialize_candidate(candidate) for candidate in orchestrator.list_candidates(query_id)]


@router.post("/candidates/{candidate_id}:collect", response_model=CollectCandidateResponse)
def collect_candidate(candidate_id: str, orchestrator: Orchestrator = Depends(get_orchestrator)) -> CollectCandidateResponse:
    collected = orchestrator.collect_candidate(candidate_id)
    return serialize_collect(candidate_id, collected)


@router.post("/candidates/{candidate_id}:collect-async", response_model=ToolRunResponse)
def collect_candidate_async(
    candidate_id: str,
    db=Depends(get_db),
    settings=Depends(get_runtime_settings),
    principal=Depends(require_authenticated_principal),
) -> ToolRunResponse:
    run = enqueue_tool(db, settings, principal, "collect_candidate", {"candidate_id": candidate_id})
    return serialize_tool_run(run)


@router.post("/documents/{document_id}:analyze", response_model=AnalyzeDocumentResponse)
def analyze_document(document_id: str, orchestrator: Orchestrator = Depends(get_orchestrator)) -> AnalyzeDocumentResponse:
    result = orchestrator.analyze_document(document_id)
    return serialize_analysis(result["parsed_document"], result["score"], result["decision"], result["fragments"])


@router.post("/documents/{document_id}:analyze-async", response_model=ToolRunResponse)
def analyze_document_async(
    document_id: str,
    db=Depends(get_db),
    settings=Depends(get_runtime_settings),
    principal=Depends(require_authenticated_principal),
) -> ToolRunResponse:
    run = enqueue_tool(db, settings, principal, "analyze_document", {"document_id": document_id})
    return serialize_tool_run(run)


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


@router.post("/fragments:consolidate-async", response_model=ToolRunResponse)
def consolidate_fragments_async(
    payload: FragmentConsolidateRequest,
    db=Depends(get_db),
    settings=Depends(get_runtime_settings),
    principal=Depends(require_authenticated_principal),
) -> ToolRunResponse:
    run = enqueue_tool(db, settings, principal, "consolidate_fragments", {"query_id": payload.query_id})
    return serialize_tool_run(run)


@router.post("/syntheses", response_model=SynthesisResponse)
def create_synthesis(
    payload: SynthesisCreateRequest,
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> SynthesisResponse:
    return serialize_synthesis(orchestrator.create_synthesis(payload.query_id, payload.fragment_ids))


@router.post("/syntheses:async", response_model=ToolRunResponse)
def create_synthesis_async(
    payload: SynthesisCreateRequest,
    db=Depends(get_db),
    settings=Depends(get_runtime_settings),
    principal=Depends(require_authenticated_principal),
) -> ToolRunResponse:
    run = enqueue_tool(
        db,
        settings,
        principal,
        "generate_fragment_synthesis",
        {"query_id": payload.query_id, "fragment_ids": payload.fragment_ids},
    )
    return serialize_tool_run(run)


@router.post("/queries/{query_id}:build-corpus", response_model=CorpusResponse)
def build_corpus(query_id: str, orchestrator: Orchestrator = Depends(get_orchestrator)) -> CorpusResponse:
    return serialize_corpus(orchestrator.build_corpus(query_id))


@router.post("/queries/{query_id}:build-corpus-async", response_model=ToolRunResponse)
def build_corpus_async(
    query_id: str,
    db=Depends(get_db),
    settings=Depends(get_runtime_settings),
    principal=Depends(require_authenticated_principal),
) -> ToolRunResponse:
    run = enqueue_tool(db, settings, principal, "build_corpus", {"query_id": query_id})
    return serialize_tool_run(run)


@router.get("/corpora/{corpus_id}:export")
def export_corpus(
    corpus_id: str,
    format: str = Query(default="markdown", pattern="^(markdown|html)$"),
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> Response:
    corpus = orchestrator.get_corpus(corpus_id)

    if format == "html":
        return Response(
            content=render_corpus_html(corpus),
            media_type="text/html",
            headers={"Content-Disposition": f'inline; filename="{export_filename(corpus, "html")}"'},
        )

    return Response(
        content=corpus.corpus_markdown,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{export_filename(corpus, "md")}"'},
    )


@router.get("/corpora/{corpus_id}", response_model=CorpusResponse)
def get_corpus(corpus_id: str, orchestrator: Orchestrator = Depends(get_orchestrator)) -> CorpusResponse:
    corpus = orchestrator.get_corpus(corpus_id)
    return serialize_corpus(corpus)


@router.post("/corpora/{corpus_id}:prepare-index", response_model=PrepareIndexResponse)
def prepare_index(corpus_id: str, orchestrator: Orchestrator = Depends(get_orchestrator)) -> PrepareIndexResponse:
    payload = orchestrator.prepare_index(corpus_id)
    corpus = orchestrator.get_corpus(corpus_id)
    return serialize_prepare_index(corpus, payload)


@router.post("/corpora/{corpus_id}:prepare-index-async", response_model=ToolRunResponse)
def prepare_index_async(
    corpus_id: str,
    db=Depends(get_db),
    settings=Depends(get_runtime_settings),
    principal=Depends(require_authenticated_principal),
) -> ToolRunResponse:
    run = enqueue_tool(db, settings, principal, "prepare_index", {"corpus_id": corpus_id})
    return serialize_tool_run(run)
