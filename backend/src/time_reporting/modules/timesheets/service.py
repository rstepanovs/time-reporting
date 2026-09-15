"""Timesheet domain logic.

Changes are flushed through the repository; the bus commits. Reads projects, users and calendar
data only through their modules' ``contracts.py`` messages, dispatched on the shared ``Bus``.
"""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from time_reporting.core.cqrs import Bus
from time_reporting.db.mixins import utc_now
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
    ApproveTimesheetWeek,
    DailyHoursExceededError,
    DuplicateChangeError,
    EntryDateOutsideWeekError,
    InvalidWeekStatusTransitionError,
    QuantityOutOfRangeError,
    ReturnCommentRequiredError,
    ReturnTimesheetWeek,
    RowCommentChange,
    SaveTimesheetWeek,
    SelfReviewError,
    SubmitTimesheetWeek,
    TimeEntryChange,
    TimeEntryDTO,
    TimesheetBillingItemNotFoundError,
    TimesheetRowClosedError,
    TimesheetRowDTO,
    TimesheetWeekDTO,
    TimesheetWeekLockedError,
    TimesheetWeekStatus,
    WeekStartNotMondayError,
)
from time_reporting.modules.timesheets.models import TimeEntry, TimesheetRowComment, TimesheetWeek
from time_reporting.modules.timesheets.repository import (
    RowCommentRepository,
    TimeEntryRepository,
    TimesheetWeekRepository,
)
from time_reporting.modules.users.contracts import GetUserById, UserDTO, UserNotFoundError, UserRole
from time_reporting.modules.work_calendar.contracts import GetCalendarDays

_WEEK_LENGTH_DAYS = 7
_EDITABLE_STATUSES = frozenset({TimesheetWeekStatus.DRAFT, TimesheetWeekStatus.RETURNED})
_REVIEWABLE_STATUSES = frozenset({TimesheetWeekStatus.SUBMITTED, TimesheetWeekStatus.APPROVED})
_MANAGER_ROLES = frozenset({UserRole.ADMIN, UserRole.PROJECT_MANAGER})


class TimesheetService:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._entries = TimeEntryRepository(bus.session)
        self._weeks = TimesheetWeekRepository(bus.session)
        self._comments = RowCommentRepository(bus.session)

    async def get_week(
        self, *, user_id: UUID, week_start: date, viewer_id: UUID
    ) -> TimesheetWeekDTO:
        _ensure_monday(week_start)
        user = await self._bus.query(GetUserById(user_id=user_id))
        if user is None:
            raise UserNotFoundError(user_id)
        viewer = (
            user if viewer_id == user_id else await self._bus.query(GetUserById(user_id=viewer_id))
        )
        week_end = _week_end(week_start)

        entries = await self._entries.list_for_user_in_range(user_id, week_start, week_end)
        comments = await self._comments.list_for_week(user_id=user_id, week_start=week_start)
        comments_by_item = {comment.billing_item_id: comment.comment for comment in comments}
        billing_item_ids = frozenset(entry.billing_item_id for entry in entries) | frozenset(
            comments_by_item
        )
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
                    comment=comments_by_item.get(item_id),
                )
                for item_id, billing_item in items_by_id.items()
            ),
            key=lambda row: (row.project.name, row.billing_item.position),
        )

        days = await self._bus.query(GetCalendarDays(date_from=week_start, date_to=week_end))

        week_row = await self._weeks.get(user_id=user_id, week_start=week_start)
        status = week_row.status if week_row is not None else TimesheetWeekStatus.DRAFT
        reviewed_by_name = await self._reviewer_name(week_row)
        is_owner_editable = viewer_id == user_id and status in _EDITABLE_STATUSES
        can_review = (
            viewer is not None
            and viewer.role in _MANAGER_ROLES
            and status in _REVIEWABLE_STATUSES
            and not (viewer.role == UserRole.PROJECT_MANAGER and viewer_id == user_id)
        )

        return TimesheetWeekDTO(
            user=user,
            week_start=week_start,
            status=status,
            submitted_at=week_row.submitted_at if week_row is not None else None,
            reviewed_at=week_row.reviewed_at if week_row is not None else None,
            reviewed_by_name=reviewed_by_name,
            return_comment=week_row.return_comment if week_row is not None else None,
            can_edit=is_owner_editable,
            can_submit=is_owner_editable,
            can_review=can_review,
            days=days,
            rows=tuple(rows),
        )

    async def save_week(self, command: SaveTimesheetWeek) -> TimesheetWeekDTO:
        week_start = command.week_start
        _ensure_monday(week_start)
        if await self._bus.query(GetUserById(user_id=command.user_id)) is None:
            raise UserNotFoundError(command.user_id)
        await self._ensure_week_editable(command.user_id, week_start)
        week_end = _week_end(week_start)

        seen_cells: set[tuple[UUID, date]] = set()
        for change in command.changes:
            cell = (change.billing_item_id, change.date)
            if cell in seen_cells:
                raise DuplicateChangeError(*cell)
            seen_cells.add(cell)
            if not week_start <= change.date <= week_end:
                raise EntryDateOutsideWeekError(change.date, week_start)

        seen_comment_items: set[UUID] = set()
        for row_comment in command.row_comments:
            if row_comment.billing_item_id in seen_comment_items:
                raise DuplicateChangeError(row_comment.billing_item_id, week_start)
            seen_comment_items.add(row_comment.billing_item_id)

        open_items, projects_by_item = await self._open_items(command.user_id)
        await self._ensure_billing_items_open(
            frozenset(c.billing_item_id for c in command.changes), open_items
        )
        await self._ensure_billing_items_open(
            frozenset(c.billing_item_id for c in command.row_comments), open_items
        )
        for change in command.changes:
            if change.quantity is not None:
                billing_item = open_items[change.billing_item_id]
                _ensure_quantity_in_range(billing_item.unit, change, change.quantity)

        await self._apply_changes(command.user_id, command.changes, open_items, projects_by_item)
        await self._apply_row_comments(command.user_id, week_start, command.row_comments)
        await self._ensure_daily_hours_in_range(command.user_id, command.changes)

        return await self.get_week(
            user_id=command.user_id, week_start=week_start, viewer_id=command.user_id
        )

    async def submit_week(self, command: SubmitTimesheetWeek) -> TimesheetWeekDTO:
        week_start = command.week_start
        _ensure_monday(week_start)
        if await self._bus.query(GetUserById(user_id=command.user_id)) is None:
            raise UserNotFoundError(command.user_id)

        week_row = await self._weeks.get(user_id=command.user_id, week_start=week_start)
        status = week_row.status if week_row is not None else TimesheetWeekStatus.DRAFT
        if status not in _EDITABLE_STATUSES:
            raise InvalidWeekStatusTransitionError(week_start, status, "submit")

        now = utc_now()
        if week_row is None:
            week_row = TimesheetWeek(
                user_id=command.user_id,
                week_start=week_start,
                status=TimesheetWeekStatus.SUBMITTED,
                submitted_at=now,
            )
        else:
            week_row.status = TimesheetWeekStatus.SUBMITTED
            week_row.submitted_at = now
            week_row.reviewed_at = None
            week_row.reviewed_by_id = None
            week_row.return_comment = None
        await self._weeks.save(week_row)

        return await self.get_week(
            user_id=command.user_id, week_start=week_start, viewer_id=command.user_id
        )

    async def approve_week(self, command: ApproveTimesheetWeek) -> TimesheetWeekDTO:
        week_start = command.week_start
        _ensure_monday(week_start)
        if await self._bus.query(GetUserById(user_id=command.user_id)) is None:
            raise UserNotFoundError(command.user_id)
        reviewer = await self._bus.query(GetUserById(user_id=command.reviewer_id))
        self._ensure_not_self_review(reviewer, command.user_id, command.reviewer_id)

        week_row = await self._weeks.get(user_id=command.user_id, week_start=week_start)
        status = week_row.status if week_row is not None else TimesheetWeekStatus.DRAFT
        if week_row is None or status != TimesheetWeekStatus.SUBMITTED:
            raise InvalidWeekStatusTransitionError(week_start, status, "approve")

        week_row.status = TimesheetWeekStatus.APPROVED
        week_row.reviewed_at = utc_now()
        week_row.reviewed_by_id = command.reviewer_id
        week_row.return_comment = None
        await self._weeks.save(week_row)

        return await self.get_week(
            user_id=command.user_id, week_start=week_start, viewer_id=command.reviewer_id
        )

    async def return_week(self, command: ReturnTimesheetWeek) -> TimesheetWeekDTO:
        week_start = command.week_start
        _ensure_monday(week_start)
        if await self._bus.query(GetUserById(user_id=command.user_id)) is None:
            raise UserNotFoundError(command.user_id)
        comment = command.comment.strip()
        if not comment:
            raise ReturnCommentRequiredError()
        reviewer = await self._bus.query(GetUserById(user_id=command.reviewer_id))
        self._ensure_not_self_review(reviewer, command.user_id, command.reviewer_id)

        week_row = await self._weeks.get(user_id=command.user_id, week_start=week_start)
        status = week_row.status if week_row is not None else TimesheetWeekStatus.DRAFT
        if week_row is None or status not in _REVIEWABLE_STATUSES:
            raise InvalidWeekStatusTransitionError(week_start, status, "return")

        week_row.status = TimesheetWeekStatus.RETURNED
        week_row.reviewed_at = utc_now()
        week_row.reviewed_by_id = command.reviewer_id
        week_row.return_comment = comment
        await self._weeks.save(week_row)

        return await self.get_week(
            user_id=command.user_id, week_start=week_start, viewer_id=command.reviewer_id
        )

    @staticmethod
    def _ensure_not_self_review(reviewer: UserDTO | None, user_id: UUID, reviewer_id: UUID) -> None:
        if reviewer_id == user_id and (reviewer is None or reviewer.role != UserRole.ADMIN):
            raise SelfReviewError()

    async def _reviewer_name(self, week_row: TimesheetWeek | None) -> str | None:
        if week_row is None or week_row.reviewed_by_id is None:
            return None
        reviewer = await self._bus.query(GetUserById(user_id=week_row.reviewed_by_id))
        return reviewer.name if reviewer is not None else None

    async def _ensure_week_editable(self, user_id: UUID, week_start: date) -> None:
        week_row = await self._weeks.get(user_id=user_id, week_start=week_start)
        if week_row is not None and week_row.status not in _EDITABLE_STATUSES:
            raise TimesheetWeekLockedError(week_start, week_row.status)

    async def _apply_row_comments(
        self, user_id: UUID, week_start: date, row_comments: tuple[RowCommentChange, ...]
    ) -> None:
        for row_comment in row_comments:
            existing = await self._comments.get(
                user_id=user_id, week_start=week_start, billing_item_id=row_comment.billing_item_id
            )
            comment_text = (row_comment.comment or "").strip() or None
            if comment_text is None:
                if existing is not None:
                    await self._comments.delete(existing)
                continue
            if existing is not None:
                existing.comment = comment_text
                await self._comments.save(existing)
            else:
                await self._comments.save(
                    TimesheetRowComment(
                        user_id=user_id,
                        week_start=week_start,
                        billing_item_id=row_comment.billing_item_id,
                        comment=comment_text,
                    )
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

    async def _ensure_billing_items_open(
        self,
        billing_item_ids: frozenset[UUID],
        open_items: dict[UUID, ProjectBillingItemDTO],
    ) -> None:
        """Raise if any of ``billing_item_ids`` isn't currently open for this user: not found at
        all (``TimesheetBillingItemNotFoundError``), or found but closed
        (``TimesheetRowClosedError`` — archived, or the user isn't a member anymore)."""
        unknown_ids = billing_item_ids - open_items.keys()
        if not unknown_ids:
            return
        existing = await self._bus.query(GetProjectBillingItemsByIds(billing_item_ids=unknown_ids))
        existing_ids = frozenset(item.id for item in existing)
        for billing_item_id in unknown_ids:
            if billing_item_id not in existing_ids:
                raise TimesheetBillingItemNotFoundError(billing_item_id)
            raise TimesheetRowClosedError(billing_item_id)

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
