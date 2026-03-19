from __future__ import annotations

from kfabric.config import get_settings
from kfabric.infra.db import get_session_factory
from kfabric.services.orchestrator import Orchestrator
from kfabric.workers.celery_app import celery_app


def _orchestrator() -> Orchestrator:
    session = get_session_factory(get_settings().database_url)()
    return Orchestrator(session=session, settings=get_settings())


@celery_app.task(name="kfabric.discover")
def discover_query(query_id: str) -> list[str]:
    orchestrator = _orchestrator()
    try:
        return [candidate.id for candidate in orchestrator.discover(query_id)]
    finally:
        orchestrator.session.close()


@celery_app.task(name="kfabric.collect_candidate")
def collect_candidate(candidate_id: str) -> str:
    orchestrator = _orchestrator()
    try:
        return orchestrator.collect_candidate(candidate_id).id
    finally:
        orchestrator.session.close()


@celery_app.task(name="kfabric.analyze_document")
def analyze_document(document_id: str) -> str:
    orchestrator = _orchestrator()
    try:
        return orchestrator.analyze_document(document_id)["parsed_document"].id
    finally:
        orchestrator.session.close()


@celery_app.task(name="kfabric.consolidate_fragments")
def consolidate_fragments(query_id: str) -> list[str]:
    orchestrator = _orchestrator()
    try:
        return [cluster.id for cluster in orchestrator.consolidate_fragments(query_id)]
    finally:
        orchestrator.session.close()


@celery_app.task(name="kfabric.create_synthesis")
def create_synthesis(query_id: str, fragment_ids: list[str] | None = None) -> str:
    orchestrator = _orchestrator()
    try:
        return orchestrator.create_synthesis(query_id, fragment_ids).id
    finally:
        orchestrator.session.close()


@celery_app.task(name="kfabric.build_corpus")
def build_corpus(query_id: str) -> str:
    orchestrator = _orchestrator()
    try:
        return orchestrator.build_corpus(query_id).id
    finally:
        orchestrator.session.close()


@celery_app.task(name="kfabric.prepare_index")
def prepare_index(corpus_id: str) -> dict[str, object]:
    orchestrator = _orchestrator()
    try:
        return orchestrator.prepare_index(corpus_id)
    finally:
        orchestrator.session.close()
