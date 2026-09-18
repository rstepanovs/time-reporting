from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from support import ADMIN, MANAGER, CustomerFactory, ProjectFactory, UserFactory
from time_reporting.core.cqrs import Bus
from time_reporting.modules.audit.contracts import AuditAction, ListAuditEvents
from time_reporting.modules.expenses.contracts import (
    ApproveExpenseReport,
    CreateExpenseReport,
    ExpenseLineChange,
    ExpenseReportLockedError,
    GetExpenseReport,
    ReturnExpenseReport,
    SaveExpenseReportLines,
    SubmitExpenseReport,
)
from time_reporting.modules.projects.contracts import (
    AddProjectMember,
    BillingItemPreset,
    ListProjectBillingItems,
)
from time_reporting.modules.timesheets.contracts import (
    ApproveTimesheetWeek,
    BillingPeriodAlreadySentError,
    BillingPeriodLockedError,
    BillingPeriodNotFoundError,
    BillingPeriodNotReadyError,
    BillingPeriodStatus,
    CurrencyAmountDTO,
    GetTimesheetWeek,
    ListBillingPeriods,
    ReopenProjectBillingPeriod,
    ReturnTimesheetWeek,
    RowCommentChange,
    SaveTimesheetWeek,
    SendProjectMonthToBilling,
    SubmitTimesheetWeek,
    TimeEntryChange,
    TimesheetProjectNotFoundError,
)
from time_reporting.modules.users.contracts import UserNotFoundError

WEEK_1 = date(2026, 9, 7)
# Still draft: dates in this week fall in September (the same month as WEEK_1) but the week itself
# is never submitted/approved, so only the billing lock (not the week-status lock) can block it.
WEEK_2 = date(2026, 9, 14)
STRADDLING_WEEK = date(2026, 8, 31)  # spans August 31 .. September 6
IN_AUGUST_DAY = date(2026, 8, 31)


async def _normal_hours_item_id(bus: Bus, project_id: UUID) -> UUID:
    items = await bus.query(ListProjectBillingItems(project_id=project_id))
    return next(item.id for item in items if item.preset == BillingItemPreset.NORMAL_HOURS)


async def _book_and_approve(
    bus: Bus, *, worker_id: UUID, admin_id: UUID, item_id: UUID, entry_date: date, week_start: date
) -> None:
    await bus.execute(
        SaveTimesheetWeek(
            user_id=worker_id,
            week_start=week_start,
            changes=(
                TimeEntryChange(billing_item_id=item_id, date=entry_date, quantity=Decimal("4")),
            ),
        )
    )
    await bus.execute(SubmitTimesheetWeek(user_id=worker_id, week_start=week_start))
    await bus.execute(
        ApproveTimesheetWeek(user_id=worker_id, week_start=week_start, reviewer_id=admin_id)
    )


async def test_send_to_billing_happy_path(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    manager = await make_user(roles=MANAGER)
    admin = await make_user(roles=ADMIN)
    worker = await make_user()
    project = await make_project(manager_id=manager.id)
    await bus.execute(AddProjectMember(project_id=project.id, user_id=worker.id))
    item_id = await _normal_hours_item_id(bus, project.id)
    await _book_and_approve(
        bus,
        worker_id=worker.id,
        admin_id=admin.id,
        item_id=item_id,
        entry_date=WEEK_1,
        week_start=WEEK_1,
    )

    period = await bus.execute(
        SendProjectMonthToBilling(project_id=project.id, year=2026, month=9, sent_by_id=manager.id)
    )

    assert period.status is BillingPeriodStatus.SENT
    assert period.sent_by is not None
    assert period.sent_by.id == manager.id
    assert period.hours.normal_hours == Decimal("4")
    assert period.period_start == date(2026, 9, 1)
    assert period.period_end == date(2026, 9, 30)

    events = await bus.query(
        ListAuditEvents(
            limit=10,
            offset=0,
            action=AuditAction.BILLING_PERIOD_SENT,
            entity_type="billing_period",
            entity_id=f"{project.id}:2026-09-01",
        )
    )
    assert len(events.items) == 1
    assert events.items[0].actor_id == manager.id


async def test_send_to_billing_rolls_back_the_audit_event_on_later_failure(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``RecordAuditEvent`` is a nested command, so if anything after it in the same outer command
    still fails, the whole thing (including the audit row) rolls back together."""
    from time_reporting.modules.timesheets import billing as billing_module

    manager = await make_user(roles=MANAGER)
    admin = await make_user(roles=ADMIN)
    worker = await make_user()
    project = await make_project(manager_id=manager.id)
    await bus.execute(AddProjectMember(project_id=project.id, user_id=worker.id))
    item_id = await _normal_hours_item_id(bus, project.id)
    await _book_and_approve(
        bus,
        worker_id=worker.id,
        admin_id=admin.id,
        item_id=item_id,
        entry_date=WEEK_1,
        week_start=WEEK_1,
    )

    async def failing_period_dto(self: object, *args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(billing_module.BillingService, "_period_dto", failing_period_dto)

    with pytest.raises(RuntimeError, match="simulated failure"):
        await bus.execute(
            SendProjectMonthToBilling(
                project_id=project.id, year=2026, month=9, sent_by_id=manager.id
            )
        )

    events = await bus.query(
        ListAuditEvents(
            limit=10,
            offset=0,
            action=AuditAction.BILLING_PERIOD_SENT,
            entity_type="billing_period",
            entity_id=f"{project.id}:2026-09-01",
        )
    )
    assert events.items == ()


async def test_send_is_allowed_before_the_month_ends(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    manager = await make_user(roles=MANAGER)
    admin = await make_user(roles=ADMIN)
    worker = await make_user()
    project = await make_project(manager_id=manager.id)
    await bus.execute(AddProjectMember(project_id=project.id, user_id=worker.id))
    item_id = await _normal_hours_item_id(bus, project.id)
    await _book_and_approve(
        bus,
        worker_id=worker.id,
        admin_id=admin.id,
        item_id=item_id,
        entry_date=WEEK_1,
        week_start=WEEK_1,
    )

    # Sent well before September ends; no error.
    period = await bus.execute(
        SendProjectMonthToBilling(project_id=project.id, year=2026, month=9, sent_by_id=manager.id)
    )
    assert period.status is BillingPeriodStatus.SENT

    # WEEK_1 itself is now approved (and thus already locked by its own status); the billing
    # lock also reaches a still-draft week whose dates fall in the sent month.
    with pytest.raises(BillingPeriodLockedError):
        await bus.execute(
            SaveTimesheetWeek(
                user_id=worker.id,
                week_start=WEEK_2,
                changes=(
                    TimeEntryChange(billing_item_id=item_id, date=WEEK_2, quantity=Decimal("2")),
                ),
            )
        )


async def test_send_with_no_time_booked_is_not_ready(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    manager = await make_user(roles=MANAGER)
    project = await make_project(manager_id=manager.id)

    with pytest.raises(BillingPeriodNotReadyError):
        await bus.execute(
            SendProjectMonthToBilling(
                project_id=project.id, year=2026, month=9, sent_by_id=manager.id
            )
        )


async def test_send_with_an_unapproved_week_is_not_ready(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    manager = await make_user(roles=MANAGER)
    worker = await make_user()
    project = await make_project(manager_id=manager.id)
    await bus.execute(AddProjectMember(project_id=project.id, user_id=worker.id))
    item_id = await _normal_hours_item_id(bus, project.id)
    await bus.execute(
        SaveTimesheetWeek(
            user_id=worker.id,
            week_start=WEEK_1,
            changes=(TimeEntryChange(billing_item_id=item_id, date=WEEK_1, quantity=Decimal("4")),),
        )
    )

    with pytest.raises(BillingPeriodNotReadyError) as exc_info:
        await bus.execute(
            SendProjectMonthToBilling(
                project_id=project.id, year=2026, month=9, sent_by_id=manager.id
            )
        )
    assert exc_info.value.blocking_weeks == 1


async def test_send_twice_is_rejected(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    manager = await make_user(roles=MANAGER)
    admin = await make_user(roles=ADMIN)
    worker = await make_user()
    project = await make_project(manager_id=manager.id)
    await bus.execute(AddProjectMember(project_id=project.id, user_id=worker.id))
    item_id = await _normal_hours_item_id(bus, project.id)
    await _book_and_approve(
        bus,
        worker_id=worker.id,
        admin_id=admin.id,
        item_id=item_id,
        entry_date=WEEK_1,
        week_start=WEEK_1,
    )
    await bus.execute(
        SendProjectMonthToBilling(project_id=project.id, year=2026, month=9, sent_by_id=manager.id)
    )

    with pytest.raises(BillingPeriodAlreadySentError):
        await bus.execute(
            SendProjectMonthToBilling(
                project_id=project.id, year=2026, month=9, sent_by_id=manager.id
            )
        )


async def test_send_by_a_manager_who_is_not_this_projects_manager_is_allowed(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    manager = await make_user(roles=MANAGER)
    other_manager = await make_user(roles=MANAGER)
    worker = await make_user()
    project = await make_project(manager_id=manager.id)
    await bus.execute(AddProjectMember(project_id=project.id, user_id=worker.id))
    item_id = await _normal_hours_item_id(bus, project.id)
    await _book_and_approve(
        bus,
        worker_id=worker.id,
        admin_id=other_manager.id,
        item_id=item_id,
        entry_date=WEEK_1,
        week_start=WEEK_1,
    )

    period = await bus.execute(
        SendProjectMonthToBilling(
            project_id=project.id, year=2026, month=9, sent_by_id=other_manager.id
        )
    )
    assert period.status is BillingPeriodStatus.SENT


async def test_send_for_unknown_project_raises(bus: Bus, make_user: UserFactory) -> None:
    admin = await make_user(roles=ADMIN)
    with pytest.raises(TimesheetProjectNotFoundError):
        await bus.execute(
            SendProjectMonthToBilling(project_id=uuid4(), year=2026, month=9, sent_by_id=admin.id)
        )


async def test_send_by_unknown_user_raises(bus: Bus, make_project: ProjectFactory) -> None:
    project = await make_project()
    with pytest.raises(UserNotFoundError):
        await bus.execute(
            SendProjectMonthToBilling(project_id=project.id, year=2026, month=9, sent_by_id=uuid4())
        )


async def test_save_a_cell_in_a_locked_period_is_rejected(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    manager = await make_user(roles=MANAGER)
    admin = await make_user(roles=ADMIN)
    worker = await make_user()
    project = await make_project(manager_id=manager.id)
    await bus.execute(AddProjectMember(project_id=project.id, user_id=worker.id))
    item_id = await _normal_hours_item_id(bus, project.id)
    await _book_and_approve(
        bus,
        worker_id=worker.id,
        admin_id=admin.id,
        item_id=item_id,
        entry_date=WEEK_1,
        week_start=WEEK_1,
    )
    await bus.execute(
        SendProjectMonthToBilling(project_id=project.id, year=2026, month=9, sent_by_id=manager.id)
    )

    with pytest.raises(BillingPeriodLockedError):
        await bus.execute(
            SaveTimesheetWeek(
                user_id=worker.id,
                week_start=WEEK_2,
                changes=(
                    TimeEntryChange(billing_item_id=item_id, date=WEEK_2, quantity=Decimal("5")),
                ),
            )
        )


async def test_save_a_row_comment_in_a_locked_period_is_rejected(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    manager = await make_user(roles=MANAGER)
    admin = await make_user(roles=ADMIN)
    worker = await make_user()
    project = await make_project(manager_id=manager.id)
    await bus.execute(AddProjectMember(project_id=project.id, user_id=worker.id))
    item_id = await _normal_hours_item_id(bus, project.id)
    await _book_and_approve(
        bus,
        worker_id=worker.id,
        admin_id=admin.id,
        item_id=item_id,
        entry_date=WEEK_1,
        week_start=WEEK_1,
    )
    await bus.execute(
        SendProjectMonthToBilling(project_id=project.id, year=2026, month=9, sent_by_id=manager.id)
    )

    with pytest.raises(BillingPeriodLockedError):
        await bus.execute(
            SaveTimesheetWeek(
                user_id=worker.id,
                week_start=WEEK_2,
                changes=(),
                row_comments=(RowCommentChange(billing_item_id=item_id, comment="note"),),
            )
        )


async def test_locked_dates_are_clipped_to_the_sent_period_for_a_straddling_week(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    """The straddling week's own status locks it entirely for editing once it must be approved to
    send August (an accepted trade-off of week-level approval — see the implementation plan), but
    ``locked_dates``/``can_review`` still reflect only the actually-sent (August) days, not the
    week's September days."""
    manager = await make_user(roles=MANAGER)
    admin = await make_user(roles=ADMIN)
    worker = await make_user()
    project = await make_project(manager_id=manager.id)
    await bus.execute(AddProjectMember(project_id=project.id, user_id=worker.id))
    item_id = await _normal_hours_item_id(bus, project.id)
    await _book_and_approve(
        bus,
        worker_id=worker.id,
        admin_id=admin.id,
        item_id=item_id,
        entry_date=IN_AUGUST_DAY,
        week_start=STRADDLING_WEEK,
    )

    await bus.execute(
        SendProjectMonthToBilling(project_id=project.id, year=2026, month=8, sent_by_id=manager.id)
    )

    week = await bus.query(
        GetTimesheetWeek(user_id=worker.id, week_start=STRADDLING_WEEK, viewer_id=admin.id)
    )
    row = next(row for row in week.rows if row.billing_item.id == item_id)
    assert row.locked_dates == (IN_AUGUST_DAY,)
    assert week.can_review is False


async def test_return_a_week_locked_by_billing_is_rejected(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    manager = await make_user(roles=MANAGER)
    admin = await make_user(roles=ADMIN)
    worker = await make_user()
    project = await make_project(manager_id=manager.id)
    await bus.execute(AddProjectMember(project_id=project.id, user_id=worker.id))
    item_id = await _normal_hours_item_id(bus, project.id)
    await _book_and_approve(
        bus,
        worker_id=worker.id,
        admin_id=admin.id,
        item_id=item_id,
        entry_date=WEEK_1,
        week_start=WEEK_1,
    )
    await bus.execute(
        SendProjectMonthToBilling(project_id=project.id, year=2026, month=9, sent_by_id=manager.id)
    )

    with pytest.raises(BillingPeriodLockedError):
        await bus.execute(
            ReturnTimesheetWeek(
                user_id=worker.id,
                week_start=WEEK_1,
                reviewer_id=admin.id,
                comment="Please redo",
            )
        )


async def test_reopen_unlocks_the_period(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    manager = await make_user(roles=MANAGER)
    admin = await make_user(roles=ADMIN)
    worker = await make_user()
    project = await make_project(manager_id=manager.id)
    await bus.execute(AddProjectMember(project_id=project.id, user_id=worker.id))
    item_id = await _normal_hours_item_id(bus, project.id)
    await _book_and_approve(
        bus,
        worker_id=worker.id,
        admin_id=admin.id,
        item_id=item_id,
        entry_date=WEEK_1,
        week_start=WEEK_1,
    )
    await bus.execute(
        SendProjectMonthToBilling(project_id=project.id, year=2026, month=9, sent_by_id=manager.id)
    )

    await bus.execute(
        ReopenProjectBillingPeriod(
            project_id=project.id, period_start=date(2026, 9, 1), actor_id=admin.id
        )
    )

    events = await bus.query(
        ListAuditEvents(
            limit=10,
            offset=0,
            action=AuditAction.BILLING_PERIOD_REOPENED,
            entity_type="billing_period",
            entity_id=f"{project.id}:2026-09-01",
        )
    )
    assert len(events.items) == 1
    assert events.items[0].actor_id == admin.id

    # WEEK_1 itself stays locked by its own (still-approved) status; WEEK_2, blocked only by the
    # now-lifted billing lock, is editable again.
    updated = await bus.execute(
        SaveTimesheetWeek(
            user_id=worker.id,
            week_start=WEEK_2,
            changes=(TimeEntryChange(billing_item_id=item_id, date=WEEK_2, quantity=Decimal("6")),),
        )
    )
    row = next(row for row in updated.rows if row.billing_item.id == item_id)
    assert row.entries[0].quantity == Decimal("6")


async def test_reopen_unknown_period_raises(
    bus: Bus, make_user: UserFactory, make_project: ProjectFactory
) -> None:
    admin = await make_user(roles=ADMIN)
    project = await make_project()
    with pytest.raises(BillingPeriodNotFoundError):
        await bus.execute(
            ReopenProjectBillingPeriod(
                project_id=project.id, period_start=date(2026, 9, 1), actor_id=admin.id
            )
        )


# --- ListBillingPeriods ---

# Full ISO weeks (Monday..Sunday) that sit entirely inside their calendar month.
JULY_WEEK = date(2026, 7, 6)
SEPTEMBER_WEEK = date(2026, 9, 7)


async def _send_month(
    bus: Bus,
    *,
    project_id: UUID,
    year: int,
    month: int,
    week_start: date,
    worker_id: UUID,
    admin_id: UUID,
    sent_by_id: UUID,
) -> None:
    item_id = await _normal_hours_item_id(bus, project_id)
    await _book_and_approve(
        bus,
        worker_id=worker_id,
        admin_id=admin_id,
        item_id=item_id,
        entry_date=week_start,
        week_start=week_start,
    )
    await bus.execute(
        SendProjectMonthToBilling(
            project_id=project_id, year=year, month=month, sent_by_id=sent_by_id
        )
    )


async def test_list_billing_periods_orders_newest_sent_first(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    manager = await make_user(roles=MANAGER)
    admin = await make_user(roles=ADMIN)
    worker = await make_user()
    project = await make_project(manager_id=manager.id)
    await bus.execute(AddProjectMember(project_id=project.id, user_id=worker.id))
    await _send_month(
        bus,
        project_id=project.id,
        year=2026,
        month=7,
        week_start=JULY_WEEK,
        worker_id=worker.id,
        admin_id=admin.id,
        sent_by_id=manager.id,
    )
    await _send_month(
        bus,
        project_id=project.id,
        year=2026,
        month=9,
        week_start=SEPTEMBER_WEEK,
        worker_id=worker.id,
        admin_id=admin.id,
        sent_by_id=manager.id,
    )

    page = await bus.query(ListBillingPeriods(limit=50, offset=0))

    assert [item.period_start for item in page.items] == [date(2026, 9, 1), date(2026, 7, 1)]
    assert page.total == 2


async def test_list_billing_periods_paginates(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    manager = await make_user(roles=MANAGER)
    admin = await make_user(roles=ADMIN)
    worker = await make_user()
    project = await make_project(manager_id=manager.id)
    await bus.execute(AddProjectMember(project_id=project.id, user_id=worker.id))
    await _send_month(
        bus,
        project_id=project.id,
        year=2026,
        month=7,
        week_start=JULY_WEEK,
        worker_id=worker.id,
        admin_id=admin.id,
        sent_by_id=manager.id,
    )
    await _send_month(
        bus,
        project_id=project.id,
        year=2026,
        month=9,
        week_start=SEPTEMBER_WEEK,
        worker_id=worker.id,
        admin_id=admin.id,
        sent_by_id=manager.id,
    )

    page = await bus.query(ListBillingPeriods(limit=1, offset=1))

    assert [item.period_start for item in page.items] == [date(2026, 7, 1)]
    assert page.total == 2
    assert page.limit == 1
    assert page.offset == 1


async def test_list_billing_periods_filters_by_project(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    manager = await make_user(roles=MANAGER)
    admin = await make_user(roles=ADMIN)
    worker = await make_user()
    other_worker = await make_user()
    project = await make_project(manager_id=manager.id)
    other_project = await make_project(manager_id=manager.id)
    await bus.execute(AddProjectMember(project_id=project.id, user_id=worker.id))
    await bus.execute(AddProjectMember(project_id=other_project.id, user_id=other_worker.id))
    await _send_month(
        bus,
        project_id=project.id,
        year=2026,
        month=9,
        week_start=SEPTEMBER_WEEK,
        worker_id=worker.id,
        admin_id=admin.id,
        sent_by_id=manager.id,
    )
    await _send_month(
        bus,
        project_id=other_project.id,
        year=2026,
        month=9,
        week_start=SEPTEMBER_WEEK,
        worker_id=other_worker.id,
        admin_id=admin.id,
        sent_by_id=manager.id,
    )

    page = await bus.query(ListBillingPeriods(project_id=project.id, limit=50, offset=0))

    assert [item.project_id for item in page.items] == [project.id]
    assert page.total == 1


async def test_list_billing_periods_filters_by_customer(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    make_customer: CustomerFactory,
) -> None:
    manager = await make_user(roles=MANAGER)
    admin = await make_user(roles=ADMIN)
    worker = await make_user()
    other_worker = await make_user()
    customer = await make_customer(name="Acme")
    other_customer = await make_customer(name="Globex")
    project = await make_project(customer_id=customer.id, manager_id=manager.id)
    other_project = await make_project(customer_id=other_customer.id, manager_id=manager.id)
    await bus.execute(AddProjectMember(project_id=project.id, user_id=worker.id))
    await bus.execute(AddProjectMember(project_id=other_project.id, user_id=other_worker.id))
    await _send_month(
        bus,
        project_id=project.id,
        year=2026,
        month=9,
        week_start=SEPTEMBER_WEEK,
        worker_id=worker.id,
        admin_id=admin.id,
        sent_by_id=manager.id,
    )
    await _send_month(
        bus,
        project_id=other_project.id,
        year=2026,
        month=9,
        week_start=SEPTEMBER_WEEK,
        worker_id=other_worker.id,
        admin_id=admin.id,
        sent_by_id=manager.id,
    )

    page = await bus.query(ListBillingPeriods(customer_id=customer.id, limit=50, offset=0))

    assert [item.project_id for item in page.items] == [project.id]
    assert page.items[0].customer_name == "Acme"


async def test_list_billing_periods_by_customer_with_no_projects_is_empty(
    bus: Bus, make_customer: CustomerFactory
) -> None:
    customer = await make_customer()

    page = await bus.query(ListBillingPeriods(customer_id=customer.id, limit=50, offset=0))

    assert page.items == ()
    assert page.total == 0


async def test_list_billing_periods_filters_by_month_range(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    manager = await make_user(roles=MANAGER)
    admin = await make_user(roles=ADMIN)
    worker = await make_user()
    project = await make_project(manager_id=manager.id)
    await bus.execute(AddProjectMember(project_id=project.id, user_id=worker.id))
    await _send_month(
        bus,
        project_id=project.id,
        year=2026,
        month=7,
        week_start=JULY_WEEK,
        worker_id=worker.id,
        admin_id=admin.id,
        sent_by_id=manager.id,
    )
    await _send_month(
        bus,
        project_id=project.id,
        year=2026,
        month=9,
        week_start=SEPTEMBER_WEEK,
        worker_id=worker.id,
        admin_id=admin.id,
        sent_by_id=manager.id,
    )

    page = await bus.query(
        ListBillingPeriods(
            month_from=date(2026, 8, 1), month_to=date(2026, 9, 30), limit=50, offset=0
        )
    )

    assert [item.period_start for item in page.items] == [date(2026, 9, 1)]


async def test_list_billing_periods_includes_project_and_sender_names(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    make_customer: CustomerFactory,
) -> None:
    manager = await make_user(roles=MANAGER, name="Manager One")
    admin = await make_user(roles=ADMIN)
    worker = await make_user()
    customer = await make_customer(name="Acme")
    project = await make_project(customer_id=customer.id, name="Website", manager_id=manager.id)
    await bus.execute(AddProjectMember(project_id=project.id, user_id=worker.id))
    await _send_month(
        bus,
        project_id=project.id,
        year=2026,
        month=9,
        week_start=SEPTEMBER_WEEK,
        worker_id=worker.id,
        admin_id=admin.id,
        sent_by_id=manager.id,
    )

    page = await bus.query(ListBillingPeriods(limit=50, offset=0))

    item = page.items[0]
    assert item.project_name == "Website"
    assert item.customer_name == "Acme"
    assert item.sent_by_id == manager.id
    assert item.sent_by_name == "Manager One"


# --- Expense reports feed into billing readiness and get locked ---


async def _purchasing_item_id(bus: Bus, project_id: UUID) -> UUID:
    items = await bus.query(ListProjectBillingItems(project_id=project_id))
    return next(item.id for item in items if item.preset == BillingItemPreset.PURCHASING_EXPENSES)


async def _claim_and_approve_expense(
    bus: Bus, *, worker_id: UUID, project_id: UUID, reviewer_id: UUID
) -> UUID:
    """Create, submit and approve a September expense report for ``worker_id``/``project_id``,
    returning the report id."""
    purchasing_id = await _purchasing_item_id(bus, project_id)
    report = await bus.execute(
        CreateExpenseReport(user_id=worker_id, project_id=project_id, year=2026, month=9)
    )
    await bus.execute(
        SaveExpenseReportLines(
            report_id=report.id,
            actor_id=worker_id,
            lines=(
                ExpenseLineChange(
                    line_id=None,
                    billing_item_id=purchasing_id,
                    expense_date=date(2026, 9, 5),
                    amount=Decimal("42.50"),
                    description="Taxi",
                ),
            ),
        )
    )
    await bus.execute(SubmitExpenseReport(report_id=report.id, actor_id=worker_id))
    await bus.execute(ApproveExpenseReport(report_id=report.id, reviewer_id=reviewer_id))
    return report.id


async def test_send_to_billing_is_ready_with_only_an_approved_expense_report(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    manager = await make_user(roles=MANAGER)
    worker = await make_user()
    project = await make_project(manager_id=manager.id)
    await bus.execute(AddProjectMember(project_id=project.id, user_id=worker.id))
    await _claim_and_approve_expense(
        bus, worker_id=worker.id, project_id=project.id, reviewer_id=manager.id
    )

    period = await bus.execute(
        SendProjectMonthToBilling(project_id=project.id, year=2026, month=9, sent_by_id=manager.id)
    )

    assert period.status is BillingPeriodStatus.SENT
    assert period.expenses == (
        CurrencyAmountDTO(currency=project.customer.currency, amount=Decimal("42.50")),
    )


async def test_send_to_billing_is_blocked_by_a_submitted_expense_report(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    manager = await make_user(roles=MANAGER)
    worker = await make_user()
    project = await make_project(manager_id=manager.id)
    await bus.execute(AddProjectMember(project_id=project.id, user_id=worker.id))
    purchasing_id = await _purchasing_item_id(bus, project.id)
    report = await bus.execute(
        CreateExpenseReport(user_id=worker.id, project_id=project.id, year=2026, month=9)
    )
    await bus.execute(
        SaveExpenseReportLines(
            report_id=report.id,
            actor_id=worker.id,
            lines=(
                ExpenseLineChange(
                    line_id=None,
                    billing_item_id=purchasing_id,
                    expense_date=date(2026, 9, 5),
                    amount=Decimal("10"),
                    description="Snacks",
                ),
            ),
        )
    )
    await bus.execute(SubmitExpenseReport(report_id=report.id, actor_id=worker.id))

    with pytest.raises(BillingPeriodNotReadyError) as exc_info:
        await bus.execute(
            SendProjectMonthToBilling(
                project_id=project.id, year=2026, month=9, sent_by_id=manager.id
            )
        )
    assert exc_info.value.blocking_reports == 1


async def test_send_to_billing_locks_expense_reports_and_reopen_unlocks_them(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    admin = await make_user(roles=ADMIN)
    manager = await make_user(roles=MANAGER)
    worker = await make_user()
    project = await make_project(manager_id=manager.id)
    await bus.execute(AddProjectMember(project_id=project.id, user_id=worker.id))
    report_id = await _claim_and_approve_expense(
        bus, worker_id=worker.id, project_id=project.id, reviewer_id=manager.id
    )

    await bus.execute(
        SendProjectMonthToBilling(project_id=project.id, year=2026, month=9, sent_by_id=manager.id)
    )

    locked = await bus.query(GetExpenseReport(report_id=report_id, viewer_id=worker.id))
    assert locked.is_locked is True
    assert locked.can_review is False
    # `save_lines` on this report hits its status check first (`approved` isn't editable) — the
    # lock is reachable through `return_report`, whose pre-lock statuses include `approved`.
    with pytest.raises(ExpenseReportLockedError):
        await bus.execute(
            ReturnExpenseReport(report_id=report_id, reviewer_id=manager.id, comment="Too late")
        )

    await bus.execute(
        ReopenProjectBillingPeriod(
            project_id=project.id, period_start=date(2026, 9, 1), actor_id=admin.id
        )
    )

    unlocked = await bus.query(GetExpenseReport(report_id=report_id, viewer_id=worker.id))
    assert unlocked.is_locked is False
