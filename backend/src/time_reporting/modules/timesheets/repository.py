"""Persistence of ``TimeEntry`` entities. Flushes but never commits — the bus owns transactions."""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from time_reporting.modules.projects.contracts import BillingUnit
from time_reporting.modules.timesheets.models import TimeEntry


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

    async def save(self, entry: TimeEntry) -> None:
        """Add ``entry`` to the session (if new) and flush pending changes."""
        self._session.add(entry)
        await self._session.flush()

    async def delete(self, entry: TimeEntry) -> None:
        await self._session.delete(entry)
        await self._session.flush()
