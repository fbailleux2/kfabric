from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


def _build_secured_client(tmp_path: Path, monkeypatch) -> TestClient:
    db_path = tmp_path / "kfabric-secured.db"
    storage_path = tmp_path / "storage"
    monkeypatch.setenv("KFABRIC_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("KFABRIC_STORAGE_PATH", str(storage_path))
    monkeypatch.setenv("KFABRIC_ENABLE_MCP", "true")
    monkeypatch.setenv("KFABRIC_REMOTE_DISCOVERY_ENABLED", "false")
    monkeypatch.setenv("KFABRIC_REMOTE_COLLECTION_ENABLED", "false")
    monkeypatch.setenv("KFABRIC_API_KEY", "test-secret")

    from kfabric.config import get_settings
    from kfabric.infra.db import get_engine, get_session_factory

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    from kfabric.api.app import create_app

    return TestClient(create_app())


def test_api_requires_api_key_and_returns_consistent_error(tmp_path: Path, monkeypatch):
    with _build_secured_client(tmp_path, monkeypatch) as client:
        response = client.get("/api/v1/version")

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"
        assert response.json()["error"]["message"] == "API key required"
        assert "trace_id" in response.json()["error"]
        assert response.headers["www-authenticate"] == "Bearer"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"


def test_health_and_readiness_are_public_for_runtime_supervision(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "kfabric.api.routes.system.collect_runtime_status",
        lambda settings: {
            "status": "degraded",
            "service": settings.app_name,
            "version": "0.1.0",
            "environment": settings.env,
            "secure_mode": settings.secure_mode,
            "dependencies": {
                "database": {
                    "name": "database",
                    "status": "ok",
                    "target": settings.database_url,
                    "latency_ms": 1.0,
                    "detail": "",
                },
                "storage": {
                    "name": "storage",
                    "status": "ok",
                    "target": str(settings.storage_path),
                    "latency_ms": 1.0,
                    "detail": "",
                },
                "redis": {
                    "name": "redis",
                    "status": "error",
                    "target": settings.redis_url,
                    "latency_ms": 1.0,
                    "detail": "connection refused",
                },
            },
        },
    )

    with _build_secured_client(tmp_path, monkeypatch) as client:
        health = client.get("/api/v1/health")
        readiness = client.get("/api/v1/readiness")

        assert health.status_code == 200
        assert health.json()["status"] == "ok"
        assert readiness.status_code == 200
        assert readiness.json()["status"] == "degraded"
        assert readiness.json()["dependencies"]["redis"]["status"] == "error"


def test_api_accepts_bearer_token_and_sets_security_headers(tmp_path: Path, monkeypatch):
    with _build_secured_client(tmp_path, monkeypatch) as client:
        response = client.get("/api/v1/version", headers={"Authorization": "Bearer test-secret"})

        assert response.status_code == 200
        assert response.json()["service"] == "KFabric"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert response.headers["cache-control"] == "no-store"


def test_readiness_returns_503_when_core_dependency_fails(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "kfabric.api.routes.system.collect_runtime_status",
        lambda settings: {
            "status": "not_ready",
            "service": settings.app_name,
            "version": "0.1.0",
            "environment": settings.env,
            "secure_mode": settings.secure_mode,
            "dependencies": {
                "database": {
                    "name": "database",
                    "status": "error",
                    "target": settings.database_url,
                    "latency_ms": 2.0,
                    "detail": "database unavailable",
                }
            },
        },
    )

    with _build_secured_client(tmp_path, monkeypatch) as client:
        response = client.get("/api/v1/readiness")

        assert response.status_code == 503
        assert response.json()["status"] == "not_ready"


def test_web_requires_session_then_allows_login(tmp_path: Path, monkeypatch):
    with _build_secured_client(tmp_path, monkeypatch) as client:
        protected_response = client.get("/", follow_redirects=False)
        assert protected_response.status_code == 303
        assert protected_response.headers["location"] == "/auth?next=/"

        auth_page = client.get("/auth")
        assert auth_page.status_code == 200
        assert "Authentification requise" in auth_page.text
        assert "content-security-policy" in auth_page.headers

        login_response = client.post(
            "/web/auth/session",
            data={"api_key": "test-secret", "next_path": "/"},
            follow_redirects=False,
        )
        assert login_response.status_code == 303
        assert login_response.headers["location"] == "/"
        assert "kfabric_session=" in login_response.headers["set-cookie"]

        home = client.get("/")
        assert home.status_code == 200
        assert "KFabric" in home.text


def test_web_login_rejects_invalid_key(tmp_path: Path, monkeypatch):
    with _build_secured_client(tmp_path, monkeypatch) as client:
        response = client.post(
            "/web/auth/session",
            data={"api_key": "wrong-secret", "next_path": "/"},
        )

        assert response.status_code == 401
        assert "Clé API invalide" in response.text
