from datetime import date
from decimal import Decimal
from uuid import UUID

from support import ProjectFactory, UserFactory
from time_reporting.core.cqrs import Bus
from time_reporting.modules.projects.contracts import (
    AddProjectMember,
    BillingItemPreset,
    ListProjectBillingItems,
    RemoveProjectMember,
)
from time_reporting.modules.timesheets.contracts import (
    ApproveTimesheetWeek,
    BillingPeriodStatus,
    GetTeamMonthOverview,
    SaveTimesheetWeek,
    SendProjectMonthToBilling,
    SubmitTimesheetWeek,
    TeamMemberWarning,
    TimeEntryChange,
)
from time_reporting.modules.users.contracts import UserRole

# September 2026's five ISO weeks (its first/last week spill outside the month): 2026-08-31 is the
# Monday of the week holding Sep 1, so it also holds Aug 31 — a straddling week used below.
SEPTEMBER_WEEKS = [
    date(2026, 8, 31),
    date(2026, 9, 7),
    date(2026, 9, 14),
    date(2026, 9, 21),
    date(2026, 9, 28),
]
STRADDLING_WEEK = SEPTEMBER_WEEKS[0]
IN_AUGUST_DAY = date(2026, 8, 31)
IN_SEPTEMBER_DAY = date(2026, 9, 2)


async def _normal_hours_item_id(bus: Bus, project_id: UUID) -> UUID:
    items = await bus.query(ListProjectBillingItems(project_id=project_id))
    return next(item.id for item in items if item.preset == BillingItemPreset.NORMAL_HOURS)


async def test_overview_scope_filters_by_manager(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    manager_a = await make_user(role=UserRole.PROJECT_MANAGER)
    manager_b = await make_user(role=UserRole.PROJECT_MANAGER)
    project_a = await make_project(name="A", manager_id=manager_a.id)
    project_b = await make_project(name="B", manager_id=manager_b.id)

    mine = await bus.query(
        GetTeamMonthOverview(manager_id=manager_a.id, year=2026, month=9, today=date(2026, 9, 15))
    )
    assert {p.project.id for p in mine.projects} == {project_a.id}

    everyone = await bus.query(
        GetTeamMonthOverview(manager_id=None, year=2026, month=9, today=date(2026, 9, 15))
    )
    ids = {p.project.id for p in everyone.projects}
    assert {project_a.id, project_b.id} <= ids


async def test_project_hours_are_clipped_to_the_query_month_for_a_straddling_week(
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
            week_start=STRADDLING_WEEK,
            changes=(
                TimeEntryChange(billing_item_id=item_id, date=IN_AUGUST_DAY, quantity=Decimal("3")),
                TimeEntryChange(
                    billing_item_id=item_id, date=IN_SEPTEMBER_DAY, quantity=Decimal("5")
                ),
            ),
        )
    )

    august = await bus.query(
        GetTeamMonthOverview(manager_id=manager.id, year=2026, month=8, today=date(2026, 8, 31))
    )
    august_member = august.projects[0].members[0]
    august_week = next(w for w in august_member.weeks if w.week_start == STRADDLING_WEEK)
    assert august_week.project_hours == Decimal("3")
    assert august_week.total_hours == Decimal("8")  # whole week, both months

    september = await bus.query(
        GetTeamMonthOverview(manager_id=manager.id, year=2026, month=9, today=date(2026, 9, 15))
    )
    september_member = september.projects[0].members[0]
    september_week = next(w for w in september_member.weeks if w.week_start == STRADDLING_WEEK)
    assert september_week.project_hours == Decimal("5")
    assert september_week.total_hours == Decimal("8")


async def test_status_counts_reflect_current_members_across_all_weeks_in_scope(
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
            week_start=SEPTEMBER_WEEKS[1],
            changes=(
                TimeEntryChange(
                    billing_item_id=item_id, date=SEPTEMBER_WEEKS[1], quantity=Decimal("4")
                ),
            ),
        )
    )
    await bus.execute(SubmitTimesheetWeek(user_id=worker.id, week_start=SEPTEMBER_WEEKS[1]))

    overview = await bus.query(
        GetTeamMonthOverview(manager_id=manager.id, year=2026, month=9, today=date(2026, 9, 15))
    )

    assert overview.counts.awaiting_approval == 1
    assert overview.counts.not_submitted == len(SEPTEMBER_WEEKS) - 1
    assert overview.counts.approved == 0
    assert overview.counts.returned == 0


async def test_warning_flags_a_member_with_no_entries_on_the_project(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    manager = await make_user(role=UserRole.PROJECT_MANAGER)
    worker = await make_user()
    project = await make_project(manager_id=manager.id)
    await bus.execute(AddProjectMember(project_id=project.id, user_id=worker.id))

    overview = await bus.query(
        GetTeamMonthOverview(manager_id=manager.id, year=2026, month=9, today=date(2026, 9, 15))
    )

    member = overview.projects[0].members[0]
    assert member.project_hours == Decimal("0")
    assert member.warning is TeamMemberWarning.NO_ENTRIES


async def test_warning_flags_a_member_under_expected_hours(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    manager = await make_user(role=UserRole.PROJECT_MANAGER)
    worker = await make_user()
    project = await make_project(manager_id=manager.id)
    await bus.execute(AddProjectMember(project_id=project.id, user_id=worker.id))
    item_id = await _normal_hours_item_id(bus, project.id)
    # A single hour booked, versus a full month's worth of working days expected by "today".
    await bus.execute(
        SaveTimesheetWeek(
            user_id=worker.id,
            week_start=SEPTEMBER_WEEKS[1],
            changes=(
                TimeEntryChange(
                    billing_item_id=item_id, date=SEPTEMBER_WEEKS[1], quantity=Decimal("1")
                ),
            ),
        )
    )

    overview = await bus.query(
        GetTeamMonthOverview(manager_id=manager.id, year=2026, month=9, today=date(2026, 9, 30))
    )

    member = overview.projects[0].members[0]
    assert member.project_hours == Decimal("1")
    assert member.warning is TeamMemberWarning.UNDER_EXPECTED_HOURS


async def test_removed_member_is_still_listed_with_is_member_false(
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
            week_start=SEPTEMBER_WEEKS[1],
            changes=(
                TimeEntryChange(
                    billing_item_id=item_id, date=SEPTEMBER_WEEKS[1], quantity=Decimal("4")
                ),
            ),
        )
    )
    await bus.execute(RemoveProjectMember(project_id=project.id, user_id=worker.id))

    overview = await bus.query(
        GetTeamMonthOverview(manager_id=manager.id, year=2026, month=9, today=date(2026, 9, 15))
    )

    member = overview.projects[0].members[0]
    assert member.user.id == worker.id
    assert member.is_member is False
    assert member.project_hours == Decimal("4")


async def test_billing_readiness_not_ready_with_no_entries(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    manager = await make_user(role=UserRole.PROJECT_MANAGER)
    await make_project(manager_id=manager.id)

    overview = await bus.query(
        GetTeamMonthOverview(manager_id=manager.id, year=2026, month=9, today=date(2026, 9, 15))
    )

    billing = overview.projects[0].billing
    assert billing.status is BillingPeriodStatus.NOT_READY
    assert billing.weeks_in_scope == 0
    assert billing.blocking_weeks == 0


async def test_billing_readiness_blocked_by_an_unapproved_week(
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
            week_start=SEPTEMBER_WEEKS[1],
            changes=(
                TimeEntryChange(
                    billing_item_id=item_id, date=SEPTEMBER_WEEKS[1], quantity=Decimal("4")
                ),
            ),
        )
    )

    overview = await bus.query(
        GetTeamMonthOverview(manager_id=manager.id, year=2026, month=9, today=date(2026, 9, 15))
    )

    billing = overview.projects[0].billing
    assert billing.status is BillingPeriodStatus.NOT_READY
    assert billing.weeks_in_scope == 1
    assert billing.blocking_weeks == 1


async def test_billing_readiness_ready_once_every_week_in_scope_is_approved(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    manager = await make_user(role=UserRole.PROJECT_MANAGER)
    admin = await make_user(role=UserRole.ADMIN)
    worker = await make_user()
    project = await make_project(manager_id=manager.id)
    await bus.execute(AddProjectMember(project_id=project.id, user_id=worker.id))
    item_id = await _normal_hours_item_id(bus, project.id)
    await bus.execute(
        SaveTimesheetWeek(
            user_id=worker.id,
            week_start=SEPTEMBER_WEEKS[1],
            changes=(
                TimeEntryChange(
                    billing_item_id=item_id, date=SEPTEMBER_WEEKS[1], quantity=Decimal("4")
                ),
            ),
        )
    )
    await bus.execute(SubmitTimesheetWeek(user_id=worker.id, week_start=SEPTEMBER_WEEKS[1]))
    await bus.execute(
        ApproveTimesheetWeek(user_id=worker.id, week_start=SEPTEMBER_WEEKS[1], reviewer_id=admin.id)
    )

    # Sent on any day, including well before the month ends.
    overview = await bus.query(
        GetTeamMonthOverview(manager_id=manager.id, year=2026, month=9, today=date(2026, 9, 16))
    )

    billing = overview.projects[0].billing
    assert billing.status is BillingPeriodStatus.READY
    assert billing.weeks_in_scope == 1
    assert billing.blocking_weeks == 0
    assert billing.hours.normal_hours == Decimal("4")


async def test_billing_status_is_sent_once_a_period_has_been_sent(
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
            week_start=SEPTEMBER_WEEKS[1],
            changes=(
                TimeEntryChange(
                    billing_item_id=item_id, date=SEPTEMBER_WEEKS[1], quantity=Decimal("4")
                ),
            ),
        )
    )
    await bus.execute(SubmitTimesheetWeek(user_id=worker.id, week_start=SEPTEMBER_WEEKS[1]))
    await bus.execute(
        ApproveTimesheetWeek(
            user_id=worker.id, week_start=SEPTEMBER_WEEKS[1], reviewer_id=manager.id
        )
    )
    await bus.execute(
        SendProjectMonthToBilling(project_id=project.id, year=2026, month=9, sent_by_id=manager.id)
    )

    overview = await bus.query(
        GetTeamMonthOverview(manager_id=manager.id, year=2026, month=9, today=date(2026, 9, 16))
    )

    billing = overview.projects[0].billing
    assert billing.status is BillingPeriodStatus.SENT
    assert billing.sent_by is not None
    assert billing.sent_by.id == manager.id
    assert billing.sent_at is not None
