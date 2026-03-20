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


def score_document(
    text: str,
    domain: str,
    query_terms: list[str],
    headings: list[str],
    settings: AppSettings,
    *,
    document_type: str = "web",
    quality_target: str = "balanced",
) -> dict[str, int | dict[str, str]]:
    lowered = text.lower()
    relevance = min(30, _relevance_score(lowered, query_terms, headings))
    source_quality = min(20, _source_score(domain, document_type))
    documentary_value = min(20, _documentary_value_score(text, headings))
    freshness = min(10, _freshness_score(lowered))
    exploitability = min(10, _exploitability_score(text, headings, document_type))
    originality = min(10, _originality_score(text, query_terms))
    quality_adjustment = _quality_target_adjustment(
        quality_target,
        relevance=relevance,
        source_quality=source_quality,
        documentary_value=documentary_value,
    )
    global_score = int(
        max(
            0,
            min(
                100,
                relevance + source_quality + documentary_value + freshness + exploitability + originality + quality_adjustment,
            ),
        )
    )
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
            "quality_target": quality_target,
            "document_type": document_type,
        },
    }


def _relevance_score(text: str, query_terms: list[str], headings: list[str]) -> int:
    if not query_terms:
        return 18
    heading_text = " ".join(headings).lower()
    text_hits = sum(1 for term in query_terms if term and term.lower() in text)
    heading_hits = sum(1 for term in query_terms[:6] if term and term.lower() in heading_text)
    return 8 + min(text_hits * 3, 16) + min(heading_hits * 2, 6)


def _source_score(domain: str, document_type: str) -> int:
    base_score = 10
    for suffix, score in SOURCE_QUALITY_RULES.items():
        if suffix in domain:
            base_score = score
            break
    if document_type in {"pdf", "docx"}:
        base_score += 1
    if document_type == "repository":
        base_score += 1
    return min(20, base_score)


def _documentary_value_score(text: str, headings: list[str]) -> int:
    number_signals = len(re.findall(r"\b\d+(?:[.,]\d+)?\b", text))
    reference_signals = len(re.findall(r"\b[A-Z]{2,}-\d{2,}\b", text))
    structure_bonus = min(len(headings), 5)
    length_bonus = min(len(text) // 150, 8)
    evidence_bonus = min(4, number_signals // 3 + min(reference_signals, 2))
    return 5 + length_bonus + structure_bonus + evidence_bonus


def _freshness_score(text: str) -> int:
    years = [int(year) for year in re.findall(r"\b((?:19|20)\d{2})\b", text)]
    if not years:
        return 5
    recent_year = max(years)
    if recent_year >= 2026:
        return 10
    if recent_year == 2025:
        return 9
    if recent_year == 2024:
        return 8
    if recent_year >= 2022:
        return 7
    return 6


def _exploitability_score(text: str, headings: list[str], document_type: str) -> int:
    newline_bonus = min(text.count("\n") // 3, 3)
    heading_bonus = min(len(headings), 4)
    type_bonus = 2 if document_type in {"pdf", "docx", "markdown", "repository"} else 1
    return 3 + heading_bonus + newline_bonus + type_bonus


def _originality_score(text: str, query_terms: list[str]) -> int:
    if not query_terms:
        return 6
    joined = " ".join(query_terms)
    similarity = ratio(text[:400].lower(), joined.lower())
    number_bonus = min(3, len(re.findall(r"\d+", text)) // 2)
    return max(3, min(10, 7 - int(similarity / 25) + number_bonus))


def _quality_target_adjustment(
    quality_target: str,
    *,
    relevance: int,
    source_quality: int,
    documentary_value: int,
) -> int:
    lowered = quality_target.lower()
    if lowered == "strict":
        return 2 if source_quality >= 16 and documentary_value >= 14 else -2
    if lowered == "wide":
        return 2 if relevance >= 16 else 0
    return 0
