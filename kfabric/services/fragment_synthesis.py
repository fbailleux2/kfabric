from __future__ import annotations

from collections import defaultdict


def synthesize_fragments(theme: str, fragments: list[dict[str, object]]) -> tuple[str, float]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for fragment in fragments:
        grouped[str(fragment["fragment_type"])].append(fragment)

    lines = [f"# Synthese documentaire - {theme}", "", "## Regles de synthese", ""]
    lines.append("- Synthese prudente, orientee corpus")
    lines.append("- Attribution et tracabilite obligatoires")
    lines.append("- Les fragments non confirmes restent de faible priorite")
    lines.append("")

    confidence_values: list[float] = []
    for fragment_type, items in grouped.items():
        lines.append(f"## {fragment_type.replace('_', ' ').title()}")
        for item in items:
            confidence_values.append(float(item["confidence_level"]))
            lines.append(
                f"- {item['fragment_text']} "
                f"(score={item['fragment_score']}, confiance={item['confidence_level']}, "
                f"verification={item['verification_status']})"
            )
        lines.append("")

    overall_confidence = round(sum(confidence_values) / len(confidence_values), 2) if confidence_values else 0.0
    return "\n".join(lines).strip(), overall_confidence

