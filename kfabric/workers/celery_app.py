from __future__ import annotations

from celery import Celery

from kfabric.config import get_settings


settings = get_settings()

celery_app = Celery(
    "kfabric",
    broker=settings.rabbitmq_url,
    backend=settings.redis_url,
    include=["kfabric.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    task_track_started=True,
)
