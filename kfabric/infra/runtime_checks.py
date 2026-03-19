from __future__ import annotations

import socket
from pathlib import Path
from time import perf_counter
from urllib.parse import urlparse

import httpx
from redis import Redis
from sqlalchemy import text

from kfabric import __version__
from kfabric.config import AppSettings
from kfabric.infra.db import get_engine


def collect_runtime_status(settings: AppSettings) -> dict[str, object]:
    checks = {
        "database": _check_database(settings),
        "storage": _check_storage(settings.storage_path),
        "redis": _check_redis(settings.redis_url),
        "rabbitmq": _check_tcp_service("rabbitmq", settings.rabbitmq_url, default_port=5672),
        "qdrant": _check_http_service("qdrant", settings.qdrant_url, path="/collections"),
    }
    core_failures = [name for name in ("database", "storage") if checks[name]["status"] != "ok"]
    optional_failures = [name for name in ("redis", "rabbitmq", "qdrant") if checks[name]["status"] != "ok"]

    if core_failures:
        status = "not_ready"
    elif optional_failures:
        status = "degraded"
    else:
        status = "ready"

    return {
        "status": status,
        "service": settings.app_name,
        "version": __version__,
        "environment": settings.env,
        "secure_mode": settings.secure_mode,
        "dependencies": checks,
    }


def _check_database(settings: AppSettings) -> dict[str, object]:
    start = perf_counter()
    try:
        engine = get_engine(settings.database_url)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return _ok_result("database", start, settings.database_url)
    except Exception as exc:
        return _error_result("database", start, settings.database_url, exc)


def _check_storage(storage_path: Path) -> dict[str, object]:
    start = perf_counter()
    try:
        storage_path.mkdir(parents=True, exist_ok=True)
        probe = storage_path / ".healthcheck"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return _ok_result("storage", start, str(storage_path))
    except Exception as exc:
        return _error_result("storage", start, str(storage_path), exc)


def _check_redis(redis_url: str) -> dict[str, object]:
    start = perf_counter()
    try:
        Redis.from_url(redis_url, socket_timeout=2.0).ping()
        return _ok_result("redis", start, redis_url)
    except Exception as exc:
        return _error_result("redis", start, redis_url, exc)


def _check_tcp_service(name: str, raw_url: str, *, default_port: int) -> dict[str, object]:
    start = perf_counter()
    try:
        parsed = urlparse(raw_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or default_port
        with socket.create_connection((host, port), timeout=2.0):
            pass
        return _ok_result(name, start, raw_url)
    except Exception as exc:
        return _error_result(name, start, raw_url, exc)


def _check_http_service(name: str, base_url: str, *, path: str) -> dict[str, object]:
    start = perf_counter()
    target = base_url.rstrip("/") + path
    try:
        response = httpx.get(target, timeout=2.0, headers={"User-Agent": "KFabric/0.1"})
        response.raise_for_status()
        return _ok_result(name, start, target)
    except Exception as exc:
        return _error_result(name, start, target, exc)


def _ok_result(name: str, started_at: float, target: str) -> dict[str, object]:
    return {
        "name": name,
        "status": "ok",
        "target": target,
        "latency_ms": round((perf_counter() - started_at) * 1000, 2),
        "detail": "",
    }


def _error_result(name: str, started_at: float, target: str, exc: Exception) -> dict[str, object]:
    return {
        "name": name,
        "status": "error",
        "target": target,
        "latency_ms": round((perf_counter() - started_at) * 1000, 2),
        "detail": str(exc),
    }
