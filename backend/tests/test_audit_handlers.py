"""The audit module's own behavior: recording an event, resolving/snapshotting the actor's name,
and ``ListAuditEvents``'s filters and pagination. Coverage of *which* commands record an event
(and that a failing one leaves none) lives next to each of those commands' own tests.
"""

from datetime import timedelta
from uuid import uuid4

from support import ADMIN, UserFactory
from time_reporting.core.cqrs import Bus
from time_reporting.modules.audit.contracts import AuditAction, ListAuditEvents, RecordAuditEvent
from time_reporting.modules.users.contracts import UpdateUser


async def test_record_audit_event_resolves_and_snapshots_the_actor_name(
    bus: Bus, make_user: UserFactory
) -> None:
    actor = await make_user(name="Alice Actor", roles=ADMIN)

    await bus.execute(
        RecordAuditEvent(
            actor_id=actor.id,
            action=AuditAction.USER_CREATED,
            entity_type="user",
            entity_id=str(uuid4()),
            summary="Something happened",
        )
    )
    # Renaming the actor afterwards must not change what the already-recorded event shows.
    await bus.execute(UpdateUser(user_id=actor.id, acting_user_id=actor.id, name="Alice Renamed"))

    page = await bus.query(ListAuditEvents(limit=10, offset=0, actor_id=actor.id))

    assert len(page.items) == 1
    assert page.items[0].actor_id == actor.id
    assert page.items[0].actor_name == "Alice Actor"


async def test_record_audit_event_with_no_actor(bus: Bus) -> None:
    entity_id = str(uuid4())

    await bus.execute(
        RecordAuditEvent(
            actor_id=None,
            action=AuditAction.PUBLIC_HOLIDAYS_IMPORTED,
            entity_type="calendar",
            entity_id=entity_id,
            summary="Imported from the CLI",
            details={"year": 2026, "added": 3},
        )
    )

    page = await bus.query(
        ListAuditEvents(limit=10, offset=0, entity_type="calendar", entity_id=entity_id)
    )

    assert len(page.items) == 1
    event = page.items[0]
    assert event.actor_id is None
    assert event.actor_name is None
    assert event.summary == "Imported from the CLI"
    assert event.details == {"year": 2026, "added": 3}


async def test_list_audit_events_filters_by_action_entity_type_and_id(bus: Bus) -> None:
    entity_id = str(uuid4())
    await bus.execute(
        RecordAuditEvent(
            actor_id=None,
            action=AuditAction.CUSTOMER_ARCHIVED,
            entity_type="customer",
            entity_id=entity_id,
            summary="Archived",
        )
    )
    await bus.execute(
        RecordAuditEvent(
            actor_id=None,
            action=AuditAction.CUSTOMER_DELETED,
            entity_type="customer",
            entity_id=entity_id,
            summary="Deleted",
        )
    )
    await bus.execute(
        RecordAuditEvent(
            actor_id=None,
            action=AuditAction.CUSTOMER_ARCHIVED,
            entity_type="customer",
            entity_id=str(uuid4()),
            summary="A different customer entirely",
        )
    )

    by_action = await bus.query(
        ListAuditEvents(
            limit=10, offset=0, entity_type="customer", action=AuditAction.CUSTOMER_ARCHIVED
        )
    )
    assert len(by_action.items) == 2

    by_entity = await bus.query(
        ListAuditEvents(limit=10, offset=0, entity_type="customer", entity_id=entity_id)
    )
    assert {event.action for event in by_entity.items} == {
        AuditAction.CUSTOMER_ARCHIVED,
        AuditAction.CUSTOMER_DELETED,
    }


async def test_list_audit_events_filters_by_date_range(bus: Bus) -> None:
    entity_id = str(uuid4())
    await bus.execute(
        RecordAuditEvent(
            actor_id=None,
            action=AuditAction.PROJECT_ARCHIVED,
            entity_type="project",
            entity_id=entity_id,
            summary="Archived",
        )
    )
    recorded = (
        await bus.query(
            ListAuditEvents(limit=10, offset=0, entity_type="project", entity_id=entity_id)
        )
    ).items[0]

    within_range = await bus.query(
        ListAuditEvents(
            limit=10,
            offset=0,
            entity_type="project",
            entity_id=entity_id,
            occurred_from=recorded.occurred_at - timedelta(minutes=1),
            occurred_to=recorded.occurred_at + timedelta(minutes=1),
        )
    )
    assert len(within_range.items) == 1

    before_it = await bus.query(
        ListAuditEvents(
            limit=10,
            offset=0,
            entity_type="project",
            entity_id=entity_id,
            occurred_to=recorded.occurred_at - timedelta(minutes=1),
        )
    )
    assert before_it.items == ()

    after_it = await bus.query(
        ListAuditEvents(
            limit=10,
            offset=0,
            entity_type="project",
            entity_id=entity_id,
            occurred_from=recorded.occurred_at + timedelta(minutes=1),
        )
    )
    assert after_it.items == ()


async def test_list_audit_events_is_paginated_newest_first(bus: Bus) -> None:
    entity_type = f"paginated-{uuid4()}"
    for index in range(3):
        await bus.execute(
            RecordAuditEvent(
                actor_id=None,
                action=AuditAction.PROJECT_ARCHIVED,
                entity_type=entity_type,
                entity_id=str(index),
                summary=f"Event {index}",
            )
        )

    page = await bus.query(ListAuditEvents(limit=2, offset=0, entity_type=entity_type))

    assert page.total == 3
    assert len(page.items) == 2
    assert (page.limit, page.offset) == (2, 0)
    assert [event.summary for event in page.items] == ["Event 2", "Event 1"]

    second_page = await bus.query(ListAuditEvents(limit=2, offset=2, entity_type=entity_type))
    assert [event.summary for event in second_page.items] == ["Event 0"]
