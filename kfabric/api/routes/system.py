from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from kfabric import __version__
from kfabric.api.deps import get_db, get_runtime_settings, require_api_key
from kfabric.api.serializers import serialize_audit_event, serialize_version
from kfabric.config import AppSettings
from kfabric.domain.schemas import AuditEventResponse, HealthResponse, VersionResponse
from kfabric.infra.models import AuditEvent
from kfabric.infra.observability import get_metrics_payload


router = APIRouter(tags=["system"], dependencies=[Depends(require_api_key)])


@router.get("/health", response_model=HealthResponse)
def health(settings: AppSettings = Depends(get_runtime_settings)) -> HealthResponse:
    return HealthResponse(status="ok", service=settings.app_name, version=__version__)


@router.get("/version", response_model=VersionResponse)
def version(settings: AppSettings = Depends(get_runtime_settings)) -> VersionResponse:
    return serialize_version(settings.app_name, __version__, settings.env, settings.secure_mode)


@router.get("/metrics")
def metrics(settings: AppSettings = Depends(get_runtime_settings)) -> Response:
    if not settings.enable_metrics:
        return Response(content=b"# Metrics disabled\n", media_type="text/plain")
    payload, media_type = get_metrics_payload()
    return Response(content=payload, media_type=media_type)


@router.get("/audit-events", response_model=list[AuditEventResponse])
def list_audit_events(
    limit: int = 50,
    db: Session = Depends(get_db),
) -> list[AuditEventResponse]:
    events = list(db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(min(limit, 200))))
    return [serialize_audit_event(event) for event in events]
