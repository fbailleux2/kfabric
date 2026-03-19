from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "kfabric-test.db"
    storage_path = tmp_path / "storage"
    monkeypatch.setenv("KFABRIC_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("KFABRIC_STORAGE_PATH", str(storage_path))
    monkeypatch.setenv("KFABRIC_ENABLE_MCP", "true")
    monkeypatch.setenv("KFABRIC_REMOTE_DISCOVERY_ENABLED", "false")
    monkeypatch.setenv("KFABRIC_REMOTE_COLLECTION_ENABLED", "false")

    from kfabric.config import get_settings
    from kfabric.infra.db import get_engine, get_session_factory

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    from kfabric.api.app import create_app

    return create_app()


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client
