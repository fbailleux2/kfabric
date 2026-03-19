from __future__ import annotations

from hashlib import sha256

import httpx

from kfabric.config import AppSettings
from kfabric.infra.models import CandidateDocument, Query


def collect_document(candidate: CandidateDocument, query: Query, settings: AppSettings) -> dict[str, str]:
    content_type = "text/plain"
    collection_method = "synthetic"
    raw_content = ""

    if settings.remote_collection_enabled and candidate.source_url.startswith("http"):
        try:
            response = httpx.get(candidate.source_url, timeout=5.0, follow_redirects=True)
            response.raise_for_status()
            raw_content = response.text
            content_type = response.headers.get("content-type", "text/html").split(";")[0]
            collection_method = "httpx"
        except Exception:
            raw_content = _synthetic_content(candidate, query)
    else:
        raw_content = _synthetic_content(candidate, query)

    return {
        "raw_content": raw_content,
        "raw_hash": sha256(raw_content.encode("utf-8")).hexdigest(),
        "content_type": content_type,
        "collection_method": collection_method,
    }


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
