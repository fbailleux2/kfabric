from __future__ import annotations

from collections.abc import Generator
from secrets import compare_digest

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from kfabric.config import AppSettings, get_settings
from kfabric.infra.db import get_db_session
from kfabric.services.auth_service import (
    AuthContext,
    resolve_api_token,
    resolve_web_session,
)
from kfabric.services.orchestrator import Orchestrator

WEB_SESSION_COOKIE = "kfabric_session"


def get_runtime_settings() -> AppSettings:
    return get_settings()


def get_db() -> Generator[Session, None, None]:
    yield from get_db_session()


def get_request_principal(
    request: Request,
    db: Session = Depends(get_db),
    settings: AppSettings = Depends(get_runtime_settings),
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
    kfabric_session: str | None = Cookie(default=None),
) -> AuthContext:
    cached = getattr(request.state, "principal", None)
    if cached is not None:
        return cached

    raw_api_token = x_api_key or _extract_bearer_token(authorization)
    principal = AuthContext()
    if raw_api_token:
        if settings.api_key and compare_digest(raw_api_token, settings.api_key):
            principal = AuthContext(user=None, auth_mode="legacy_api_key", is_system=True)
        else:
            token = resolve_api_token(db, raw_api_token)
            if token is not None:
                principal = AuthContext(user=token.user, auth_mode="api_token")
    if not principal.is_authenticated and kfabric_session:
        web_session = resolve_web_session(db, kfabric_session)
        if web_session is not None:
            principal = AuthContext(user=web_session.user, auth_mode="web_session")

    request.state.principal = principal
    request.state.current_user = principal.user
    request.state.web_authenticated = principal.auth_mode == "web_session"
    request.state.api_authenticated = principal.auth_mode in {"api_token", "legacy_api_key"}
    return principal


def require_authenticated_principal(
    request: Request,
    principal: AuthContext = Depends(get_request_principal),
    settings: AppSettings = Depends(get_runtime_settings),
    db: Session = Depends(get_db),
) -> AuthContext:
    if _is_public_api_path(request.url.path):
        return principal
    if principal.is_authenticated:
        return principal
    if not _auth_required(settings, request, db):
        return principal
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_admin_principal(principal: AuthContext = Depends(require_authenticated_principal)) -> AuthContext:
    if principal.is_admin:
        return principal
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")


def require_web_session(
    request: Request,
    settings: AppSettings = Depends(get_runtime_settings),
    principal: AuthContext = Depends(get_request_principal),
    db: Session = Depends(get_db),
) -> None:
    request.state.principal = principal
    request.state.current_user = principal.user
    request.state.web_authenticated = principal.auth_mode == "web_session"
    request.state.bootstrap_required = not _has_users_cached(request, db)

    if _is_public_web_path(request.url.path):
        return

    if principal.auth_mode == "web_session":
        return

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Web session required")


def require_admin_web_session(
    principal: AuthContext = Depends(get_request_principal),
) -> AuthContext:
    if principal.is_admin:
        return principal
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")


def get_orchestrator(
    db: Session = Depends(get_db),
    settings: AppSettings = Depends(get_runtime_settings),
    principal: AuthContext = Depends(get_request_principal),
) -> Orchestrator:
    return Orchestrator(session=db, settings=settings, principal=principal)


def auth_bootstrap_required(
    request: Request,
    db: Session = Depends(get_db),
) -> bool:
    return not _has_users_cached(request, db)


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _is_public_web_path(path: str) -> bool:
    return path in {"/auth", "/web/auth/session", "/web/auth/bootstrap", "/web/auth/logout"}


def _is_public_api_path(path: str) -> bool:
    return path in {
        "/api/v1/health",
        "/api/v1/readiness",
        "/api/v1/auth/bootstrap-admin",
        "/api/v1/auth/login",
    }


def _auth_required(settings: AppSettings, request: Request, db: Session) -> bool:
    return True


def _has_users_cached(request: Request, db: Session) -> bool:
    cached = getattr(request.state, "has_users", None)
    if cached is not None:
        return cached
    from kfabric.services.auth_service import has_users

    request.state.has_users = has_users(db)
    return request.state.has_users
