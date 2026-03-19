from __future__ import annotations

from collections.abc import Generator
from hashlib import sha256
from secrets import compare_digest

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from kfabric.config import AppSettings, get_settings
from kfabric.infra.db import get_db_session
from kfabric.services.orchestrator import Orchestrator

WEB_SESSION_COOKIE = "kfabric_session"


def get_runtime_settings() -> AppSettings:
    return get_settings()


def get_db() -> Generator[Session, None, None]:
    yield from get_db_session()


def require_api_key(
    request: Request,
    settings: AppSettings = Depends(get_runtime_settings),
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> None:
    request.state.api_authenticated = False
    if not settings.api_key:
        request.state.api_authenticated = True
        return

    provided_key = x_api_key or _extract_bearer_token(authorization)
    if not provided_key or not compare_digest(provided_key, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    request.state.api_authenticated = True


def require_web_session(
    request: Request,
    settings: AppSettings = Depends(get_runtime_settings),
    kfabric_session: str | None = Cookie(default=None),
) -> None:
    if _is_public_web_path(request.url.path):
        request.state.web_authenticated = not bool(settings.api_key)
        return

    if not settings.api_key:
        request.state.web_authenticated = True
        return

    expected = _build_web_session_token(settings.api_key)
    request.state.web_authenticated = bool(kfabric_session and compare_digest(kfabric_session, expected))
    if not request.state.web_authenticated:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Web session required")


def issue_web_session_cookie_value(api_key: str) -> str:
    return _build_web_session_token(api_key)


def get_orchestrator(
    db: Session = Depends(get_db),
    settings: AppSettings = Depends(get_runtime_settings),
) -> Orchestrator:
    return Orchestrator(session=db, settings=settings)


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _build_web_session_token(api_key: str) -> str:
    return sha256(f"kfabric-web-session:{api_key}".encode("utf-8")).hexdigest()


def _is_public_web_path(path: str) -> bool:
    return path in {"/auth", "/web/auth/session", "/web/auth/logout"}
