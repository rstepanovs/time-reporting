"""Persistence of timesheet entities. Flushes but never commits — the bus owns transactions."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Date, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from time_reporting.modules.projects.contracts import BillingUnit
from time_reporting.modules.timesheets.contracts import TimesheetWeekStatus
from time_reporting.modules.timesheets.models import (
    ProjectBillingPeriod,
    TimeEntry,
    TimesheetRowComment,
    TimesheetWeek,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class MonthlyHoursTotal:
    """One (month, project, billing item)'s summed ``hour``-unit quantity, for the dashboard's
    year-hours summary."""

    month_start: date
    project_id: UUID
    billing_item_id: UUID
    total: Decimal


class TimeEntryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, *, user_id: UUID, billing_item_id: UUID, entry_date: date
    ) -> TimeEntry | None:
        result = await self._session.scalars(
            select(TimeEntry).where(
                TimeEntry.user_id == user_id,
                TimeEntry.billing_item_id == billing_item_id,
                TimeEntry.entry_date == entry_date,
            )
        )
        return result.one_or_none()

    async def list_for_user_in_range(
        self, user_id: UUID, date_from: date, date_to: date
    ) -> Sequence[TimeEntry]:
        result = await self._session.scalars(
            select(TimeEntry)
            .where(
                TimeEntry.user_id == user_id,
                TimeEntry.entry_date >= date_from,
                TimeEntry.entry_date <= date_to,
            )
            .order_by(TimeEntry.entry_date)
        )
        return result.all()

    async def list_for_projects_in_range(
        self, project_ids: frozenset[UUID], date_from: date, date_to: date
    ) -> Sequence[TimeEntry]:
        """Every entry (any user, any unit) on any of ``project_ids`` in the date range, for the
        manager team overview and billing-period readiness."""
        if not project_ids:
            return ()
        result = await self._session.scalars(
            select(TimeEntry)
            .where(
                TimeEntry.project_id.in_(project_ids),
                TimeEntry.entry_date >= date_from,
                TimeEntry.entry_date <= date_to,
            )
            .order_by(TimeEntry.entry_date)
        )
        return result.all()

    async def sum_hours_by_user_in_range(
        self, user_ids: frozenset[UUID], date_from: date, date_to: date
    ) -> dict[UUID, Decimal]:
        """Each user's total ``hour``-unit quantity (any project) in the date range, for the team
        overview's per-member month total."""
        if not user_ids:
            return {}
        result = await self._session.execute(
            select(TimeEntry.user_id, func.sum(TimeEntry.quantity))
            .where(
                TimeEntry.user_id.in_(user_ids),
                TimeEntry.entry_date >= date_from,
                TimeEntry.entry_date <= date_to,
                TimeEntry.unit == BillingUnit.HOUR,
            )
            .group_by(TimeEntry.user_id)
        )
        return {user_id: total for user_id, total in result.all()}

    async def sum_quantity_by_date(
        self, user_id: UUID, dates: frozenset[date], unit: BillingUnit
    ) -> dict[date, Decimal]:
        """The user's total quantity of ``unit``-unit entries on each of ``dates`` that has any."""
        if not dates:
            return {}
        result = await self._session.execute(
            select(TimeEntry.entry_date, func.sum(TimeEntry.quantity))
            .where(
                TimeEntry.user_id == user_id,
                TimeEntry.entry_date.in_(dates),
                TimeEntry.unit == unit,
            )
            .group_by(TimeEntry.entry_date)
        )
        return {entry_date: total for entry_date, total in result.all()}

    async def sum_hours_by_month_and_billing_item(
        self, user_id: UUID, date_from: date, date_to: date
    ) -> Sequence[MonthlyHoursTotal]:
        """The user's total ``hour``-unit quantity per (month, project, billing item) over the
        range, for the dashboard's year-hours summary."""
        month_start = func.date_trunc("month", TimeEntry.entry_date).cast(Date).label("month_start")
        result = await self._session.execute(
            select(
                month_start,
                TimeEntry.project_id,
                TimeEntry.billing_item_id,
                func.sum(TimeEntry.quantity).label("total"),
            )
            .where(
                TimeEntry.user_id == user_id,
                TimeEntry.entry_date >= date_from,
                TimeEntry.entry_date <= date_to,
                TimeEntry.unit == BillingUnit.HOUR,
            )
            .group_by(month_start, TimeEntry.project_id, TimeEntry.billing_item_id)
        )
        return [
            MonthlyHoursTotal(
                month_start=row.month_start,
                project_id=row.project_id,
                billing_item_id=row.billing_item_id,
                total=row.total,
            )
            for row in result.all()
        ]

    async def count(
        self,
        *,
        user_id: UUID | None = None,
        project_id: UUID | None = None,
        billing_item_id: UUID | None = None,
    ) -> int:
        statement: Select[tuple[int]] = select(func.count()).select_from(TimeEntry)
        statement = self._filtered(
            statement, user_id=user_id, project_id=project_id, billing_item_id=billing_item_id
        )
        result = await self._session.execute(statement)
        return result.scalar_one()

    def _filtered[T: tuple[Any, ...]](
        self,
        statement: Select[T],
        *,
        user_id: UUID | None,
        project_id: UUID | None,
        billing_item_id: UUID | None,
    ) -> Select[T]:
        if user_id is not None:
            statement = statement.where(TimeEntry.user_id == user_id)
        if project_id is not None:
            statement = statement.where(TimeEntry.project_id == project_id)
        if billing_item_id is not None:
            statement = statement.where(TimeEntry.billing_item_id == billing_item_id)
        return statement

    async def sum_hours_by_user_week(
        self, user_ids: frozenset[UUID]
    ) -> dict[tuple[UUID, date], Decimal]:
        """Each user's total ``hour``-unit quantity per ISO week (Monday-start — Postgres'
        ``date_trunc('week', ...)`` already uses the ISO definition, matching ``week_start``
        elsewhere in this module), for the approvals list's per-week totals."""
        if not user_ids:
            return {}
        week_start = func.date_trunc("week", TimeEntry.entry_date).cast(Date).label("week_start")
        result = await self._session.execute(
            select(TimeEntry.user_id, week_start, func.sum(TimeEntry.quantity))
            .where(TimeEntry.user_id.in_(user_ids), TimeEntry.unit == BillingUnit.HOUR)
            .group_by(TimeEntry.user_id, week_start)
        )
        return {(user_id, row_week_start): total for user_id, row_week_start, total in result.all()}

    async def save(self, entry: TimeEntry) -> None:
        """Add ``entry`` to the session (if new) and flush pending changes."""
        self._session.add(entry)
        await self._session.flush()

    async def delete(self, entry: TimeEntry) -> None:
        await self._session.delete(entry)
        await self._session.flush()


class TimesheetWeekRepository:
    """Persistence of ``TimesheetWeek`` — a (user, week_start)'s place in the submit/review
    workflow. No row means draft; this repository never creates a ``draft`` row."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, *, user_id: UUID, week_start: date) -> TimesheetWeek | None:
        result = await self._session.scalars(
            select(TimesheetWeek).where(
                TimesheetWeek.user_id == user_id, TimesheetWeek.week_start == week_start
            )
        )
        return result.one_or_none()

    async def list_by_status(self, status: TimesheetWeekStatus) -> Sequence[TimesheetWeek]:
        result = await self._session.scalars(
            select(TimesheetWeek)
            .where(TimesheetWeek.status == status)
            .order_by(TimesheetWeek.submitted_at)
        )
        return result.all()

    async def list_for_users_in_range(
        self, user_ids: frozenset[UUID], date_from: date, date_to: date
    ) -> Sequence[TimesheetWeek]:
        """Every ``TimesheetWeek`` row for ``user_ids`` whose ``week_start`` falls in the range,
        for the manager team overview's status grid. A (user, week) with no row is ``draft``."""
        if not user_ids:
            return ()
        result = await self._session.scalars(
            select(TimesheetWeek).where(
                TimesheetWeek.user_id.in_(user_ids),
                TimesheetWeek.week_start >= date_from,
                TimesheetWeek.week_start <= date_to,
            )
        )
        return result.all()

    async def save(self, week: TimesheetWeek) -> None:
        """Add ``week`` to the session (if new) and flush pending changes."""
        self._session.add(week)
        await self._session.flush()


class RowCommentRepository:
    """Persistence of ``TimesheetRowComment`` — a per (user, week, billing item) note."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_week(
        self, *, user_id: UUID, week_start: date
    ) -> Sequence[TimesheetRowComment]:
        result = await self._session.scalars(
            select(TimesheetRowComment).where(
                TimesheetRowComment.user_id == user_id,
                TimesheetRowComment.week_start == week_start,
            )
        )
        return result.all()

    async def get(
        self, *, user_id: UUID, week_start: date, billing_item_id: UUID
    ) -> TimesheetRowComment | None:
        result = await self._session.scalars(
            select(TimesheetRowComment).where(
                TimesheetRowComment.user_id == user_id,
                TimesheetRowComment.week_start == week_start,
                TimesheetRowComment.billing_item_id == billing_item_id,
            )
        )
        return result.one_or_none()

    async def save(self, comment: TimesheetRowComment) -> None:
        """Add ``comment`` to the session (if new) and flush pending changes."""
        self._session.add(comment)
        await self._session.flush()

    async def delete(self, comment: TimesheetRowComment) -> None:
        await self._session.delete(comment)
        await self._session.flush()


class ProjectBillingPeriodRepository:
    """Persistence of ``ProjectBillingPeriod`` — a project's month sent to billing. No row means
    not sent."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, *, project_id: UUID, period_start: date) -> ProjectBillingPeriod | None:
        result = await self._session.scalars(
            select(ProjectBillingPeriod).where(
                ProjectBillingPeriod.project_id == project_id,
                ProjectBillingPeriod.period_start == period_start,
            )
        )
        return result.one_or_none()

    async def list_by_invoice_id(self, invoice_id: UUID) -> Sequence[ProjectBillingPeriod]:
        """Every period currently marked with ``invoice_id`` — used to clear the mark when the
        future ``invoices`` module deletes a draft."""
        result = await self._session.scalars(
            select(ProjectBillingPeriod).where(ProjectBillingPeriod.invoice_id == invoice_id)
        )
        return result.all()

    async def list_for_projects_in_range(
        self, project_ids: frozenset[UUID], date_from: date, date_to: date
    ) -> Sequence[ProjectBillingPeriod]:
        """Periods for ``project_ids`` whose ``period_start`` falls in the range — used to look up
        a specific month's sent status for several projects in one query."""
        if not project_ids:
            return ()
        result = await self._session.scalars(
            select(ProjectBillingPeriod).where(
                ProjectBillingPeriod.project_id.in_(project_ids),
                ProjectBillingPeriod.period_start >= date_from,
                ProjectBillingPeriod.period_start <= date_to,
            )
        )
        return result.all()

    async def list_overlapping(
        self, project_ids: frozenset[UUID], date_from: date, date_to: date
    ) -> Sequence[ProjectBillingPeriod]:
        """Periods for ``project_ids`` whose range overlaps [``date_from``, ``date_to``] — used to
        check whether a week's dates fall inside a sent period, for the lock rules."""
        if not project_ids:
            return ()
        result = await self._session.scalars(
            select(ProjectBillingPeriod).where(
                ProjectBillingPeriod.project_id.in_(project_ids),
                ProjectBillingPeriod.period_start <= date_to,
                ProjectBillingPeriod.period_end >= date_from,
            )
        )
        return result.all()

    async def get_page(
        self,
        *,
        project_ids: frozenset[UUID] | None,
        month_from: date | None,
        month_to: date | None,
        invoiced: bool | None,
        limit: int,
        offset: int,
    ) -> Sequence[ProjectBillingPeriod]:
        """Newest ``sent_at`` first. ``project_ids=None`` means no project filter; an empty (but
        not ``None``) set short-circuits to no rows, without hitting the database."""
        if project_ids is not None and not project_ids:
            return ()
        statement = (
            self._filtered(
                select(ProjectBillingPeriod),
                project_ids=project_ids,
                month_from=month_from,
                month_to=month_to,
                invoiced=invoiced,
            )
            .order_by(ProjectBillingPeriod.sent_at.desc(), ProjectBillingPeriod.id)
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.scalars(statement)
        return result.all()

    async def count(
        self,
        *,
        project_ids: frozenset[UUID] | None,
        month_from: date | None,
        month_to: date | None,
        invoiced: bool | None,
    ) -> int:
        if project_ids is not None and not project_ids:
            return 0
        statement = self._filtered(
            select(func.count()).select_from(ProjectBillingPeriod),
            project_ids=project_ids,
            month_from=month_from,
            month_to=month_to,
            invoiced=invoiced,
        )
        result = await self._session.execute(statement)
        return result.scalar_one()

    def _filtered[T: tuple[Any, ...]](
        self,
        statement: Select[T],
        *,
        project_ids: frozenset[UUID] | None,
        month_from: date | None,
        month_to: date | None,
        invoiced: bool | None,
    ) -> Select[T]:
        if project_ids is not None:
            statement = statement.where(ProjectBillingPeriod.project_id.in_(project_ids))
        if month_from is not None:
            statement = statement.where(ProjectBillingPeriod.period_start >= month_from)
        if month_to is not None:
            statement = statement.where(ProjectBillingPeriod.period_start <= month_to)
        if invoiced is True:
            statement = statement.where(ProjectBillingPeriod.invoice_id.is_not(None))
        elif invoiced is False:
            statement = statement.where(ProjectBillingPeriod.invoice_id.is_(None))
        return statement

    async def save(self, period: ProjectBillingPeriod) -> None:
        """Add ``period`` to the session and flush."""
        self._session.add(period)
        await self._session.flush()

    async def delete(self, period: ProjectBillingPeriod) -> None:
        await self._session.delete(period)
        await self._session.flush()
