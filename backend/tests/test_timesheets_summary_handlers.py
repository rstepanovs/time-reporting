from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from support import CustomerFactory, ProjectFactory, UserFactory
from time_reporting.core.cqrs import Bus
from time_reporting.modules.projects.contracts import (
    AddProjectBillingItem,
    AddProjectMember,
    BillingItemPreset,
    BillingUnit,
    ListProjectBillingItems,
    UpdateProject,
)
from time_reporting.modules.timesheets.contracts import (
    GetMonthCalendar,
    GetYearHours,
    SaveTimesheetWeek,
    TimeEntryChange,
)
from time_reporting.modules.users.contracts import UserNotFoundError
from time_reporting.modules.work_calendar.contracts import AddNonWorkingDay, NonWorkingDayKind

# September 2026: the 1st is a Tuesday and the 30th is a Wednesday, so the month calendar spans
# 2026-08-31 (Mon) .. 2026-10-04 (Sun), 5 full ISO weeks.
YEAR = 2026
MONTH = 9
# A Tuesday inside the week of 2026-09-14..09-20. Sep 1..15 (excluding the two weekends in
# between) has 11 working weekdays, so `expected_hours_to_date` for September is 11 * 8 = 88.
TODAY = date(2026, 9, 15)
EXPECTED_HOURS_TO_DATE_SEPTEMBER = Decimal("88")


async def _billing_item_id(bus: Bus, project_id: UUID, preset: BillingItemPreset) -> UUID:
    items = await bus.query(ListProjectBillingItems(project_id=project_id))
    return next(item.id for item in items if item.preset == preset)


async def _book(bus: Bus, user_id: UUID, item_id: UUID, day: date, quantity: Decimal) -> None:
    week_start = day - timedelta(days=day.isoweekday() - 1)
    await bus.execute(
        SaveTimesheetWeek(
            user_id=user_id,
            week_start=week_start,
            changes=(TimeEntryChange(billing_item_id=item_id, date=day, quantity=quantity),),
        )
    )


# --- GetMonthCalendar ---


async def test_month_calendar_spans_full_iso_weeks_with_in_month_flag(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user = await make_user()
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))
    item_id = await _billing_item_id(bus, project.id, BillingItemPreset.NORMAL_HOURS)

    # One entry outside the month (in the first week) and one inside it.
    await _book(bus, user.id, item_id, date(2026, 8, 31), Decimal("8"))
    await _book(bus, user.id, item_id, date(2026, 9, 1), Decimal("6"))

    calendar = await bus.query(
        GetMonthCalendar(user_id=user.id, year=YEAR, month=MONTH, today=TODAY)
    )

    assert len(calendar.weeks) == 5
    assert all(len(week.days) == 7 for week in calendar.weeks)
    assert calendar.weeks[0].week_start == date(2026, 8, 31)
    assert calendar.weeks[-1].days[-1].calendar_day.day == date(2026, 10, 4)

    first_day, second_day = calendar.weeks[0].days[0], calendar.weeks[0].days[1]
    assert first_day.calendar_day.day == date(2026, 8, 31)
    assert first_day.in_month is False
    assert first_day.hours == Decimal("8.00")
    assert second_day.calendar_day.day == date(2026, 9, 1)
    assert second_day.in_month is True
    assert second_day.hours == Decimal("6.00")

    # The week total includes the out-of-month day; the month total does not.
    assert calendar.weeks[0].hours == Decimal("14.00")
    assert calendar.hours == Decimal("6.00")


async def test_month_calendar_expected_hours_skip_weekends_and_non_working_days(
    bus: Bus, make_user: UserFactory
) -> None:
    user = await make_user()
    await bus.execute(
        AddNonWorkingDay(
            day=date(2026, 9, 16), name="Company day off", kind=NonWorkingDayKind.COMPANY_DAY_OFF
        )
    )

    calendar = await bus.query(
        GetMonthCalendar(user_id=user.id, year=YEAR, month=MONTH, today=TODAY)
    )
    days_by_date = {d.calendar_day.day: d for week in calendar.weeks for d in week.days}

    saturday = days_by_date[date(2026, 9, 5)]
    assert saturday.is_working_day is False
    assert saturday.expected_hours == Decimal(0)

    company_day_off = days_by_date[date(2026, 9, 16)]
    assert company_day_off.is_working_day is False
    assert company_day_off.expected_hours == Decimal(0)

    workday = days_by_date[date(2026, 9, 17)]
    assert workday.is_working_day is True
    assert workday.expected_hours == Decimal("8")


async def test_month_calendar_expected_hours_to_date_uses_today(
    bus: Bus, make_user: UserFactory
) -> None:
    user = await make_user()

    calendar = await bus.query(
        GetMonthCalendar(user_id=user.id, year=YEAR, month=MONTH, today=TODAY)
    )

    assert calendar.expected_hours_to_date == EXPECTED_HOURS_TO_DATE_SEPTEMBER
    assert calendar.expected_hours_to_date < calendar.expected_hours


async def test_month_calendar_ignores_non_hour_entries(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user = await make_user()
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))
    per_diem_id = await _billing_item_id(bus, project.id, BillingItemPreset.PER_DIEM)
    await _book(bus, user.id, per_diem_id, date(2026, 9, 2), Decimal("1"))

    calendar = await bus.query(
        GetMonthCalendar(user_id=user.id, year=YEAR, month=MONTH, today=TODAY)
    )
    day = next(
        d for week in calendar.weeks for d in week.days if d.calendar_day.day == date(2026, 9, 2)
    )
    assert day.hours == Decimal(0)
    assert calendar.hours == Decimal(0)


async def test_month_calendar_for_unknown_user_raises(bus: Bus) -> None:
    with pytest.raises(UserNotFoundError):
        await bus.query(GetMonthCalendar(user_id=uuid4(), year=YEAR, month=MONTH, today=TODAY))


# --- GetYearHours ---


async def test_year_hours_categorizes_by_preset(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user = await make_user()
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))
    normal_id = await _billing_item_id(bus, project.id, BillingItemPreset.NORMAL_HOURS)
    overtime_id = await _billing_item_id(bus, project.id, BillingItemPreset.OVERTIME_HOURS)
    travel_id = await _billing_item_id(bus, project.id, BillingItemPreset.TRAVEL_TIME)
    per_diem_id = await _billing_item_id(bus, project.id, BillingItemPreset.PER_DIEM)
    custom = await bus.execute(
        AddProjectBillingItem(project_id=project.id, name="Consulting", unit=BillingUnit.HOUR)
    )

    await _book(bus, user.id, normal_id, date(2026, 9, 1), Decimal("8"))
    await _book(bus, user.id, overtime_id, date(2026, 9, 1), Decimal("2"))
    await _book(bus, user.id, travel_id, date(2026, 9, 2), Decimal("3"))
    await _book(bus, user.id, custom.id, date(2026, 9, 2), Decimal("4"))
    await _book(bus, user.id, per_diem_id, date(2026, 9, 2), Decimal("1"))  # ignored: `day` unit

    year = await bus.query(GetYearHours(user_id=user.id, year=YEAR, today=TODAY))
    september = next(m for m in year.months if m.month == MONTH)

    assert september.totals.normal_hours == Decimal("8.00")
    assert september.totals.overtime_hours == Decimal("2.00")
    assert september.totals.travel_hours == Decimal("3.00")
    assert september.totals.other_hours == Decimal("4.00")
    assert september.totals.total_hours == Decimal("17.00")


async def test_year_hours_per_project_breakdown_only_lists_projects_with_hours(
    bus: Bus,
    make_project: ProjectFactory,
    make_customer: CustomerFactory,
    make_user: UserFactory,
) -> None:
    user = await make_user()
    customer_a = await make_customer(name="Alpha")
    customer_b = await make_customer(name="Beta")
    project_a = await make_project(customer_id=customer_a.id, name="Portal")
    project_b = await make_project(customer_id=customer_b.id, name="ERP")
    project_c = await make_project(customer_id=customer_a.id, name="No hours booked")
    for project in (project_a, project_b, project_c):
        await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))
    item_a = await _billing_item_id(bus, project_a.id, BillingItemPreset.NORMAL_HOURS)
    item_b = await _billing_item_id(bus, project_b.id, BillingItemPreset.NORMAL_HOURS)

    await _book(bus, user.id, item_a, date(2026, 9, 1), Decimal("5"))
    await _book(bus, user.id, item_b, date(2026, 9, 1), Decimal("3"))

    year = await bus.query(GetYearHours(user_id=user.id, year=YEAR, today=TODAY))
    september = next(m for m in year.months if m.month == MONTH)

    # Sorted by customer name then project name; the project with no hours is left out.
    assert [p.project.id for p in september.projects] == [project_a.id, project_b.id]
    assert september.projects[0].totals.normal_hours == Decimal("5.00")
    assert september.projects[1].totals.normal_hours == Decimal("3.00")


async def test_year_hours_lists_january_through_current_month(
    bus: Bus, make_user: UserFactory
) -> None:
    user = await make_user()

    year = await bus.query(GetYearHours(user_id=user.id, year=YEAR, today=TODAY))

    assert [m.month for m in year.months] == list(range(MONTH, 0, -1))
    assert all(m.totals.total_hours == Decimal(0) for m in year.months)
    assert year.months[0].is_current is True
    assert all(not m.is_current for m in year.months[1:])


async def test_year_hours_for_past_year_lists_all_twelve_months(
    bus: Bus, make_user: UserFactory
) -> None:
    user = await make_user()

    year = await bus.query(GetYearHours(user_id=user.id, year=YEAR - 1, today=TODAY))

    assert [m.month for m in year.months] == list(range(12, 0, -1))
    assert all(not m.is_current for m in year.months)
    assert all(m.expected_hours_to_date == m.expected_hours for m in year.months)


async def test_year_hours_for_future_year_is_empty(bus: Bus, make_user: UserFactory) -> None:
    user = await make_user()

    year = await bus.query(GetYearHours(user_id=user.id, year=YEAR + 1, today=TODAY))

    assert year.months == ()
    assert year.totals.total_hours == Decimal(0)


async def test_year_hours_expected_hours_to_date_only_for_the_current_month(
    bus: Bus, make_user: UserFactory
) -> None:
    user = await make_user()

    year = await bus.query(GetYearHours(user_id=user.id, year=YEAR, today=TODAY))

    current = next(m for m in year.months if m.is_current)
    assert current.expected_hours_to_date == EXPECTED_HOURS_TO_DATE_SEPTEMBER
    assert current.expected_hours_to_date < current.expected_hours

    past_month = next(m for m in year.months if m.month == MONTH - 1)
    assert past_month.expected_hours_to_date == past_month.expected_hours


async def test_year_hours_includes_archived_project(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user = await make_user()
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))
    item_id = await _billing_item_id(bus, project.id, BillingItemPreset.NORMAL_HOURS)
    await _book(bus, user.id, item_id, date(2026, 9, 1), Decimal("4"))
    await bus.execute(UpdateProject(project_id=project.id, is_active=False))

    year = await bus.query(GetYearHours(user_id=user.id, year=YEAR, today=TODAY))
    september = next(m for m in year.months if m.month == MONTH)

    assert september.totals.normal_hours == Decimal("4.00")
    assert [p.project.id for p in september.projects] == [project.id]


async def test_year_hours_totals_sum_across_months(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user = await make_user()
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))
    item_id = await _billing_item_id(bus, project.id, BillingItemPreset.NORMAL_HOURS)
    await _book(bus, user.id, item_id, date(2026, 8, 3), Decimal("6"))
    await _book(bus, user.id, item_id, date(2026, 9, 1), Decimal("4"))

    year = await bus.query(GetYearHours(user_id=user.id, year=YEAR, today=TODAY))

    assert year.totals.normal_hours == Decimal("10.00")
    assert year.totals.total_hours == Decimal("10.00")


async def test_year_hours_for_unknown_user_raises(bus: Bus) -> None:
    with pytest.raises(UserNotFoundError):
        await bus.query(GetYearHours(user_id=uuid4(), year=YEAR, today=TODAY))
