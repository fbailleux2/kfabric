from __future__ import annotations

import re

from rapidfuzz.fuzz import ratio

from kfabric.config import AppSettings


SOURCE_QUALITY_RULES = {
    ".gouv.fr": 20,
    "europa.eu": 19,
    ".edu": 18,
    ".org": 15,
    "github.com": 14,
    "arxiv.org": 16,
}


def score_document(text: str, domain: str, query_terms: list[str], headings: list[str], settings: AppSettings) -> dict[str, int | dict[str, str]]:
    lowered = text.lower()
    relevance = min(30, _relevance_score(lowered, query_terms))
    source_quality = min(20, _source_score(domain))
    documentary_value = min(20, 6 + min(len(text) // 120, 10) + min(len(headings), 4))
    freshness = min(10, 6 + (1 if "2024" in lowered else 0) + (1 if "2025" in lowered else 0) + (1 if "2026" in lowered else 0))
    exploitability = min(10, 4 + min(len(headings), 3) + min(text.count("\n") // 3, 3))
    originality = min(10, _originality_score(text, query_terms))
    global_score = int(relevance + source_quality + documentary_value + freshness + exploitability + originality)
    return {
        "global_score": global_score,
        "relevance_score": relevance,
        "source_quality_score": source_quality,
        "documentary_value_score": documentary_value,
        "freshness_score": freshness,
        "exploitability_score": exploitability,
        "originality_score": originality,
        "scoring_notes": {
            "accept_threshold": str(settings.accept_threshold),
            "salvage_threshold": str(settings.salvage_threshold),
        },
    }


def _relevance_score(text: str, query_terms: list[str]) -> int:
    if not query_terms:
        return 18
    term_hits = sum(1 for term in query_terms if term and term.lower() in text)
    return 8 + min(term_hits * 4, 22)


def _source_score(domain: str) -> int:
    for suffix, score in SOURCE_QUALITY_RULES.items():
        if suffix in domain:
            return score
    return 10


def _originality_score(text: str, query_terms: list[str]) -> int:
    if not query_terms:
        return 6
    joined = " ".join(query_terms)
    similarity = ratio(text[:400].lower(), joined.lower())
    number_bonus = min(3, len(re.findall(r"\d+", text)) // 2)
    return max(3, min(10, 7 - int(similarity / 25) + number_bonus))

