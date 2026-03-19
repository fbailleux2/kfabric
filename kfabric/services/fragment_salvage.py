from __future__ import annotations

import re

from kfabric.config import AppSettings
from kfabric.domain.enums import FragmentType, VerificationStatus


def salvage_fragments(text: str, query_terms: list[str], settings: AppSettings) -> list[dict[str, object]]:
    fragments: list[dict[str, object]] = []
    sentences = [segment.strip() for segment in re.split(r"(?<=[.!?])\s+", text) if segment.strip()]
    for sentence in sentences:
        if len(sentence) < 30 or len(sentence) > settings.max_fragment_chars:
            continue
        if not _looks_useful(sentence, query_terms):
            continue
        fragment_type = _classify(sentence)
        score = _fragment_score(sentence, query_terms)
        confidence = min(0.95, 0.4 + (score / 150))
        verification = VerificationStatus.PLAUSIBLE.value if score >= 60 else VerificationStatus.TO_CONFIRM.value
        fragments.append(
            {
                "fragment_text": sentence,
                "fragment_type": fragment_type,
                "fragment_score": score,
                "confidence_level": round(confidence, 2),
                "verification_status": verification,
                "start_offset": text.find(sentence),
                "end_offset": text.find(sentence) + len(sentence),
            }
        )
    return fragments[:8]


def _looks_useful(sentence: str, query_terms: list[str]) -> bool:
    lowered = sentence.lower()
    return (
        bool(re.search(r"\b(19|20)\d{2}\b", sentence))
        or bool(re.search(r"\b[A-Z]{2,}-\d{2,}\b", sentence))
        or bool(re.search(r"\b\d+([.,]\d+)?\s?%\b", sentence))
        or any(term.lower() in lowered for term in query_terms[:6])
    )


def _classify(sentence: str) -> str:
    if re.search(r"\b(19|20)\d{2}\b", sentence):
        return FragmentType.DATE.value
    if re.search(r"\b[A-Z]{2,}-\d{2,}\b", sentence):
        return FragmentType.REFERENCE.value
    if re.search(r"\b\d+([.,]\d+)?\s?%\b", sentence):
        return FragmentType.NUMBER.value
    if ":" in sentence:
        return FragmentType.DEFINITION.value
    return FragmentType.FACT.value


def _fragment_score(sentence: str, query_terms: list[str]) -> int:
    score = 40
    score += min(20, sum(1 for term in query_terms if term.lower() in sentence.lower()) * 4)
    if re.search(r"\b(19|20)\d{2}\b", sentence):
        score += 10
    if re.search(r"\b[A-Z]{2,}-\d{2,}\b", sentence):
        score += 10
    if re.search(r"\b\d+([.,]\d+)?\s?%\b", sentence):
        score += 8
    return min(95, score)

