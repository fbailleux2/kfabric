from __future__ import annotations

from collections import OrderedDict


SYNONYM_MAP = {
    "reglementation": ["conformite", "directive", "norme"],
    "europe": ["ue", "union europeenne", "europeen"],
    "savon": ["cosmetique", "hygiene", "formulation"],
    "artisanale": ["artisanat", "fabrication", "metier"],
    "document": ["rapport", "guide", "specification"],
    "mcp": ["protocol", "json-rpc", "tooling"],
}


def _tokenize(text: str) -> list[str]:
    return [token.strip(" ,.;:!?()[]{}").lower() for token in text.split() if token.strip()]


def expand_query(theme: str | None, question: str | None, keywords: list[str]) -> dict[str, object]:
    source_parts = [part for part in [theme, question, *keywords] if part]
    original_query = " | ".join(source_parts) if source_parts else "corpus documentaire"
    ordered_terms: OrderedDict[str, None] = OrderedDict()
    for token in _tokenize(original_query):
        ordered_terms[token] = None
        for synonym in SYNONYM_MAP.get(token, []):
            ordered_terms[synonym] = None

    if theme:
        ordered_terms[theme.lower()] = None
    if question:
        ordered_terms[question.lower()] = None

    terms = list(ordered_terms.keys())
    expanded_query = " ".join(terms)
    return {
        "original_query": original_query,
        "expanded_query": expanded_query,
        "expansion_terms": terms,
    }

