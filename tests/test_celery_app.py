from __future__ import annotations


def test_configure_celery_app_uses_memory_backend_in_eager_mode(monkeypatch):
    monkeypatch.setenv("KFABRIC_CELERY_ALWAYS_EAGER", "true")

    from kfabric.config import get_settings
    from kfabric.workers.celery_app import celery_app, configure_celery_app

    get_settings.cache_clear()
    configure_celery_app()

    assert celery_app.conf.task_always_eager is True
    assert celery_app.conf.result_backend == "cache+memory://"
