#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kfabric.config import AppSettings
from kfabric.domain.enums import DocumentDecisionStatus
from kfabric.domain.schemas import QueryCreate
from kfabric.infra.db import get_session_factory, init_db
from kfabric.infra.models import CandidateDocument
from kfabric.services.orchestrator import Orchestrator


@dataclass(frozen=True)
class CandidateSeed:
    title: str
    source_url: str
    snippet: str
    domain: str
    document_type: str = "web"


@dataclass(frozen=True)
class DemoScenario:
    slug: str
    payload: QueryCreate
    candidate_seeds: tuple[CandidateSeed, ...]


SCENARIOS = (
    DemoScenario(
        slug="savon-europe",
        payload=QueryCreate(
            theme="Reglementation savon artisanal en Europe",
            question="Quels textes et quelles obligations concretes faut-il integrer dans un corpus fiable ?",
            keywords=["savon artisanal", "europe", "conformite", "etiquetage"],
            preferred_domains=["eur-lex.europa.eu", "europa.eu", "service-public.fr"],
            quality_target="strict",
        ),
        candidate_seeds=(
            CandidateSeed(
                title="Reglement cosmetique europeen 1223/2009",
                source_url="https://eur-lex.europa.eu/legal-content/FR/TXT/?uri=CELEX:32009R1223",
                snippet="Texte de reference pour la mise sur le marche, la securite produit et la documentation technique.",
                domain="eur-lex.europa.eu",
                document_type="pdf",
            ),
            CandidateSeed(
                title="Europa - exigences de tracabilite et de securite",
                source_url="https://europa.eu/youreurope/business/product-requirements/compliance/index_fr.htm",
                snippet="Cadre de conformite europeen, obligations d'information et responsabilites des operateurs.",
                domain="europa.eu",
                document_type="web",
            ),
            CandidateSeed(
                title="Service-Public - etiquetage et obligations declaratives",
                source_url="https://www.service-public.fr/professionnels-entreprises/vosdroits/F23455",
                snippet="Fiche pratique sur les pieces a conserver, les obligations administratives et les demarches utiles.",
                domain="service-public.fr",
                document_type="web",
            ),
        ),
    ),
    DemoScenario(
        slug="cosmetique-france",
        payload=QueryCreate(
            theme="Formalites et conformite cosmetique en France",
            question="Quelles demarches, textes et jeux de donnees prioriser pour un corpus actionnable ?",
            keywords=["cosmetique", "france", "demarches", "ingredients"],
            preferred_domains=["legifrance.gouv.fr", "service-public.fr", "data.gouv.fr"],
            quality_target="balanced",
        ),
        candidate_seeds=(
            CandidateSeed(
                title="Legifrance - arrete relatif a la fabrication artisanale",
                source_url="https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000000111111",
                snippet="Texte national pour l'etiquetage, la securite et la conservation des preuves documentaires.",
                domain="legifrance.gouv.fr",
                document_type="web",
            ),
            CandidateSeed(
                title="Service-Public - demarches pour la mise sur le marche",
                source_url="https://www.service-public.fr/professionnels-entreprises/vosdroits/F35732",
                snippet="Guide administratif sur les formulaires, justificatifs et obligations a verifier avant diffusion.",
                domain="service-public.fr",
                document_type="web",
            ),
            CandidateSeed(
                title="data.gouv.fr - base ingredients cosmetiques",
                source_url="https://www.data.gouv.fr/fr/datasets/base-ingredients-cosmetiques/",
                snippet="Jeu de donnees ouvert pour recouper ingredients, metadonnees, references et enrichissement du corpus.",
                domain="data.gouv.fr",
                document_type="web",
            ),
        ),
    ),
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Genere deux corpus de demonstration KFabric.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8010", help="URL publique de l'application pour les liens de sortie.")
    parser.add_argument("--output", type=Path, default=None, help="Fichier JSON de sortie pour le manifeste.")
    args = parser.parse_args()

    settings = AppSettings()
    settings.ensure_storage()
    init_db(settings)
    session_factory = get_session_factory(settings.database_url)

    manifest = {
        "base_url": args.base_url.rstrip("/"),
        "database_url": settings.database_url,
        "storage_path": str(settings.storage_path),
        "scenarios": [],
    }

    with session_factory() as session:
        orchestrator = Orchestrator(session=session, settings=settings)
        for scenario in SCENARIOS:
            manifest["scenarios"].append(_run_scenario(orchestrator, scenario, manifest["base_url"]))

    output_text = json.dumps(manifest, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output_text, encoding="utf-8")
    print(output_text)


def _run_scenario(orchestrator: Orchestrator, scenario: DemoScenario, base_url: str) -> dict[str, Any]:
    query = orchestrator.create_query(scenario.payload)
    candidates = orchestrator.discover(query.id)
    _apply_candidate_seeds(orchestrator.session, candidates, scenario.candidate_seeds)

    analyzed_results: list[dict[str, Any]] = []
    for candidate in candidates[: len(scenario.candidate_seeds)]:
        collected = orchestrator.collect_candidate(candidate.id)
        analyzed_results.append(orchestrator.analyze_document(collected.id))

    if analyzed_results:
        last_parsed_id = analyzed_results[-1]["parsed_document"].id
        orchestrator.override_decision(last_parsed_id, accepted=False)

    for result in analyzed_results[:2]:
        decision_status = result["decision"].status
        if decision_status not in (
            DocumentDecisionStatus.ACCEPTED.value,
            DocumentDecisionStatus.MANUAL_ACCEPTED.value,
        ):
            orchestrator.override_decision(result["parsed_document"].id, accepted=True)

    clusters = orchestrator.consolidate_fragments(query.id)
    synthesis = orchestrator.create_synthesis(query.id)
    corpus = orchestrator.build_corpus(query.id)
    index_payload = orchestrator.prepare_index(corpus.id)

    return {
        "slug": scenario.slug,
        "query_id": query.id,
        "query_title": query.theme or query.question or query.id,
        "dashboard_url": f"{base_url}/queries/{query.id}",
        "corpus_id": corpus.id,
        "corpus_title": corpus.title,
        "api_export_markdown_url": f"{base_url}/api/v1/corpora/{corpus.id}:export?format=markdown",
        "api_export_html_url": f"{base_url}/api/v1/corpora/{corpus.id}:export?format=html",
        "web_export_html_url": f"{base_url}/web/corpora/{corpus.id}/export.html",
        "web_export_markdown_url": f"{base_url}/web/corpora/{corpus.id}/export.md",
        "candidate_count": len(candidates),
        "cluster_count": len(clusters),
        "synthesis_id": synthesis.id,
        "index_chunk_count": int(index_payload["chunk_count"]),
    }


def _apply_candidate_seeds(
    session,
    candidates: list[CandidateDocument],
    seeds: tuple[CandidateSeed, ...],
) -> None:
    for candidate, seed in zip(candidates, seeds, strict=False):
        candidate.title = seed.title
        candidate.source_url = seed.source_url
        candidate.snippet = seed.snippet
        candidate.domain = seed.domain
        candidate.document_type = seed.document_type
        candidate.discovery_source = "demo_curated"
    session.commit()


if __name__ == "__main__":
    main()
