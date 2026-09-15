from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from support import ProjectFactory, UserFactory
from time_reporting.core.cqrs import Bus
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
    GetTimesheetWeek,
    NotProjectManagerError,
    ReopenProjectBillingPeriod,
    ReturnTimesheetWeek,
    RowCommentChange,
    SaveTimesheetWeek,
    SendProjectMonthToBilling,
    SubmitTimesheetWeek,
    TimeEntryChange,
    TimesheetProjectNotFoundError,
)
from time_reporting.modules.users.contracts import UserNotFoundError, UserRole

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
    manager = await make_user(role=UserRole.PROJECT_MANAGER)
    admin = await make_user(role=UserRole.ADMIN)
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


async def test_send_is_allowed_before_the_month_ends(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    manager = await make_user(role=UserRole.PROJECT_MANAGER)
    admin = await make_user(role=UserRole.ADMIN)
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
    manager = await make_user(role=UserRole.PROJECT_MANAGER)
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
    manager = await make_user(role=UserRole.PROJECT_MANAGER)
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
    manager = await make_user(role=UserRole.PROJECT_MANAGER)
    admin = await make_user(role=UserRole.ADMIN)
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


async def test_send_by_a_project_manager_who_is_not_this_projects_manager_is_rejected(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    manager = await make_user(role=UserRole.PROJECT_MANAGER)
    other_manager = await make_user(role=UserRole.PROJECT_MANAGER)
    project = await make_project(manager_id=manager.id)

    with pytest.raises(NotProjectManagerError):
        await bus.execute(
            SendProjectMonthToBilling(
                project_id=project.id, year=2026, month=9, sent_by_id=other_manager.id
            )
        )


async def test_admin_can_send_any_project(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    manager = await make_user(role=UserRole.PROJECT_MANAGER)
    admin = await make_user(role=UserRole.ADMIN)
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
        SendProjectMonthToBilling(project_id=project.id, year=2026, month=9, sent_by_id=admin.id)
    )
    assert period.status is BillingPeriodStatus.SENT


async def test_send_for_unknown_project_raises(bus: Bus, make_user: UserFactory) -> None:
    admin = await make_user(role=UserRole.ADMIN)
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
    manager = await make_user(role=UserRole.PROJECT_MANAGER)
    admin = await make_user(role=UserRole.ADMIN)
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
    manager = await make_user(role=UserRole.PROJECT_MANAGER)
    admin = await make_user(role=UserRole.ADMIN)
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
    manager = await make_user(role=UserRole.PROJECT_MANAGER)
    admin = await make_user(role=UserRole.ADMIN)
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
    manager = await make_user(role=UserRole.PROJECT_MANAGER)
    admin = await make_user(role=UserRole.ADMIN)
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
    manager = await make_user(role=UserRole.PROJECT_MANAGER)
    admin = await make_user(role=UserRole.ADMIN)
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
        ReopenProjectBillingPeriod(project_id=project.id, period_start=date(2026, 9, 1))
    )

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


async def test_reopen_unknown_period_raises(bus: Bus, make_project: ProjectFactory) -> None:
    project = await make_project()
    with pytest.raises(BillingPeriodNotFoundError):
        await bus.execute(
            ReopenProjectBillingPeriod(project_id=project.id, period_start=date(2026, 9, 1))
        )
