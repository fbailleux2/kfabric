from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from kfabric.config import AppSettings, get_settings
from kfabric.infra.db import get_db_session
from kfabric.services.orchestrator import Orchestrator


def get_runtime_settings() -> AppSettings:
    return get_settings()


def get_db() -> Generator[Session, None, None]:
    yield from get_db_session()


def require_api_key(
    settings: AppSettings = Depends(get_runtime_settings),
    x_api_key: str | None = Header(default=None),
) -> None:
    if not settings.api_key:
        return
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


def get_orchestrator(
    db: Session = Depends(get_db),
    settings: AppSettings = Depends(get_runtime_settings),
) -> Orchestrator:
    return Orchestrator(session=db, settings=settings)
