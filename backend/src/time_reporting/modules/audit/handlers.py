"""Command and query handlers of the audit module (registered in ``audit.module``)."""

from time_reporting.core.cqrs import Bus
from time_reporting.modules.audit.contracts import (
    AuditAction,
    AuditEventDTO,
    AuditEventPageDTO,
    ListAuditEvents,
    RecordAuditEvent,
)
from time_reporting.modules.audit.models import AuditEvent
from time_reporting.modules.audit.repository import AuditEventRepository
from time_reporting.modules.users.contracts import GetUserById


def to_dto(event: AuditEvent) -> AuditEventDTO:
    return AuditEventDTO(
        id=event.id,
        occurred_at=event.occurred_at,
        actor_id=event.actor_id,
        actor_name=event.actor_name,
        action=AuditAction(event.action),
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        summary=event.summary,
        details=event.details,
    )


class RecordAuditEventHandler:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._events = AuditEventRepository(bus.session)

    async def handle(self, command: RecordAuditEvent) -> None:
        actor_name = None
        if command.actor_id is not None:
            actor = await self._bus.query(GetUserById(user_id=command.actor_id))
            # A deleted actor's audit rows already carry their own `actor_name` snapshot from when
            # they were recorded; this branch is only reachable for one written *while* the actor
            # still existed, so `actor` is never `None` in practice.
            actor_name = actor.name if actor is not None else None
        await self._events.save(
            AuditEvent(
                actor_id=command.actor_id,
                actor_name=actor_name,
                action=command.action.value,
                entity_type=command.entity_type,
                entity_id=command.entity_id,
                summary=command.summary,
                details=command.details,
            )
        )


class ListAuditEventsHandler:
    def __init__(self, bus: Bus) -> None:
        self._events = AuditEventRepository(bus.session)

    async def handle(self, query: ListAuditEvents) -> AuditEventPageDTO:
        action = query.action.value if query.action is not None else None
        events = await self._events.get_page(
            action=action,
            entity_type=query.entity_type,
            entity_id=query.entity_id,
            actor_id=query.actor_id,
            occurred_from=query.occurred_from,
            occurred_to=query.occurred_to,
            limit=query.limit,
            offset=query.offset,
        )
        total = await self._events.count(
            action=action,
            entity_type=query.entity_type,
            entity_id=query.entity_id,
            actor_id=query.actor_id,
            occurred_from=query.occurred_from,
            occurred_to=query.occurred_to,
        )
        return AuditEventPageDTO(
            items=tuple(to_dto(event) for event in events),
            total=total,
            limit=query.limit,
            offset=query.offset,
        )
