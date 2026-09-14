from datetime import date
from uuid import uuid4

import pytest

from time_reporting.core.config import get_settings
from time_reporting.core.cqrs import Bus
from time_reporting.modules.work_calendar.contracts import (
    AddNonWorkingDay,
    CalendarRangeTooWideError,
    DeleteNonWorkingDay,
    GetCalendarDays,
    HolidayCountryNotSupportedError,
    ImportPublicHolidays,
    ListNonWorkingDays,
    NonWorkingDayAlreadyExistsError,
    NonWorkingDayKind,
    NonWorkingDayNotFoundError,
    UpdateNonWorkingDay,
)


async def test_add_and_update_non_working_day(bus: Bus) -> None:
    added = await bus.execute(
        AddNonWorkingDay(
            day=date(2026, 12, 24), name="Christmas Eve", kind=NonWorkingDayKind.COMPANY_DAY_OFF
        )
    )

    assert added.day == date(2026, 12, 24)
    assert added.kind == NonWorkingDayKind.COMPANY_DAY_OFF

    updated = await bus.execute(
        UpdateNonWorkingDay(non_working_day_id=added.id, name="Christmas Eve (half day)")
    )

    assert updated.name == "Christmas Eve (half day)"
    assert updated.day == added.day
    assert updated.kind == added.kind


async def test_duplicate_date_is_rejected_and_session_stays_usable(bus: Bus) -> None:
    existing = await bus.execute(
        AddNonWorkingDay(
            day=date(2026, 1, 1), name="New Year", kind=NonWorkingDayKind.PUBLIC_HOLIDAY
        )
    )

    with pytest.raises(NonWorkingDayAlreadyExistsError):
        await bus.execute(
            AddNonWorkingDay(
                day=date(2026, 1, 1), name="Duplicate", kind=NonWorkingDayKind.PUBLIC_HOLIDAY
            )
        )

    days = await bus.query(ListNonWorkingDays(year=2026))
    assert [day.id for day in days] == [existing.id]


async def test_update_to_taken_date_is_rejected(bus: Bus) -> None:
    await bus.execute(
        AddNonWorkingDay(
            day=date(2026, 1, 1), name="New Year", kind=NonWorkingDayKind.PUBLIC_HOLIDAY
        )
    )
    other = await bus.execute(
        AddNonWorkingDay(day=date(2026, 1, 2), name="Bridge", kind=NonWorkingDayKind.BRIDGE_DAY)
    )

    with pytest.raises(NonWorkingDayAlreadyExistsError):
        await bus.execute(UpdateNonWorkingDay(non_working_day_id=other.id, day=date(2026, 1, 1)))


async def test_unknown_non_working_day_raises(bus: Bus) -> None:
    with pytest.raises(NonWorkingDayNotFoundError):
        await bus.execute(UpdateNonWorkingDay(non_working_day_id=uuid4(), name="Nobody"))

    with pytest.raises(NonWorkingDayNotFoundError):
        await bus.execute(DeleteNonWorkingDay(non_working_day_id=uuid4()))


async def test_delete_non_working_day_removes_the_row(bus: Bus) -> None:
    added = await bus.execute(
        AddNonWorkingDay(
            day=date(2026, 5, 1), name="Labor Day", kind=NonWorkingDayKind.PUBLIC_HOLIDAY
        )
    )

    await bus.execute(DeleteNonWorkingDay(non_working_day_id=added.id))

    assert await bus.query(ListNonWorkingDays(year=2026)) == ()


async def test_list_non_working_days_filters_by_year(bus: Bus) -> None:
    in_2026 = await bus.execute(
        AddNonWorkingDay(
            day=date(2026, 1, 1), name="New Year", kind=NonWorkingDayKind.PUBLIC_HOLIDAY
        )
    )
    await bus.execute(
        AddNonWorkingDay(
            day=date(2027, 1, 1), name="New Year", kind=NonWorkingDayKind.PUBLIC_HOLIDAY
        )
    )

    days = await bus.query(ListNonWorkingDays(year=2026))

    assert [day.id for day in days] == [in_2026.id]


async def test_get_calendar_days_flags_weekends_and_non_working_days(bus: Bus) -> None:
    # 2026-09-14 is a Monday; the range spans one full week.
    holiday = await bus.execute(
        AddNonWorkingDay(
            day=date(2026, 9, 16), name="Custom Holiday", kind=NonWorkingDayKind.COMPANY_DAY_OFF
        )
    )

    days = await bus.query(GetCalendarDays(date_from=date(2026, 9, 14), date_to=date(2026, 9, 20)))

    by_date = {day.day: day for day in days}
    assert len(days) == 7
    assert by_date[date(2026, 9, 14)].is_weekend is False
    assert by_date[date(2026, 9, 19)].is_weekend is True  # Saturday
    assert by_date[date(2026, 9, 20)].is_weekend is True  # Sunday
    holiday_on_day = by_date[date(2026, 9, 16)].non_working_day
    assert holiday_on_day is not None
    assert holiday_on_day.id == holiday.id
    assert by_date[date(2026, 9, 14)].non_working_day is None


async def test_get_calendar_days_rejects_too_wide_a_range(bus: Bus) -> None:
    with pytest.raises(CalendarRangeTooWideError):
        await bus.query(GetCalendarDays(date_from=date(2020, 1, 1), date_to=date(2026, 1, 1)))


async def test_get_calendar_days_rejects_reversed_range(bus: Bus) -> None:
    with pytest.raises(CalendarRangeTooWideError):
        await bus.query(GetCalendarDays(date_from=date(2026, 1, 2), date_to=date(2026, 1, 1)))


async def test_import_public_holidays_is_idempotent_and_skips_taken_dates(bus: Bus) -> None:
    # New Year's Day would normally be imported; pre-seed it manually under a different kind so
    # the import must skip it rather than overwrite it.
    manual = await bus.execute(
        AddNonWorkingDay(
            day=date(2026, 1, 1), name="Manual New Year", kind=NonWorkingDayKind.COMPANY_DAY_OFF
        )
    )

    first_run = await bus.execute(ImportPublicHolidays(year=2026))
    days_after_first = await bus.query(ListNonWorkingDays(year=2026))

    second_run = await bus.execute(ImportPublicHolidays(year=2026))
    days_after_second = await bus.query(ListNonWorkingDays(year=2026))

    assert first_run > 0
    assert second_run == 0
    assert len(days_after_first) == len(days_after_second)
    new_year = next(day for day in days_after_first if day.day == date(2026, 1, 1))
    assert new_year.id == manual.id
    assert new_year.kind == NonWorkingDayKind.COMPANY_DAY_OFF


async def test_import_public_holidays_rejects_unsupported_country(
    bus: Bus, monkeypatch: pytest.MonkeyPatch
) -> None:
    from time_reporting.modules.work_calendar import service as work_calendar_service

    unsupported = get_settings().model_copy(update={"holiday_country": "ZZ"})
    monkeypatch.setattr(work_calendar_service, "get_settings", lambda: unsupported)

    with pytest.raises(HolidayCountryNotSupportedError):
        await bus.execute(ImportPublicHolidays(year=2026))
