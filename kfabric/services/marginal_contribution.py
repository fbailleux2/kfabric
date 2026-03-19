from __future__ import annotations


def marginal_contribution(text: str, reference_texts: list[str]) -> float:
    candidate_tokens = {token for token in text.lower().split() if len(token) > 3}
    if not candidate_tokens:
        return 0.0
    if not reference_texts:
        return 1.0
    reference_tokens: set[str] = set()
    for reference in reference_texts:
        reference_tokens.update(token for token in reference.lower().split() if len(token) > 3)
    novel_tokens = candidate_tokens - reference_tokens
    return round(len(novel_tokens) / len(candidate_tokens), 2)

