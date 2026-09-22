"""HTTP response models of the audit API."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from time_reporting.modules.audit.contracts import AuditAction


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    occurred_at: datetime
    actor_id: UUID | None
    actor_name: str | None
    action: AuditAction
    entity_type: str
    entity_id: str
    summary: str
    details: dict[str, Any] | None


class AuditEventPageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[AuditEventResponse]
    total: int
    limit: int
    offset: int
