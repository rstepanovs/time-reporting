"""Audit log HTTP API — admin only."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from time_reporting.api.deps import BusDep
from time_reporting.modules.audit.contracts import AuditAction, ListAuditEvents
from time_reporting.modules.audit.schemas import AuditEventPageResponse
from time_reporting.modules.auth.dependencies import AdminDep

router = APIRouter(prefix="/admin/audit-events", tags=["audit"])


@router.get("")
async def list_audit_events(
    _admin: AdminDep,
    bus: BusDep,
    action: Annotated[AuditAction | None, Query()] = None,
    entity_type: Annotated[str | None, Query(max_length=50)] = None,
    entity_id: Annotated[str | None, Query(max_length=255)] = None,
    actor_id: Annotated[UUID | None, Query()] = None,
    occurred_from: Annotated[datetime | None, Query()] = None,
    occurred_to: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditEventPageResponse:
    page = await bus.query(
        ListAuditEvents(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            occurred_from=occurred_from,
            occurred_to=occurred_to,
            limit=limit,
            offset=offset,
        )
    )
    return AuditEventPageResponse.model_validate(page)
