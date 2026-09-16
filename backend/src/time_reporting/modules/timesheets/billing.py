"""Sending a project's calendar month to billing, and reopening a sent one.

A stub: "sending" records the handoff (``ProjectBillingPeriod``) and locks the period against
further edits — invoicing itself doesn't exist yet; a future invoices module would pick up sent
periods from here. Kept separate from ``service.py`` (week read/write) and ``team.py`` (the team
overview's own read of the same readiness rule, which this reuses via ``billing_readiness``).
"""

from collections.abc import Sequence
from datetime import date
from uuid import UUID

from time_reporting.core.cqrs import Bus
from time_reporting.db.mixins import utc_now
from time_reporting.modules.audit.contracts import AuditAction, RecordAuditEvent
from time_reporting.modules.projects.contracts import (
    BillingUnit,
    GetProjectBillingItemsByIds,
    GetProjectById,
)
from time_reporting.modules.timesheets.contracts import (
    BillingPeriodAlreadySentError,
    BillingPeriodNotFoundError,
    BillingPeriodNotReadyError,
    BillingPeriodStatus,
    ProjectBillingPeriodDTO,
    ReopenProjectBillingPeriod,
    SendProjectMonthToBilling,
    TimesheetProjectNotFoundError,
)
from time_reporting.modules.timesheets.models import ProjectBillingPeriod, TimeEntry
from time_reporting.modules.timesheets.repository import (
    ProjectBillingPeriodRepository,
    TimeEntryRepository,
    TimesheetWeekRepository,
)
from time_reporting.modules.timesheets.summary import (
    _end_of_iso_week,
    _month_bounds,
    _preset_of,
    _QuantityAccumulator,
    _start_of_iso_week,
)
from time_reporting.modules.timesheets.team import billing_readiness
from time_reporting.modules.users.contracts import GetUserById, UserDTO, UserNotFoundError


class BillingService:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._entries = TimeEntryRepository(bus.session)
        self._weeks = TimesheetWeekRepository(bus.session)
        self._periods = ProjectBillingPeriodRepository(bus.session)

    async def send_to_billing(self, command: SendProjectMonthToBilling) -> ProjectBillingPeriodDTO:
        project = await self._bus.query(GetProjectById(project_id=command.project_id))
        if project is None:
            raise TimesheetProjectNotFoundError(command.project_id)
        sender = await self._bus.query(GetUserById(user_id=command.sent_by_id))
        if sender is None:
            raise UserNotFoundError(command.sent_by_id)

        month_first, month_last = _month_bounds(command.year, command.month)
        if (
            await self._periods.get(project_id=command.project_id, period_start=month_first)
            is not None
        ):
            raise BillingPeriodAlreadySentError(command.project_id, month_first)

        entries = await self._entries.list_for_projects_in_range(
            frozenset({command.project_id}), month_first, month_last
        )
        scope_pairs = {
            (time_entry.user_id, _start_of_iso_week(time_entry.entry_date))
            for time_entry in entries
        }
        user_ids = frozenset(user_id for user_id, _week_start in scope_pairs)
        week_rows = (
            await self._weeks.list_for_users_in_range(
                user_ids, _start_of_iso_week(month_first), _end_of_iso_week(month_last)
            )
            if user_ids
            else ()
        )
        status_by_user_week = {(row.user_id, row.week_start): row.status for row in week_rows}
        status, blocking_weeks, _weeks_in_scope = billing_readiness(
            scope_pairs, status_by_user_week
        )
        if status is not BillingPeriodStatus.READY:
            raise BillingPeriodNotReadyError(blocking_weeks)

        period = ProjectBillingPeriod(
            project_id=command.project_id,
            period_start=month_first,
            period_end=month_last,
            sent_at=utc_now(),
            sent_by_id=command.sent_by_id,
        )
        await self._periods.save(period)
        await self._bus.execute(
            RecordAuditEvent(
                actor_id=command.sent_by_id,
                action=AuditAction.BILLING_PERIOD_SENT,
                entity_type="billing_period",
                entity_id=f"{command.project_id}:{month_first.isoformat()}",
                summary=(
                    f"Sent {project.customer.name} · {project.name} "
                    f"({month_first:%Y-%m}) to billing"
                ),
                details={
                    "project_id": str(command.project_id),
                    "period_start": month_first.isoformat(),
                    "period_end": month_last.isoformat(),
                },
            )
        )

        return await self._period_dto(period, entries, project.customer.currency, sender)

    async def reopen_period(self, command: ReopenProjectBillingPeriod) -> None:
        period = await self._periods.get(
            project_id=command.project_id, period_start=command.period_start
        )
        if period is None:
            raise BillingPeriodNotFoundError(command.project_id, command.period_start)
        # `ON DELETE RESTRICT` on `project_billing_periods.project_id` guarantees the project
        # still exists while any of its periods (including this one, until the delete below) do.
        project = await self._bus.query(GetProjectById(project_id=command.project_id))
        assert project is not None
        await self._periods.delete(period)
        await self._bus.execute(
            RecordAuditEvent(
                actor_id=command.actor_id,
                action=AuditAction.BILLING_PERIOD_REOPENED,
                entity_type="billing_period",
                entity_id=f"{command.project_id}:{command.period_start.isoformat()}",
                summary=(
                    f"Reopened {project.customer.name} · {project.name} "
                    f"({command.period_start:%Y-%m}) billing period"
                ),
            )
        )

    async def _period_dto(
        self,
        period: ProjectBillingPeriod,
        entries: Sequence[TimeEntry],
        currency: str,
        sent_by: UserDTO,
    ) -> ProjectBillingPeriodDTO:
        billing_item_ids = frozenset(time_entry.billing_item_id for time_entry in entries)
        items_by_id = {
            item.id: item
            for item in await self._bus.query(
                GetProjectBillingItemsByIds(billing_item_ids=billing_item_ids)
            )
        }
        accumulator = _QuantityAccumulator()
        scope_pairs: set[tuple[UUID, date]] = set()
        for time_entry in entries:
            scope_pairs.add((time_entry.user_id, _start_of_iso_week(time_entry.entry_date)))
            if time_entry.unit is BillingUnit.HOUR:
                accumulator.add_hours(
                    preset=_preset_of(items_by_id.get(time_entry.billing_item_id)),
                    quantity=time_entry.quantity,
                )
            elif time_entry.unit is BillingUnit.DAY:
                accumulator.add_days(time_entry.quantity)
            elif time_entry.unit is BillingUnit.AMOUNT:
                accumulator.add_amount(currency=currency, quantity=time_entry.quantity)

        return ProjectBillingPeriodDTO(
            project_id=period.project_id,
            period_start=period.period_start,
            period_end=period.period_end,
            status=BillingPeriodStatus.SENT,
            sent_at=period.sent_at,
            sent_by=sent_by,
            blocking_weeks=0,
            weeks_in_scope=len(scope_pairs),
            hours=accumulator.freeze_hours(),
            per_diem_days=accumulator.days,
            expenses=accumulator.freeze_amounts(),
        )
