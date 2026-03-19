from __future__ import annotations

from datetime import datetime, timezone

from kfabric.domain.enums import CorpusStatus


def build_corpus_markdown(
    theme: str,
    accepted_documents: list[dict[str, object]],
    syntheses: list[dict[str, object]],
    *,
    query_context: dict[str, object] | None = None,
) -> str:
    context = query_context or {}
    accepted_count = len(accepted_documents)
    synthesis_count = len(syntheses)
    domains = _list_domains(accepted_documents)
    average_score = _average_score(accepted_documents)
    generated_at = str(context.get("generated_at") or _utc_timestamp())
    keywords = [str(keyword) for keyword in context.get("keywords", []) if keyword]
    question = str(context.get("question") or "").strip()
    quality_target = str(context.get("quality_target") or "balanced")
    trace_id = str(context.get("trace_id") or "")

    lines = [f"# KFabric Corpus - {theme}", ""]
    lines.append("> Corpus consolide pour revue humaine, export documentaire et pre-indexation.")
    lines.append(
        f"> Version generee le {generated_at} • {accepted_count} documents acceptes • {synthesis_count} syntheses complementaires"
    )
    lines.append("")

    lines.append("## Resume executif")
    lines.append("")
    lines.append(
        f"Le corpus consolide pour **{theme}** assemble {accepted_count} source(s) prioritaire(s) et "
        f"{synthesis_count} synthese(s) de fragments a faible poids. "
        f"La cible de qualite retenue est **{quality_target}**."
    )
    if question:
        lines.append("")
        lines.append(f"Question de cadrage : {question}")
    if keywords:
        lines.append("")
        lines.append(f"Mots-cles de pilotage : {', '.join(keywords)}")
    lines.append("")

    lines.append("## Tableau de bord")
    lines.append("")
    lines.append(f"- Statut cible : {CorpusStatus.READY.value}")
    lines.append(f"- Score moyen des documents retenus : {average_score}/100")
    lines.append(f"- Domaines representes : {', '.join(domains) if domains else 'aucun'}")
    lines.append(f"- Strategie d'usage : documents acceptes en priorite, syntheses a poids reduit")
    if trace_id:
        lines.append(f"- Trace de reference : {trace_id}")
    lines.append("")

    lines.append("## Recommandation d'usage")
    lines.append("")
    lines.append("- Utiliser d'abord les documents acceptes pour toute synthese ou indexation primaire.")
    lines.append("- Ajouter les syntheses de fragments comme contexte secondaire, avec verification manuelle si besoin.")
    lines.append("- Conserver les URLs, scores et indices de confiance pour toute restitution aval.")
    lines.append("")

    lines.append("## Dossier principal")
    lines.append("")
    if not accepted_documents:
        lines.append("_Aucun document accepte pour le moment._")
    else:
        for index, document in enumerate(accepted_documents, start=1):
            lines.extend(_render_document_section(index, document))
    lines.append("")

    lines.append("## Syntheses complementaires")
    lines.append("")
    if not syntheses:
        lines.append("_Aucune synthese de fragments rejetes disponible._")
    else:
        for index, synthesis in enumerate(syntheses, start=1):
            lines.extend(_render_synthesis_section(index, synthesis))
    lines.append("")

    lines.append("## Traceabilite et prudence")
    lines.append("")
    lines.append("- Toutes les sources retenues conservent leur URL et leur score global.")
    lines.append("- Les syntheses de rejets doivent etre lues comme des aides documentaires et non comme des sources primaires.")
    lines.append("- Ce corpus est pret pour export, revue humaine et preparation d'index.")
    return "\n".join(lines).strip()


def _render_document_section(index: int, document: dict[str, object]) -> list[str]:
    headings = [str(heading) for heading in document.get("headings", []) if heading]
    excerpt = _quote_block(str(document.get("excerpt") or ""))
    score = int(document.get("score") or 0)
    text_length = int(document.get("text_length") or 0)
    lines = [f"### {index}. {document['title']}", ""]
    lines.append(f"- Score global : {score}/100")
    lines.append(f"- Domaine : {document.get('domain', 'inconnu')}")
    lines.append(f"- Type : {document.get('document_type', 'web')}")
    lines.append(f"- Extraction : {document.get('extraction_method', 'unknown')}")
    lines.append(f"- Taille normalisee : {text_length} caracteres")
    lines.append(f"- Source : {document['source_url']}")
    if headings:
        lines.append(f"- Points d'appui : {' ; '.join(headings[:4])}")
    lines.append("- Extrait cle :")
    lines.append(excerpt or "> Extrait indisponible")
    lines.append("")
    return lines


def _render_synthesis_section(index: int, synthesis: dict[str, object]) -> list[str]:
    confidence = float(synthesis.get("overall_confidence") or 0.0)
    fragments = int(synthesis.get("generated_from_n_fragments") or 0)
    rejected_docs = int(synthesis.get("generated_from_n_rejected_docs") or 0)
    index_priority = float(synthesis.get("index_priority") or 0.0)
    excerpt = _quote_block(str(synthesis.get("excerpt") or ""))
    lines = [f"### {index}. {synthesis['theme']}", ""]
    lines.append(f"- Confiance globale : {confidence:.2f}")
    lines.append(f"- Fragments consolides : {fragments}")
    lines.append(f"- Documents rejetes contributifs : {rejected_docs}")
    lines.append(f"- Priorite d'indexation : {index_priority:.2f}")
    lines.append("- Extrait de synthese :")
    lines.append(excerpt or "> Extrait indisponible")
    lines.append("")
    return lines


def _list_domains(accepted_documents: list[dict[str, object]]) -> list[str]:
    domains: list[str] = []
    for document in accepted_documents:
        domain = str(document.get("domain") or "").strip()
        if domain and domain not in domains:
            domains.append(domain)
    return domains


def _average_score(accepted_documents: list[dict[str, object]]) -> int:
    if not accepted_documents:
        return 0
    scores = [int(document.get("score") or 0) for document in accepted_documents]
    return round(sum(scores) / len(scores))


def _quote_block(text: str, max_chars: int = 320) -> str:
    cleaned = " ".join(text.split()).strip()
    if not cleaned:
        return ""
    excerpt = cleaned[:max_chars].rstrip()
    if len(cleaned) > max_chars:
        excerpt += "..."
    return f"> {excerpt}"


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
