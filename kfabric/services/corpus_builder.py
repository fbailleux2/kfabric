from __future__ import annotations

from kfabric.domain.enums import CorpusStatus


def build_corpus_markdown(theme: str, accepted_documents: list[dict[str, str]], syntheses: list[dict[str, str]]) -> str:
    lines = [f"# Corpus final - {theme}", ""]
    lines.append("## Documents acceptes")
    if not accepted_documents:
        lines.append("- Aucun document accepte pour le moment")
    else:
        for document in accepted_documents:
            lines.append(f"- **{document['title']}**")
            lines.append(f"  - URL: {document['source_url']}")
            lines.append(f"  - Score: {document['score']}")
            lines.append(f"  - Poids: fort")
    lines.append("")
    lines.append("## Syntheses de fragments rejetes")
    if not syntheses:
        lines.append("- Aucune synthese disponible")
    else:
        for synthesis in syntheses:
            lines.append(f"- **{synthesis['theme']}**")
            lines.append(f"  - Confiance: {synthesis['overall_confidence']}")
            lines.append(f"  - Poids: reduit")
    lines.append("")
    lines.append(f"Statut cible: {CorpusStatus.READY.value}")
    return "\n".join(lines)

