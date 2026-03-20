from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from kfabric.infra.models import CandidateDocument


@dataclass(frozen=True)
class RemoteFetchResult:
    response: httpx.Response
    content_url: str
    collection_method: str


def fetch_remote_candidate_content(
    candidate: CandidateDocument,
    *,
    headers: dict[str, str],
    timeout: float = 10.0,
) -> RemoteFetchResult:
    initial_response = _http_get(candidate.source_url, headers=headers, timeout=timeout)
    initial_url = _response_url(initial_response, candidate.source_url)
    domain = _normalize_domain(candidate.domain or urlparse(initial_url).netloc)

    if not _response_looks_like_html(initial_url, initial_response):
        candidate.document_type = _infer_document_type(initial_url, initial_response, candidate.document_type)
        return RemoteFetchResult(
            response=initial_response,
            content_url=initial_url,
            collection_method=_collection_method(domain, "direct"),
        )

    soup = BeautifulSoup(_response_text(initial_response), "html.parser")
    _apply_candidate_enrichment(candidate, soup, domain)

    detail_response = initial_response
    detail_url = initial_url
    if _should_resolve_detail(candidate, initial_url):
        resolved_detail = _extract_detail_url(domain, soup, initial_url)
        if resolved_detail and resolved_detail != initial_url:
            candidate.source_url = resolved_detail
            candidate.domain = _normalize_domain(urlparse(resolved_detail).netloc) or domain
            detail_response = _http_get(resolved_detail, headers=headers, timeout=timeout)
            detail_url = _response_url(detail_response, resolved_detail)
            if _response_looks_like_html(detail_url, detail_response):
                detail_soup = BeautifulSoup(_response_text(detail_response), "html.parser")
                _apply_candidate_enrichment(candidate, detail_soup, candidate.domain)
                soup = detail_soup
            else:
                candidate.document_type = _infer_document_type(detail_url, detail_response, candidate.document_type)
                return RemoteFetchResult(
                    response=detail_response,
                    content_url=detail_url,
                    collection_method=_collection_method(candidate.domain, "detail"),
                )

    resource_url = _extract_resource_url(candidate.domain, soup, detail_url)
    if resource_url and resource_url != detail_url:
        resource_response = _http_get(resource_url, headers=headers, timeout=timeout)
        candidate.document_type = _infer_document_type(resource_url, resource_response, candidate.document_type)
        return RemoteFetchResult(
            response=resource_response,
            content_url=_response_url(resource_response, resource_url),
            collection_method=_collection_method(candidate.domain, "resource"),
        )

    candidate.document_type = _infer_document_type(detail_url, detail_response, candidate.document_type)
    return RemoteFetchResult(
        response=detail_response,
        content_url=detail_url,
        collection_method=_collection_method(candidate.domain, "html"),
    )


def _http_get(url: str, *, headers: dict[str, str], timeout: float) -> httpx.Response:
    response = httpx.get(
        url,
        timeout=timeout,
        follow_redirects=True,
        headers=headers,
    )
    try:
        response.raise_for_status()
    except RuntimeError:
        if response.status_code >= 400:
            raise
    return response


def _response_looks_like_html(url: str, response: httpx.Response) -> bool:
    content_type = _response_content_type(response)
    if "html" in content_type:
        return True
    if content_type:
        return False
    lowered_url = url.lower()
    if lowered_url.endswith((".pdf", ".docx", ".md", ".txt")):
        return False
    sample = response.content[:256].decode("utf-8", errors="ignore").lower()
    return "<html" in sample or "<!doctype html" in sample


def _response_content_type(response: httpx.Response) -> str:
    return response.headers.get("content-type", "").split(";")[0].strip().lower()


def _response_url(response: httpx.Response, fallback: str) -> str:
    try:
        return str(response.url)
    except RuntimeError:
        return fallback


def _response_text(response: httpx.Response) -> str:
    try:
        return response.text
    except Exception:
        for encoding in ("utf-8", "latin-1", "cp1252"):
            try:
                return response.content.decode(encoding)
            except UnicodeDecodeError:
                continue
    return response.content.decode("utf-8", errors="ignore")


def _normalize_domain(netloc: str) -> str:
    return netloc.lower().removeprefix("www.")


def _collection_method(domain: str, suffix: str) -> str:
    normalized = _normalize_domain(domain).replace(".", "_").replace("-", "_") or "remote"
    return f"{normalized}_{suffix}_connector"


def _should_resolve_detail(candidate: CandidateDocument, current_url: str) -> bool:
    if candidate.discovery_source == "targeted_domain_search":
        return True

    parsed = urlparse(current_url)
    lowered = (parsed.path + "?" + parsed.query).lower()
    return any(marker in lowered for marker in ("/search", "/recherche", "keyword=", "scope=eurlex", "q="))


def _apply_candidate_enrichment(candidate: CandidateDocument, soup: BeautifulSoup, domain: str) -> None:
    extracted_title = _extract_title(soup, domain)
    if extracted_title:
        candidate.title = extracted_title

    extracted_snippet = _extract_snippet(soup, domain)
    if extracted_snippet and (not candidate.snippet or len(extracted_snippet) >= len(candidate.snippet)):
        candidate.snippet = extracted_snippet


def _extract_title(soup: BeautifulSoup, domain: str) -> str:
    selectors_by_domain = {
        "arxiv.org": ("h1.title", ".title.mathjax", "main h1", "h1"),
        "eur-lex.europa.eu": (".eli-main-title", ".oj-doc-ti", ".doc-ti", "main h1", "h1"),
        "github.com": ("strong[itemprop='name'] a", "meta[property='og:title']", "main h1", "h1"),
        "data.gouv.fr": ("[data-testid='dataset-title']", ".fr-card__title", "main h1", "h1"),
        "hal.science": (".Page-title", ".result-title", "main h1", "h1"),
        "legifrance.gouv.fr": (".title-page", ".titreTexte", "main h1", "h1"),
        "service-public.fr": (".page-title", ".fr-h1", "main h1", "h1"),
        "europa.eu": ("main h1", ".ecl-page-header__title", "h1", "title"),
    }
    generic_selectors = ("meta[property='og:title']", "meta[name='twitter:title']", "title", "main h1", "h1")
    for selector in (*selectors_by_domain.get(domain, ()), *generic_selectors):
        tag = soup.select_one(selector)
        if tag is None:
            continue
        if tag.name == "meta":
            content = (tag.get("content") or "").strip()
            if content:
                return content
            continue
        text = tag.get_text(" ", strip=True)
        if text:
            return text
    return ""


def _extract_snippet(soup: BeautifulSoup, domain: str) -> str:
    selectors_by_domain = {
        "arxiv.org": (".abstract", "blockquote.abstract", ".authors", "main p"),
        "eur-lex.europa.eu": (".eli-context", ".eli-data dd", "#text p", "main p"),
        "github.com": ("meta[name='description']", "meta[property='og:description']", "article.markdown-body p", "#readme p", ".markdown-body p", "main p"),
        "data.gouv.fr": (".fr-text--lead", ".dataset-description", "main p"),
        "hal.science": (".abstract", "#abstract", ".description", "main p"),
        "legifrance.gouv.fr": (".chapo", ".article-body p", ".texte p", "main p"),
        "service-public.fr": (".introduction", ".fr-text--lead", ".chapo", "main p"),
        "europa.eu": (".ecl-paragraph", ".ecl-u-type-lead", "main p"),
    }
    generic_selectors = ("meta[name='description']", "meta[property='og:description']", "main p", "article p", "p")
    for selector in (*selectors_by_domain.get(domain, ()), *generic_selectors):
        tag = soup.select_one(selector)
        if tag is None:
            continue
        if tag.name == "meta":
            content = (tag.get("content") or "").strip()
            if content:
                return content[:420]
            continue
        text = tag.get_text(" ", strip=True)
        if text:
            return text[:420]
    return ""


def _extract_detail_url(domain: str, soup: BeautifulSoup, base_url: str) -> str | None:
    selectors_by_domain = {
        "arxiv.org": ("a[href*='/abs/']",),
        "eur-lex.europa.eu": ("a[href*='/legal-content/']", "a[href*='uri=CELEX']"),
        "github.com": ("a.v-align-middle[href]", "a[data-testid='result-list-item-title'][href]", ".search-title a[href]"),
        "data.gouv.fr": ("a[href*='/datasets/']", "a[href*='/reuses/']"),
        "hal.science": ("a[href*='/hal-']",),
        "legifrance.gouv.fr": ("a[href*='/jorf/id/']", "a[href*='/codes/article_lc/']", "a[href*='/loda/id/']"),
        "service-public.fr": ("a[href*='/particuliers/']", "a[href*='/professionnels-entreprises/']"),
        "europa.eu": ("main a[href]", "article a[href]"),
    }
    return _first_candidate_href(soup, selectors_by_domain.get(domain, ()), base_url)


def _extract_resource_url(domain: str, soup: BeautifulSoup, base_url: str) -> str | None:
    selectors_by_domain = {
        "arxiv.org": (
            "a[href*='/pdf/']",
            "a[href$='.pdf']",
        ),
        "eur-lex.europa.eu": (
            "a[href*='/TXT/PDF/']",
            "a[href$='.pdf']",
            "a[href*='format=PDF']",
        ),
        "data.gouv.fr": (
            "a[href$='.pdf']",
            "a[href*='/resources/'][href$='.pdf']",
            "a[href$='.md']",
            "a[href$='.txt']",
            "a[href$='.docx']",
        ),
        "hal.science": (
            "a[href$='/document']",
            "a[href*='/document?']",
            "a[href$='.pdf']",
        ),
        "legifrance.gouv.fr": (
            "a[href*='/download/pdf/']",
            "a[href$='.pdf']",
            "a[href*='telecharger?format=pdf']",
        ),
        "service-public.fr": (
            "a[href$='.pdf']",
            "a[download][href$='.pdf']",
            "a[href*='telecharger']",
        ),
        "europa.eu": (
            "a[href$='.pdf']",
            "a[href*='download'][href$='.pdf']",
        ),
    }
    return _first_candidate_href(soup, selectors_by_domain.get(domain, ()), base_url)


def _first_candidate_href(soup: BeautifulSoup, selectors: tuple[str, ...], base_url: str) -> str | None:
    for selector in selectors:
        for tag in soup.select(selector):
            href = (tag.get("href") or "").strip()
            if not _is_candidate_href(href):
                continue
            absolute = urljoin(base_url, href)
            if absolute.startswith(("http://", "https://")):
                return absolute
    return None


def _is_candidate_href(href: str) -> bool:
    lowered = href.lower()
    return bool(href) and not lowered.startswith(("#", "javascript:", "mailto:"))


def _infer_document_type(source_url: str, response: httpx.Response, fallback: str) -> str:
    content_type = _response_content_type(response)
    lowered_url = source_url.lower()
    lowered = " ".join([lowered_url, content_type, fallback.lower()])
    if ".pdf" in lowered or "application/pdf" in lowered:
        return "pdf"
    if ".docx" in lowered or "wordprocessingml" in lowered:
        return "docx"
    if ".md" in lowered or "markdown" in lowered:
        return "markdown"
    if ".txt" in lowered or "text/plain" in lowered:
        return "text"
    return fallback
