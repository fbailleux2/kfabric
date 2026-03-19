from __future__ import annotations

from hashlib import sha256

import httpx

from kfabric.config import AppSettings
from kfabric.infra.models import CandidateDocument, Query
from kfabric.services.content_payloads import pack_binary_payload


REQUEST_HEADERS = {
    "User-Agent": "KFabric/0.1 (+https://github.com/fbailleux2/kfabric)",
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "application/pdf;q=0.8,text/markdown;q=0.7,text/plain;q=0.6,*/*;q=0.5"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.6",
}


def collect_document(candidate: CandidateDocument, query: Query, settings: AppSettings) -> dict[str, str]:
    content_type = "text/plain"
    collection_method = "synthetic"
    raw_content = ""
    raw_hash = ""

    if settings.remote_collection_enabled and candidate.source_url.startswith("http"):
        try:
            response = httpx.get(
                candidate.source_url,
                timeout=10.0,
                follow_redirects=True,
                headers=REQUEST_HEADERS,
            )
            try:
                response.raise_for_status()
            except RuntimeError:
                if response.status_code >= 400:
                    raise
            content_type = _detect_content_type(candidate.source_url, response)
            raw_content, raw_hash, collection_method = _build_collected_payload(candidate, response, content_type)
        except Exception:
            raw_content = _synthetic_content(candidate, query)
            raw_hash = sha256(raw_content.encode("utf-8")).hexdigest()
    else:
        raw_content = _synthetic_content(candidate, query)
        raw_hash = sha256(raw_content.encode("utf-8")).hexdigest()

    return {
        "raw_content": raw_content,
        "raw_hash": raw_hash,
        "content_type": content_type,
        "collection_method": collection_method,
    }


def _build_collected_payload(
    candidate: CandidateDocument,
    response: httpx.Response,
    content_type: str,
) -> tuple[str, str, str]:
    if _is_pdf_content(candidate.source_url, content_type, response.content):
        raw_content = pack_binary_payload(
            response.content,
            "application/pdf",
            source_url=candidate.source_url,
            title=candidate.title,
        )
        return raw_content, sha256(response.content).hexdigest(), "httpx_pdf"

    raw_content = _decode_response_text(response)
    return raw_content, sha256(raw_content.encode("utf-8")).hexdigest(), "httpx_html"


def _detect_content_type(source_url: str, response: httpx.Response) -> str:
    header_content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if _is_pdf_content(source_url, header_content_type, response.content):
        return "application/pdf"
    if header_content_type:
        return header_content_type
    if _looks_like_html(response.content):
        return "text/html"
    return "text/plain"


def _is_pdf_content(source_url: str, content_type: str, content: bytes) -> bool:
    return (
        "pdf" in (content_type or "")
        or source_url.lower().endswith(".pdf")
        or content.startswith(b"%PDF-")
    )


def _looks_like_html(content: bytes) -> bool:
    start = content[:256].decode("utf-8", errors="ignore").lower()
    return "<html" in start or "<!doctype html" in start


def _decode_response_text(response: httpx.Response) -> str:
    try:
        return response.text
    except Exception:
        for encoding in ("utf-8", "latin-1", "cp1252"):
            try:
                return response.content.decode(encoding)
            except UnicodeDecodeError:
                continue
    return response.content.decode("utf-8", errors="ignore")


def _synthetic_content(candidate: CandidateDocument, query: Query) -> str:
    query_focus = query.theme or query.question or "corpus documentaire"
    return (
        f"# {candidate.title}\n\n"
        f"Source: {candidate.source_url}\n\n"
        f"Ce document synthetic couvre {query_focus}. "
        f"Il mentionne une date cle 2024, une reference technique REF-2024-KFABRIC, "
        f"et un score de conformite de 87%. "
        f"Le contenu inclut des definitions courtes, des chiffres exploitables "
        f"et des pistes de consolidation documentaire.\n\n"
        f"Snippet initial: {candidate.snippet}\n\n"
        "Sections:\n"
        "- Contexte\n"
        "- Exigences reglementaires\n"
        "- Signaux faibles a confirmer\n"
        "- References complementaires\n"
    )
