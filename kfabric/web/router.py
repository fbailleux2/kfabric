from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from kfabric.api.deps import get_db, get_orchestrator
from kfabric.config import get_settings
from kfabric.domain.schemas import QueryCreate
from kfabric.infra.models import CandidateDocument, Corpus, FragmentCluster, FragmentSynthesis, Query
from kfabric.services.orchestrator import Orchestrator


router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _dashboard_context(db: Session, query_id: str) -> dict[str, object]:
    query = db.get(Query, query_id)
    if not query:
        raise ValueError(f"Query {query_id} not found")
    candidates = list(
        db.scalars(
            select(CandidateDocument)
            .where(CandidateDocument.query_id == query_id)
            .order_by(CandidateDocument.discovery_rank.asc())
        )
    )
    fragments = []
    for candidate in candidates:
        if candidate.collected_document and candidate.collected_document.parsed_document:
            fragments.extend(candidate.collected_document.parsed_document.fragments)
    clusters = list(
        db.scalars(select(FragmentCluster).where(FragmentCluster.query_id == query_id).order_by(FragmentCluster.created_at.desc()))
    )
    syntheses = list(
        db.scalars(select(FragmentSynthesis).where(FragmentSynthesis.query_id == query_id).order_by(FragmentSynthesis.created_at.desc()))
    )
    corpora = list(db.scalars(select(Corpus).where(Corpus.query_id == query_id).order_by(Corpus.created_at.desc())))
    accepted_count = sum(
        1
        for candidate in candidates
        if candidate.collected_document
        and candidate.collected_document.parsed_document
        and candidate.collected_document.parsed_document.decision
        and candidate.collected_document.parsed_document.decision.status in {"accepted", "manual_accepted"}
    )
    return {
        "query": query,
        "candidates": candidates,
        "fragments": fragments,
        "clusters": clusters,
        "syntheses": syntheses,
        "corpora": corpora,
        "accepted_count": accepted_count,
    }


@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    recent_queries = list(db.scalars(select(Query).order_by(Query.created_at.desc()).limit(8)))
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request,
            "settings": get_settings(),
            "recent_queries": recent_queries,
        },
    )


@router.get("/queries/{query_id}", response_class=HTMLResponse)
def query_dashboard(request: Request, query_id: str, db: Session = Depends(get_db)) -> HTMLResponse:
    context = _dashboard_context(db, query_id)
    context.update({"request": request, "settings": get_settings()})
    return templates.TemplateResponse(request=request, name="dashboard.html", context=context)


@router.post("/web/queries")
def create_query_from_form(
    theme: str = Form(default=""),
    question: str = Form(default=""),
    keywords: str = Form(default=""),
    preferred_domains: str = Form(default=""),
    excluded_domains: str = Form(default=""),
    document_types: str = Form(default=""),
    quality_target: str = Form(default="balanced"),
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> RedirectResponse:
    query = orchestrator.create_query(
        QueryCreate(
            theme=theme or None,
            question=question or None,
            keywords=_split_csv(keywords),
            language="fr",
            period=None,
            document_types=_split_csv(document_types),
            preferred_domains=_split_csv(preferred_domains),
            excluded_domains=_split_csv(excluded_domains),
            quality_target=quality_target,
        )
    )
    orchestrator.discover(query.id)
    return RedirectResponse(url=f"/queries/{query.id}", status_code=303)


@router.post("/web/candidates/{candidate_id}/collect")
def collect_candidate(candidate_id: str, orchestrator: Orchestrator = Depends(get_orchestrator)) -> RedirectResponse:
    collected = orchestrator.collect_candidate(candidate_id)
    return RedirectResponse(url=f"/queries/{collected.candidate.query_id}", status_code=303)


@router.post("/web/documents/{document_id}/analyze")
def analyze_document(document_id: str, orchestrator: Orchestrator = Depends(get_orchestrator)) -> RedirectResponse:
    result = orchestrator.analyze_document(document_id)
    query_id = result["parsed_document"].collected_document.candidate.query_id
    return RedirectResponse(url=f"/queries/{query_id}", status_code=303)


@router.post("/web/documents/{document_id}/accept")
def accept_document(document_id: str, orchestrator: Orchestrator = Depends(get_orchestrator)) -> RedirectResponse:
    decision = orchestrator.override_decision(document_id, accepted=True)
    query_id = decision.parsed_document.collected_document.candidate.query_id
    return RedirectResponse(url=f"/queries/{query_id}", status_code=303)


@router.post("/web/documents/{document_id}/reject")
def reject_document(document_id: str, orchestrator: Orchestrator = Depends(get_orchestrator)) -> RedirectResponse:
    decision = orchestrator.override_decision(document_id, accepted=False)
    query_id = decision.parsed_document.collected_document.candidate.query_id
    return RedirectResponse(url=f"/queries/{query_id}", status_code=303)


@router.post("/web/queries/{query_id}/consolidate")
def consolidate_query(query_id: str, orchestrator: Orchestrator = Depends(get_orchestrator)) -> RedirectResponse:
    orchestrator.consolidate_fragments(query_id)
    return RedirectResponse(url=f"/queries/{query_id}", status_code=303)


@router.post("/web/queries/{query_id}/syntheses")
def create_synthesis(query_id: str, orchestrator: Orchestrator = Depends(get_orchestrator)) -> RedirectResponse:
    orchestrator.create_synthesis(query_id)
    return RedirectResponse(url=f"/queries/{query_id}", status_code=303)


@router.post("/web/queries/{query_id}/corpora")
def build_corpus(query_id: str, orchestrator: Orchestrator = Depends(get_orchestrator)) -> RedirectResponse:
    orchestrator.build_corpus(query_id)
    return RedirectResponse(url=f"/queries/{query_id}", status_code=303)


@router.post("/web/corpora/{corpus_id}/prepare-index")
def prepare_index(
    corpus_id: str,
    orchestrator: Orchestrator = Depends(get_orchestrator),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    corpus = db.get(Corpus, corpus_id)
    if not corpus:
        raise ValueError(f"Corpus {corpus_id} not found")
    orchestrator.prepare_index(corpus_id)
    return RedirectResponse(url=f"/queries/{corpus.query_id}", status_code=303)
