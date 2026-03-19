from __future__ import annotations

from urllib.parse import quote_plus

from kfabric.infra.models import Query


DEFAULT_DOMAINS = [
    "europa.eu",
    "service-public.fr",
    "data.gouv.fr",
    "arxiv.org",
    "hal.science",
    "github.com",
]


def discover_candidates(query: Query) -> list[dict[str, object]]:
    search_terms = (query.expansion_text or query.theme or query.question or "kfabric").split()
    preferred_domains = query.preferred_domains or DEFAULT_DOMAINS
    candidates: list[dict[str, object]] = []
    primary_topic = query.theme or query.question or "Corpus documentaire"
    for index, domain in enumerate(preferred_domains[:8], start=1):
        keyword = search_terms[(index - 1) % max(len(search_terms), 1)] if search_terms else "corpus"
        title = f"{primary_topic} - source {index}"
        snippet = (
            f"Document candidat sur {primary_topic}, orienté {keyword}, "
            f"collecté depuis {domain} pour analyse et consolidation."
        )
        candidates.append(
            {
                "source_url": f"https://{domain}/search?q={quote_plus(primary_topic)}&focus={quote_plus(keyword)}",
                "title": title,
                "snippet": snippet,
                "domain": domain,
                "document_type": "pdf" if index % 2 == 0 else "web",
                "language": query.language,
                "discovery_rank": index,
                "discovery_source": "heuristic_discovery",
            }
        )
    return candidates

