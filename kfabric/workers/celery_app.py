from __future__ import annotations

from celery import Celery

from kfabric.config import AppSettings, get_settings


celery_app = Celery(
    "kfabric",
    include=["kfabric.workers.tasks"],
)


def configure_celery_app(settings: AppSettings | None = None) -> Celery:
    settings = settings or get_settings()
    result_backend = "cache+memory://" if settings.celery_always_eager else settings.redis_url

    celery_app.conf.update(
        broker_url=settings.rabbitmq_url,
        result_backend=result_backend,
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        task_track_started=True,
        task_always_eager=settings.celery_always_eager,
        task_eager_propagates=True,
        task_store_eager_result=False,
    )
    return celery_app


configure_celery_app()
