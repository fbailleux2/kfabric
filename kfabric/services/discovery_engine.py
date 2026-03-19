from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote_plus, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from kfabric.config import AppSettings
from kfabric.infra.models import Query


@dataclass(frozen=True)
class DiscoveryProfile:
    domain: str
    search_url_template: str
    title_suffix: str
    snippet_hint: str
    document_type: str = "web"
    discovery_source: str = "targeted_domain_search"
    result_selectors: tuple[str, ...] = (
        "article",
        ".search-result",
        ".fr-card",
        ".card",
        "main li",
    )
    snippet_selectors: tuple[str, ...] = (
        "p",
        ".search-result__description",
        ".fr-card__desc",
        ".result__summary",
        ".description",
    )


DISCOVERY_PROFILES = {
    "europa.eu": DiscoveryProfile(
        domain="europa.eu",
        search_url_template="https://europa.eu/search/?query={query}",
        title_suffix="Recherche Europa",
        snippet_hint="Portail institutionnel europeen pour cadrage reglementaire et pages de contexte.",
        result_selectors=(".search-result", ".ecl-search-result", "article", "main li"),
    ),
    "eur-lex.europa.eu": DiscoveryProfile(
        domain="eur-lex.europa.eu",
        search_url_template="https://eur-lex.europa.eu/search.html?scope=EURLEX&text={query}",
        title_suffix="Recherche EUR-Lex",
        snippet_hint="Base juridique europeenne pour textes, directives, reglements et references officielles.",
        result_selectors=(".SearchResult", ".result", "article", "main li"),
    ),
    "service-public.fr": DiscoveryProfile(
        domain="service-public.fr",
        search_url_template="https://www.service-public.fr/particuliers/recherche?keyword={query}",
        title_suffix="Recherche Service-Public",
        snippet_hint="Information administrative francaise utile pour obligations declaratives et demarches.",
        result_selectors=(".fr-card", ".search-result", "article", "main li"),
    ),
    "data.gouv.fr": DiscoveryProfile(
        domain="data.gouv.fr",
        search_url_template="https://www.data.gouv.fr/fr/search/?q={query}",
        title_suffix="Recherche data.gouv.fr",
        snippet_hint="Jeux de donnees et ressources ouvertes pour completer le corpus avec sources publiques.",
        result_selectors=(".dataset-result", ".search-result", "article", ".card", "main li"),
    ),
    "legifrance.gouv.fr": DiscoveryProfile(
        domain="legifrance.gouv.fr",
        search_url_template="https://www.legifrance.gouv.fr/search/all?query={query}",
        title_suffix="Recherche Legifrance",
        snippet_hint="Source normative francaise pour textes consolides et references juridiques officielles.",
        result_selectors=(".search-results__item", ".result", "article", "main li"),
    ),
    "hal.science": DiscoveryProfile(
        domain="hal.science",
        search_url_template="https://hal.science/search/index/?q={query}",
        title_suffix="Recherche HAL",
        snippet_hint="Production scientifique francaise et europeenne avec potentiel de PDF exploitables.",
        result_selectors=(".result-item", ".search-result", "article", "main li"),
    ),
    "arxiv.org": DiscoveryProfile(
        domain="arxiv.org",
        search_url_template="https://arxiv.org/search/?query={query}&searchtype=all&source=header",
        title_suffix="Recherche arXiv",
        snippet_hint="Preprints scientifiques utiles pour veille technique, signaux faibles et etat de l'art.",
        result_selectors=(".arxiv-result", "li.arxiv-result", "article", "main li"),
    ),
    "github.com": DiscoveryProfile(
        domain="github.com",
        search_url_template="https://github.com/search?q={query}&type=repositories",
        title_suffix="Recherche GitHub",
        snippet_hint="Documentation technique, depots et schemas de reference pour cadrer l'implementation.",
        result_selectors=(".repo-list-item", ".search-title", "article", "main li"),
    ),
}

DEFAULT_DOMAINS = list(DISCOVERY_PROFILES)
REMOTE_RESULTS_PER_DOMAIN = 3
DISCOVERY_HEADERS = {
    "User-Agent": "KFabric/0.1 (+https://github.com/fbailleux2/kfabric)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.5",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.6",
}


def discover_candidates(query: Query, settings: AppSettings | None = None) -> list[dict[str, object]]:
    search_terms = _build_search_terms(query)
    preferred_domains = _select_domains(query)
    candidates: list[dict[str, object]] = []
    primary_topic = query.theme or query.question or "Corpus documentaire"
    next_rank = 1
    for index, domain in enumerate(preferred_domains[:8], start=1):
        keyword = search_terms[(index - 1) % max(len(search_terms), 1)] if search_terms else "corpus"
        profile = DISCOVERY_PROFILES.get(
            domain,
            DiscoveryProfile(
                domain=domain,
                search_url_template=f"https://{domain}/search?q={{query}}",
                title_suffix=f"Recherche {domain}",
                snippet_hint="Source externe ajoutee a la strategie de decouverte ciblee.",
            ),
        )
        search_query = _build_query_string(primary_topic, keyword, query.keywords)

        remote_candidates: list[dict[str, object]] = []
        if settings and settings.remote_discovery_enabled:
            remote_candidates = _discover_remote_candidates(query, profile, search_query, next_rank)

        if remote_candidates:
            candidates.extend(remote_candidates)
            next_rank += len(remote_candidates)
            continue

        candidates.append(_build_fallback_candidate(query, profile, search_query, keyword, next_rank))
        next_rank += 1
    return candidates


def _select_domains(query: Query) -> list[str]:
    preferred_domains = query.preferred_domains or DEFAULT_DOMAINS
    excluded = {domain.lower() for domain in (query.excluded_domains or [])}
    selected: list[str] = []
    for domain in preferred_domains:
        normalized = domain.lower().strip()
        if normalized and normalized not in excluded and normalized not in selected:
            selected.append(normalized)
    return selected or DEFAULT_DOMAINS


def _build_search_terms(query: Query) -> list[str]:
    raw_terms = [
        query.theme or "",
        query.question or "",
        query.expansion_text or "",
        *(query.keywords or []),
    ]
    terms: list[str] = []
    for raw_term in raw_terms:
        for token in re.split(r"[\s,;:/|()!?]+", raw_term):
            cleaned = token.strip().lower()
            if len(cleaned) >= 3 and cleaned not in terms:
                terms.append(cleaned)
    return terms or ["corpus", "documentaire"]


def _build_query_string(primary_topic: str, focus_term: str, keywords: list[str]) -> str:
    phrases = [primary_topic.strip(), focus_term.strip(), *[keyword.strip() for keyword in keywords[:3]]]
    deduplicated: list[str] = []
    for phrase in phrases:
        lowered = phrase.lower()
        if phrase and lowered not in deduplicated:
            deduplicated.append(lowered)
    return " ".join(deduplicated)


def _build_fallback_candidate(
    query: Query,
    profile: DiscoveryProfile,
    search_query: str,
    keyword: str,
    rank: int,
) -> dict[str, object]:
    primary_topic = query.theme or query.question or "Corpus documentaire"
    title = f"{primary_topic} - {profile.title_suffix}"
    snippet = (
        f"{profile.snippet_hint} Focus {keyword}. "
        f"Candidat prepare pour collecte et qualification sur {profile.domain}."
    )
    return {
        "source_url": profile.search_url_template.format(
            query=quote_plus(search_query),
            focus=quote_plus(keyword),
        ),
        "title": title,
        "snippet": snippet,
        "domain": profile.domain,
        "document_type": profile.document_type,
        "language": query.language,
        "discovery_rank": rank,
        "discovery_source": profile.discovery_source,
    }


def _discover_remote_candidates(
    query: Query,
    profile: DiscoveryProfile,
    search_query: str,
    start_rank: int,
) -> list[dict[str, object]]:
    search_url = profile.search_url_template.format(query=quote_plus(search_query), focus=quote_plus(search_query))
    try:
        response = httpx.get(
            search_url,
            timeout=10.0,
            follow_redirects=True,
            headers=DISCOVERY_HEADERS,
        )
        try:
            response.raise_for_status()
        except RuntimeError:
            if response.status_code >= 400:
                raise
    except Exception:
        return []

    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type and "html" not in content_type:
        return []

    extracted_results = _extract_result_cards(response.text, search_url, profile)
    candidates: list[dict[str, object]] = []
    rank = start_rank
    for result in extracted_results[:REMOTE_RESULTS_PER_DOMAIN]:
        candidates.append(
            {
                "source_url": result["source_url"],
                "title": result["title"],
                "snippet": result["snippet"] or profile.snippet_hint,
                "domain": result["domain"],
                "document_type": result["document_type"],
                "language": query.language,
                "discovery_rank": rank,
                "discovery_source": "remote_search_connector",
            }
        )
        rank += 1
    return candidates


def _extract_result_cards(raw_html: str, base_url: str, profile: DiscoveryProfile) -> list[dict[str, str]]:
    soup = BeautifulSoup(raw_html, "html.parser")
    result_nodes = _select_result_nodes(soup, profile.result_selectors)
    extracted: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for node in result_nodes:
        link = node.select_one("a[href]")
        if link is None:
            continue
        href = (link.get("href") or "").strip()
        if not _is_candidate_href(href):
            continue
        absolute_url = urljoin(base_url, href)
        if absolute_url in seen_urls:
            continue
        title = _extract_title(node, link)
        if not title:
            continue
        snippet = _extract_snippet(node, link, profile)
        seen_urls.add(absolute_url)
        extracted.append(
            {
                "source_url": absolute_url,
                "title": title,
                "snippet": snippet,
                "domain": _normalize_domain(urlparse(absolute_url).netloc or profile.domain),
                "document_type": _infer_document_type(absolute_url, title, snippet, profile.document_type),
            }
        )

    return extracted


def _select_result_nodes(soup: BeautifulSoup, selectors: tuple[str, ...]) -> list[BeautifulSoup]:
    nodes: list[BeautifulSoup] = []
    seen: set[int] = set()
    for selector in selectors:
        for node in soup.select(selector):
            if id(node) in seen:
                continue
            if node.select_one("a[href]") is None:
                continue
            seen.add(id(node))
            nodes.append(node)
        if nodes:
            break

    if nodes:
        return nodes

    for node in soup.select("main a[href], article a[href], li a[href]"):
        parent = node.parent or node
        if id(parent) in seen:
            continue
        seen.add(id(parent))
        nodes.append(parent)
    return nodes


def _extract_title(node: BeautifulSoup, link: BeautifulSoup) -> str:
    for selector in ("h1", "h2", "h3", ".title", ".search-result__title", ".fr-card__title"):
        tag = node.select_one(selector)
        if tag and tag.get_text(" ", strip=True):
            return tag.get_text(" ", strip=True)
    return link.get_text(" ", strip=True)


def _extract_snippet(node: BeautifulSoup, link: BeautifulSoup, profile: DiscoveryProfile) -> str:
    for selector in profile.snippet_selectors:
        tag = node.select_one(selector)
        if tag and tag is not link:
            snippet = tag.get_text(" ", strip=True)
            if snippet:
                return snippet[:420]

    text = node.get_text(" ", strip=True)
    title = link.get_text(" ", strip=True)
    if text.startswith(title):
        text = text[len(title) :].strip(" -:\n\t")
    return text[:420]


def _is_candidate_href(href: str) -> bool:
    lowered = href.lower()
    return bool(href) and not lowered.startswith(("#", "javascript:", "mailto:"))


def _infer_document_type(source_url: str, title: str, snippet: str, fallback_type: str) -> str:
    lowered = " ".join([source_url.lower(), title.lower(), snippet.lower()])
    if ".pdf" in lowered or " pdf" in lowered:
        return "pdf"
    return fallback_type


def _normalize_domain(netloc: str) -> str:
    return netloc.lower().removeprefix("www.")
