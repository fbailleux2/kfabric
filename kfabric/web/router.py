from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from kfabric.api.deps import WEB_SESSION_COOKIE, get_db, get_orchestrator, require_web_session
from kfabric.config import get_settings
from kfabric.domain.schemas import QueryCreate
from kfabric.infra.models import CandidateDocument, Corpus, FragmentCluster, FragmentSynthesis
from kfabric.services.auth_service import authenticate_user, bootstrap_admin, create_web_session, revoke_web_session
from kfabric.services.corpus_export import export_filename, render_corpus_html
from kfabric.services.orchestrator import Orchestrator


router = APIRouter(include_in_schema=False, dependencies=[Depends(require_web_session)])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _dashboard_context(db: Session, orchestrator: Orchestrator, query_id: str) -> dict[str, object]:
    query = orchestrator.get_query(query_id)
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


@router.get("/auth", response_class=HTMLResponse)
def auth_page(request: Request) -> HTMLResponse:
    settings = get_settings()
    if getattr(request.state, "web_authenticated", False):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="auth.html",
        context={
            "request": request,
            "settings": settings,
            "next_path": request.query_params.get("next") or "/",
            "error_message": None,
            "bootstrap_required": getattr(request.state, "bootstrap_required", False),
        },
    )


@router.post("/web/auth/session")
def create_password_session(
    request: Request,
    email: str = Form(default=""),
    password: str = Form(default=""),
    next_path: str = Form(default="/"),
    db: Session = Depends(get_db),
) -> Response:
    settings = get_settings()
    if getattr(request.state, "bootstrap_required", False):
        return templates.TemplateResponse(
            request=request,
            name="auth.html",
            context={
                "request": request,
                "settings": settings,
                "next_path": next_path or "/",
                "error_message": "Un administrateur initial doit d'abord être créé",
                "bootstrap_required": True,
            },
            status_code=401,
        )

    user = authenticate_user(db, email=email, password=password)
    if user is None:
        return templates.TemplateResponse(
            request=request,
            name="auth.html",
            context={
                "request": request,
                "settings": settings,
                "next_path": next_path or "/",
                "error_message": "Identifiants invalides",
                "bootstrap_required": False,
            },
            status_code=401,
        )

    web_session, raw_token = create_web_session(db, user=user, ttl_seconds=settings.session_ttl_seconds)
    db.commit()
    response = RedirectResponse(url=next_path or "/", status_code=303)
    response.set_cookie(
        WEB_SESSION_COOKIE,
        raw_token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        max_age=settings.session_ttl_seconds,
    )
    return response


@router.post("/web/auth/logout")
def clear_web_session(request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    session_token = request.cookies.get(WEB_SESSION_COOKIE)
    if session_token:
        revoke_web_session(db, session_token)
        db.commit()
    response = RedirectResponse(url="/auth", status_code=303)
    response.delete_cookie(WEB_SESSION_COOKIE, httponly=True, samesite="strict")
    return response


@router.post("/web/auth/bootstrap")
def bootstrap_web_admin(
    request: Request,
    email: str = Form(default=""),
    password: str = Form(default=""),
    display_name: str = Form(default=""),
    next_path: str = Form(default="/"),
    db: Session = Depends(get_db),
) -> Response:
    settings = get_settings()
    if not getattr(request.state, "bootstrap_required", False):
        return RedirectResponse(url="/auth", status_code=303)
    try:
        user = bootstrap_admin(db, email=email, password=password, display_name=display_name or None)
        web_session, raw_token = create_web_session(db, user=user, ttl_seconds=settings.session_ttl_seconds)
        db.commit()
    except ValueError as exc:
        db.rollback()
        return templates.TemplateResponse(
            request=request,
            name="auth.html",
            context={
                "request": request,
                "settings": settings,
                "next_path": next_path or "/",
                "error_message": str(exc),
                "bootstrap_required": True,
            },
            status_code=400,
        )

    response = RedirectResponse(url=next_path or "/", status_code=303)
    response.set_cookie(
        WEB_SESSION_COOKIE,
        raw_token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        max_age=settings.session_ttl_seconds,
    )
    return response


@router.get("/", response_class=HTMLResponse)
def home(request: Request, orchestrator: Orchestrator = Depends(get_orchestrator)) -> HTMLResponse:
    recent_queries = orchestrator.list_recent_queries(limit=8)
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
def query_dashboard(
    request: Request,
    query_id: str,
    db: Session = Depends(get_db),
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> HTMLResponse:
    context = _dashboard_context(db, orchestrator, query_id)
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
) -> RedirectResponse:
    corpus = orchestrator.get_corpus(corpus_id)
    orchestrator.prepare_index(corpus_id)
    return RedirectResponse(url=f"/queries/{corpus.query_id}", status_code=303)


@router.get("/web/corpora/{corpus_id}/export.html", response_class=HTMLResponse)
def export_corpus_html(corpus_id: str, orchestrator: Orchestrator = Depends(get_orchestrator)) -> HTMLResponse:
    corpus = orchestrator.get_corpus(corpus_id)
    return HTMLResponse(content=render_corpus_html(corpus))


@router.get("/web/corpora/{corpus_id}/export.md")
def export_corpus_markdown(corpus_id: str, orchestrator: Orchestrator = Depends(get_orchestrator)) -> Response:
    corpus = orchestrator.get_corpus(corpus_id)
    return Response(
        content=corpus.corpus_markdown,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{export_filename(corpus, "md")}"'},
    )
