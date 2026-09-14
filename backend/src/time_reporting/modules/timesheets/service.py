"""Timesheet domain logic.

Changes are flushed through the repository; the bus commits. Reads projects, users and calendar
data only through their modules' ``contracts.py`` messages, dispatched on the shared ``Bus``.
"""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from time_reporting.core.cqrs import Bus
from time_reporting.modules.projects.contracts import (
    BillingUnit,
    GetProjectBillingItemsByIds,
    GetProjectsByIds,
    ListMemberProjectsWithBillingItems,
    ProjectBillingItemDTO,
    ProjectDTO,
)
from time_reporting.modules.timesheets.contracts import (
    MAX_DAILY_HOURS,
    MAX_DAY_ENTRY_QUANTITY,
    MAX_HOUR_ENTRY_QUANTITY,
    DailyHoursExceededError,
    DuplicateChangeError,
    EntryDateOutsideWeekError,
    QuantityOutOfRangeError,
    SaveTimesheetWeek,
    TimeEntryChange,
    TimeEntryDTO,
    TimesheetBillingItemNotFoundError,
    TimesheetRowClosedError,
    TimesheetRowDTO,
    TimesheetWeekDTO,
    WeekStartNotMondayError,
)
from time_reporting.modules.timesheets.models import TimeEntry
from time_reporting.modules.timesheets.repository import TimeEntryRepository
from time_reporting.modules.users.contracts import GetUserById, UserNotFoundError
from time_reporting.modules.work_calendar.contracts import GetCalendarDays

_WEEK_LENGTH_DAYS = 7


class TimesheetService:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._entries = TimeEntryRepository(bus.session)

    async def get_week(
        self, *, user_id: UUID, week_start: date, viewer_id: UUID
    ) -> TimesheetWeekDTO:
        _ensure_monday(week_start)
        user = await self._bus.query(GetUserById(user_id=user_id))
        if user is None:
            raise UserNotFoundError(user_id)
        week_end = _week_end(week_start)

        entries = await self._entries.list_for_user_in_range(user_id, week_start, week_end)
        billing_item_ids = frozenset(entry.billing_item_id for entry in entries)
        items_by_id = {
            item.id: item
            for item in await self._bus.query(
                GetProjectBillingItemsByIds(billing_item_ids=billing_item_ids)
            )
        }
        project_ids = frozenset(item.project_id for item in items_by_id.values())
        projects_by_id = {
            project.id: project
            for project in await self._bus.query(GetProjectsByIds(project_ids=project_ids))
        }
        open_item_ids = frozenset(
            item.id
            for option in await self._bus.query(ListMemberProjectsWithBillingItems(user_id=user_id))
            for item in option.billing_items
        )

        entries_by_item: dict[UUID, list[TimeEntryDTO]] = defaultdict(list)
        for entry in entries:
            entries_by_item[entry.billing_item_id].append(
                TimeEntryDTO(date=entry.entry_date, quantity=entry.quantity, note=entry.note)
            )

        rows = sorted(
            (
                TimesheetRowDTO(
                    project=projects_by_id[billing_item.project_id],
                    billing_item=billing_item,
                    is_open=item_id in open_item_ids,
                    entries=tuple(entries_by_item[item_id]),
                )
                for item_id, billing_item in items_by_id.items()
            ),
            key=lambda row: (row.project.name, row.billing_item.position),
        )

        days = await self._bus.query(GetCalendarDays(date_from=week_start, date_to=week_end))
        return TimesheetWeekDTO(
            user=user,
            week_start=week_start,
            can_edit=viewer_id == user_id,
            days=days,
            rows=tuple(rows),
        )

    async def save_week(self, command: SaveTimesheetWeek) -> TimesheetWeekDTO:
        week_start = command.week_start
        _ensure_monday(week_start)
        if await self._bus.query(GetUserById(user_id=command.user_id)) is None:
            raise UserNotFoundError(command.user_id)
        week_end = _week_end(week_start)

        seen_cells: set[tuple[UUID, date]] = set()
        for change in command.changes:
            cell = (change.billing_item_id, change.date)
            if cell in seen_cells:
                raise DuplicateChangeError(*cell)
            seen_cells.add(cell)
            if not week_start <= change.date <= week_end:
                raise EntryDateOutsideWeekError(change.date, week_start)

        open_items, projects_by_item = await self._open_items(command.user_id)
        await self._ensure_changes_are_valid(command.changes, open_items)
        await self._apply_changes(command.user_id, command.changes, open_items, projects_by_item)
        await self._ensure_daily_hours_in_range(command.user_id, command.changes)

        return await self.get_week(
            user_id=command.user_id, week_start=week_start, viewer_id=command.user_id
        )

    async def _open_items(
        self, user_id: UUID
    ) -> tuple[dict[UUID, ProjectBillingItemDTO], dict[UUID, ProjectDTO]]:
        options = await self._bus.query(ListMemberProjectsWithBillingItems(user_id=user_id))
        open_items = {item.id: item for option in options for item in option.billing_items}
        projects_by_item = {
            item.id: option.project for option in options for item in option.billing_items
        }
        return open_items, projects_by_item

    async def _ensure_changes_are_valid(
        self,
        changes: tuple[TimeEntryChange, ...],
        open_items: dict[UUID, ProjectBillingItemDTO],
    ) -> None:
        unknown_ids = frozenset(c.billing_item_id for c in changes) - open_items.keys()
        existing_unknown_ids: frozenset[UUID] = frozenset()
        if unknown_ids:
            existing = await self._bus.query(
                GetProjectBillingItemsByIds(billing_item_ids=unknown_ids)
            )
            existing_unknown_ids = frozenset(item.id for item in existing)

        for change in changes:
            billing_item = open_items.get(change.billing_item_id)
            if billing_item is None:
                if change.billing_item_id not in existing_unknown_ids:
                    raise TimesheetBillingItemNotFoundError(change.billing_item_id)
                raise TimesheetRowClosedError(change.billing_item_id)
            if change.quantity is not None:
                _ensure_quantity_in_range(billing_item.unit, change, change.quantity)

    async def _apply_changes(
        self,
        user_id: UUID,
        changes: tuple[TimeEntryChange, ...],
        open_items: dict[UUID, ProjectBillingItemDTO],
        projects_by_item: dict[UUID, ProjectDTO],
    ) -> None:
        for change in changes:
            existing_entry = await self._entries.get(
                user_id=user_id, billing_item_id=change.billing_item_id, entry_date=change.date
            )
            if change.quantity is None:
                if existing_entry is not None:
                    await self._entries.delete(existing_entry)
                continue
            if existing_entry is not None:
                existing_entry.quantity = change.quantity
                existing_entry.note = change.note
                await self._entries.save(existing_entry)
            else:
                billing_item = open_items[change.billing_item_id]
                await self._entries.save(
                    TimeEntry(
                        user_id=user_id,
                        project_id=projects_by_item[change.billing_item_id].id,
                        billing_item_id=change.billing_item_id,
                        entry_date=change.date,
                        quantity=change.quantity,
                        unit=billing_item.unit,
                        note=change.note,
                    )
                )

    async def _ensure_daily_hours_in_range(
        self, user_id: UUID, changes: tuple[TimeEntryChange, ...]
    ) -> None:
        touched_dates = frozenset(change.date for change in changes)
        if not touched_dates:
            return
        totals = await self._entries.sum_quantity_by_date(user_id, touched_dates, BillingUnit.HOUR)
        for entry_date, total in totals.items():
            if total > MAX_DAILY_HOURS:
                raise DailyHoursExceededError(entry_date, total)


def _ensure_monday(week_start: date) -> None:
    if week_start.isoweekday() != 1:
        raise WeekStartNotMondayError(week_start)


def _week_end(week_start: date) -> date:
    return week_start + timedelta(days=_WEEK_LENGTH_DAYS - 1)


def _ensure_quantity_in_range(
    unit: BillingUnit, change: TimeEntryChange, quantity: Decimal
) -> None:
    max_quantity: Decimal | None = {
        BillingUnit.HOUR: MAX_HOUR_ENTRY_QUANTITY,
        BillingUnit.DAY: MAX_DAY_ENTRY_QUANTITY,
    }.get(unit)
    if quantity <= 0 or (max_quantity is not None and quantity > max_quantity):
        raise QuantityOutOfRangeError(change.billing_item_id, change.date, quantity)
