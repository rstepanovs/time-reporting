"""Persistence of audit events. Flushes but never commits — the bus owns transactions."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from time_reporting.modules.audit.models import AuditEvent


class AuditEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, event: AuditEvent) -> None:
        self._session.add(event)
        await self._session.flush()

    async def get_page(
        self,
        *,
        action: str | None,
        entity_type: str | None,
        entity_id: str | None,
        actor_id: UUID | None,
        occurred_from: datetime | None,
        occurred_to: datetime | None,
        limit: int,
        offset: int,
    ) -> Sequence[AuditEvent]:
        """Newest first."""
        statement = (
            self._filtered(
                select(AuditEvent),
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                actor_id=actor_id,
                occurred_from=occurred_from,
                occurred_to=occurred_to,
            )
            .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id)
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.scalars(statement)
        return result.all()

    async def count(
        self,
        *,
        action: str | None,
        entity_type: str | None,
        entity_id: str | None,
        actor_id: UUID | None,
        occurred_from: datetime | None,
        occurred_to: datetime | None,
    ) -> int:
        statement = self._filtered(
            select(func.count()).select_from(AuditEvent),
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            occurred_from=occurred_from,
            occurred_to=occurred_to,
        )
        result = await self._session.execute(statement)
        return result.scalar_one()

    def _filtered[T: tuple[Any, ...]](
        self,
        statement: Select[T],
        *,
        action: str | None,
        entity_type: str | None,
        entity_id: str | None,
        actor_id: UUID | None,
        occurred_from: datetime | None,
        occurred_to: datetime | None,
    ) -> Select[T]:
        if action is not None:
            statement = statement.where(AuditEvent.action == action)
        if entity_type is not None:
            statement = statement.where(AuditEvent.entity_type == entity_type)
        if entity_id is not None:
            statement = statement.where(AuditEvent.entity_id == entity_id)
        if actor_id is not None:
            statement = statement.where(AuditEvent.actor_id == actor_id)
        if occurred_from is not None:
            statement = statement.where(AuditEvent.occurred_at >= occurred_from)
        if occurred_to is not None:
            statement = statement.where(AuditEvent.occurred_at <= occurred_to)
        return statement
