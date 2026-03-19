from __future__ import annotations

import re

from rapidfuzz.fuzz import ratio


def canonicalize_text(value: str) -> str:
    return re.sub(r"\W+", " ", value.lower()).strip()


def cluster_fragments(fragments: list[dict[str, object]]) -> list[dict[str, object]]:
    clusters: list[dict[str, object]] = []
    for fragment in fragments:
        text = str(fragment["fragment_text"])
        canonical = canonicalize_text(text)
        matched_cluster = None
        for cluster in clusters:
            similarity = ratio(canonical, cluster["canonical"])
            if similarity >= 88:
                matched_cluster = cluster
                break
        if matched_cluster:
            matched_cluster["items"].append(fragment)
        else:
            clusters.append(
                {
                    "canonical": canonical,
                    "label": text[:72],
                    "items": [fragment],
                }
            )
    return clusters

