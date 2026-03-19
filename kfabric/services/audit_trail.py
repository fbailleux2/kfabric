from __future__ import annotations

from sqlalchemy.orm import Session

from kfabric.infra.models import AuditEvent


def record_audit_event(
    session: Session,
    event_type: str,
    entity_type: str,
    entity_id: str,
    trace_id: str,
    actor: str = "system",
    payload: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        trace_id=trace_id,
        actor=actor,
        payload=payload or {},
    )
    session.add(event)
    session.flush()
    return event

