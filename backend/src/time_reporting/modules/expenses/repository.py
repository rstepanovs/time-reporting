"""Persistence of expense entities. Flushes but never commits — the bus owns transactions."""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from time_reporting.modules.expenses.contracts import (
    ExpenseReportAlreadyExistsError,
    ExpenseReportStatus,
)
from time_reporting.modules.expenses.models import (
    ExpenseAttachment,
    ExpenseReport,
    ExpenseReportLine,
)

_REPORT_UNIQUE_CONSTRAINT = "uq_expense_reports_user_id_project_id_period_start"


class ExpenseReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, report_id: UUID) -> ExpenseReport | None:
        result = await self._session.scalars(
            select(ExpenseReport).where(ExpenseReport.id == report_id)
        )
        return result.one_or_none()

    async def get_by_period(
        self, *, user_id: UUID, project_id: UUID, period_start: date
    ) -> ExpenseReport | None:
        result = await self._session.scalars(
            select(ExpenseReport).where(
                ExpenseReport.user_id == user_id,
                ExpenseReport.project_id == project_id,
                ExpenseReport.period_start == period_start,
            )
        )
        return result.one_or_none()

    async def list_for_user_period(
        self, *, user_id: UUID, period_start: date
    ) -> Sequence[ExpenseReport]:
        """Every report ``user_id`` has for ``period_start`` (one per project)."""
        result = await self._session.scalars(
            select(ExpenseReport).where(
                ExpenseReport.user_id == user_id,
                ExpenseReport.period_start == period_start,
            )
        )
        return result.all()

    async def list_for_projects_period(
        self, *, project_ids: frozenset[UUID], period_start: date
    ) -> Sequence[ExpenseReport]:
        """Every report for any of ``project_ids`` at ``period_start`` (any user) — used by the
        timesheets module's billing readiness check and lock/unlock, via
        ``ListProjectMonthExpenseReports``."""
        if not project_ids:
            return ()
        result = await self._session.scalars(
            select(ExpenseReport).where(
                ExpenseReport.project_id.in_(project_ids),
                ExpenseReport.period_start == period_start,
            )
        )
        return result.all()

    async def list_by_status(self, status: ExpenseReportStatus) -> Sequence[ExpenseReport]:
        result = await self._session.scalars(
            select(ExpenseReport)
            .where(ExpenseReport.status == status)
            .order_by(ExpenseReport.submitted_at)
        )
        return result.all()

    async def list_for_period(self, period_start: date) -> Sequence[ExpenseReport]:
        """Every report (any user, any project, any status) whose ``period_start`` is this month —
        unlike ``list_for_projects_period``, not scoped to a set of projects, since the accountant
        package (``ListMonthExpenseLines``) spans every project including internal ones."""
        result = await self._session.scalars(
            select(ExpenseReport).where(ExpenseReport.period_start == period_start)
        )
        return result.all()

    async def count_for_period_excluding_status(
        self, *, period_start: date, status: ExpenseReportStatus
    ) -> int:
        """How many reports at ``period_start`` are *not* ``status`` — used for
        ``CountMonthReportsNotApproved`` (``status=APPROVED``)."""
        result = await self._session.execute(
            select(func.count())
            .select_from(ExpenseReport)
            .where(ExpenseReport.period_start == period_start, ExpenseReport.status != status)
        )
        return result.scalar_one()

    async def save(self, report: ExpenseReport) -> None:
        """Add ``report`` to the session (if new) and flush pending changes."""
        self._session.add(report)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            if _REPORT_UNIQUE_CONSTRAINT in str(exc.orig):
                raise ExpenseReportAlreadyExistsError(
                    report.user_id, report.project_id, report.period_start
                ) from exc
            raise

    async def delete(self, report: ExpenseReport) -> None:
        await self._session.delete(report)
        await self._session.flush()


class ExpenseReportLineRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, line_id: UUID) -> ExpenseReportLine | None:
        result = await self._session.scalars(
            select(ExpenseReportLine).where(ExpenseReportLine.id == line_id)
        )
        return result.one_or_none()

    async def list_for_report(self, report_id: UUID) -> Sequence[ExpenseReportLine]:
        result = await self._session.scalars(
            select(ExpenseReportLine)
            .where(ExpenseReportLine.report_id == report_id)
            .order_by(ExpenseReportLine.position, ExpenseReportLine.expense_date)
        )
        return result.all()

    async def next_position(self, report_id: UUID) -> int:
        """The position to give the next line added to ``report_id`` (existing max + 1, or 1)."""
        result = await self._session.execute(
            select(func.coalesce(func.max(ExpenseReportLine.position), 0) + 1).where(
                ExpenseReportLine.report_id == report_id
            )
        )
        return result.scalar_one()

    async def sum_and_count_by_report(
        self, report_ids: frozenset[UUID]
    ) -> dict[UUID, tuple[Decimal, int]]:
        """Each report's ``(total amount, line count)``, in one query — for list views that show a
        report's total without loading every line. A report with no lines is absent from the
        result (callers default to ``(Decimal("0"), 0)``)."""
        if not report_ids:
            return {}
        result = await self._session.execute(
            select(
                ExpenseReportLine.report_id,
                func.sum(ExpenseReportLine.amount),
                func.count(),
            )
            .where(ExpenseReportLine.report_id.in_(report_ids))
            .group_by(ExpenseReportLine.report_id)
        )
        return {report_id: (total, count) for report_id, total, count in result.all()}

    async def save(self, line: ExpenseReportLine) -> None:
        """Add ``line`` to the session (if new) and flush pending changes."""
        self._session.add(line)
        await self._session.flush()

    async def delete(self, line: ExpenseReportLine) -> None:
        await self._session.delete(line)
        await self._session.flush()


class ExpenseAttachmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, attachment_id: UUID) -> ExpenseAttachment | None:
        result = await self._session.scalars(
            select(ExpenseAttachment).where(ExpenseAttachment.id == attachment_id)
        )
        return result.one_or_none()

    async def list_for_report(self, report_id: UUID) -> Sequence[ExpenseAttachment]:
        result = await self._session.scalars(
            select(ExpenseAttachment)
            .where(ExpenseAttachment.report_id == report_id)
            .order_by(ExpenseAttachment.created_at)
        )
        return result.all()

    async def list_all_storage_keys(self) -> frozenset[str]:
        result = await self._session.scalars(select(ExpenseAttachment.storage_key))
        return frozenset(result.all())

    async def save(self, attachment: ExpenseAttachment) -> None:
        """Add ``attachment`` to the session (if new) and flush pending changes."""
        self._session.add(attachment)
        await self._session.flush()

    async def delete(self, attachment: ExpenseAttachment) -> None:
        await self._session.delete(attachment)
        await self._session.flush()
