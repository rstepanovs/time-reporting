"""Expense report domain logic.

Changes are flushed through the repository; the bus commits. Reads projects and users only through
their modules' ``contracts.py`` messages, dispatched on the shared ``Bus``.
"""

from calendar import monthrange
from datetime import date
from decimal import Decimal
from uuid import UUID

from time_reporting.core.cqrs import Bus
from time_reporting.db.mixins import utc_now
from time_reporting.modules.audit.contracts import AuditAction, RecordAuditEvent
from time_reporting.modules.expenses.contracts import (
    ApproveExpenseReport,
    CreateExpenseReport,
    DeleteExpenseReport,
    ExpenseBillingItemNotFoundError,
    ExpenseDateOutsidePeriodError,
    ExpenseLineChange,
    ExpenseLineNotFoundError,
    ExpenseProjectClosedError,
    ExpenseReportDTO,
    ExpenseReportLineDTO,
    ExpenseReportLockedError,
    ExpenseReportNotEditableError,
    ExpenseReportNotFoundError,
    ExpenseReportStatus,
    ExpenseReturnCommentRequiredError,
    ExpenseSelfReviewError,
    InvalidExpenseStatusTransitionError,
    LockProjectMonthExpenseReports,
    ReturnExpenseReport,
    SaveExpenseReportLines,
    SubmitExpenseReport,
    UnlockProjectMonthExpenseReports,
)
from time_reporting.modules.expenses.models import ExpenseReport, ExpenseReportLine
from time_reporting.modules.expenses.repository import (
    ExpenseReportLineRepository,
    ExpenseReportRepository,
)
from time_reporting.modules.projects.contracts import (
    BillingUnit,
    GetProjectBillingItemsByIds,
    GetProjectById,
    ListMemberProjectsWithBillingItems,
    ProjectBillingItemDTO,
    ProjectOptionDTO,
)
from time_reporting.modules.users.contracts import GetUserById, UserRole

_EDITABLE_STATUSES = frozenset({ExpenseReportStatus.DRAFT, ExpenseReportStatus.RETURNED})
_REVIEWABLE_STATUSES = frozenset({ExpenseReportStatus.SUBMITTED, ExpenseReportStatus.APPROVED})


class ExpenseService:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._reports = ExpenseReportRepository(bus.session)
        self._lines = ExpenseReportLineRepository(bus.session)

    async def create_report(self, command: CreateExpenseReport) -> ExpenseReportDTO:
        period_start, period_end = _month_bounds(command.year, command.month)
        await self._ensure_project_open(command.user_id, command.project_id)

        report = ExpenseReport(
            user_id=command.user_id,
            project_id=command.project_id,
            period_start=period_start,
            period_end=period_end,
            status=ExpenseReportStatus.DRAFT,
        )
        await self._reports.save(report)

        return await self.get_report(report_id=report.id, viewer_id=command.user_id)

    async def get_report(self, *, report_id: UUID, viewer_id: UUID) -> ExpenseReportDTO:
        report_row = await self._reports.get(report_id)
        if report_row is None:
            raise ExpenseReportNotFoundError(report_id)

        user = await self._bus.query(GetUserById(user_id=report_row.user_id))
        # `users.id` is referenced `ON DELETE RESTRICT`, so the owner always still exists.
        assert user is not None
        viewer = (
            user
            if viewer_id == report_row.user_id
            else await self._bus.query(GetUserById(user_id=viewer_id))
        )
        project = await self._bus.query(GetProjectById(project_id=report_row.project_id))
        # `projects.id` is referenced `ON DELETE RESTRICT`, so the project always still exists.
        assert project is not None

        lines = await self._lines.list_for_report(report_id)
        items_by_id = {
            item.id: item
            for item in await self._bus.query(
                GetProjectBillingItemsByIds(
                    billing_item_ids=frozenset(line.billing_item_id for line in lines)
                )
            )
        }
        line_dtos = tuple(
            ExpenseReportLineDTO(
                id=line.id,
                expense_date=line.expense_date,
                billing_item=items_by_id[line.billing_item_id],
                amount=line.amount,
                description=line.description,
                vendor=line.vendor,
                document_no=line.document_no,
            )
            for line in lines
        )
        total = sum((line.amount for line in line_dtos), start=Decimal("0"))

        reviewed_by_name = await self._reviewer_name(report_row)
        is_locked = report_row.locked_at is not None
        is_owner_editable = (
            viewer_id == report_row.user_id
            and report_row.status in _EDITABLE_STATUSES
            and not is_locked
        )
        can_review = (
            viewer is not None
            and UserRole.MANAGER in viewer.roles
            and report_row.status in _REVIEWABLE_STATUSES
            and viewer_id != report_row.user_id
            and not is_locked
        )

        return ExpenseReportDTO(
            id=report_row.id,
            project=project,
            user=user,
            period_start=report_row.period_start,
            period_end=report_row.period_end,
            status=report_row.status,
            submitted_at=report_row.submitted_at,
            reviewed_at=report_row.reviewed_at,
            reviewed_by_name=reviewed_by_name,
            return_comment=report_row.return_comment,
            locked_at=report_row.locked_at,
            can_edit=is_owner_editable,
            can_submit=is_owner_editable,
            can_review=can_review,
            is_locked=is_locked,
            total=total,
            lines=line_dtos,
        )

    async def save_lines(self, command: SaveExpenseReportLines) -> ExpenseReportDTO:
        report_row = await self._reports.get(command.report_id)
        if report_row is None:
            raise ExpenseReportNotFoundError(command.report_id)
        self._ensure_editable(report_row)

        open_items = await self._open_items(report_row.user_id, report_row.project_id)

        resolved: list[tuple[ExpenseReportLine | None, ExpenseLineChange]] = []
        for change in command.lines:
            existing_line: ExpenseReportLine | None = None
            if change.line_id is not None:
                existing_line = await self._lines.get(change.line_id)
                if existing_line is None or existing_line.report_id != report_row.id:
                    raise ExpenseLineNotFoundError(change.line_id)
            if change.billing_item_id not in open_items:
                raise ExpenseBillingItemNotFoundError(change.billing_item_id)
            if not report_row.period_start <= change.expense_date <= report_row.period_end:
                raise ExpenseDateOutsidePeriodError(
                    change.expense_date, report_row.period_start, report_row.period_end
                )
            resolved.append((existing_line, change))

        for existing_line, change in resolved:
            if existing_line is not None:
                existing_line.billing_item_id = change.billing_item_id
                existing_line.expense_date = change.expense_date
                existing_line.amount = change.amount
                existing_line.description = change.description
                existing_line.vendor = change.vendor
                existing_line.document_no = change.document_no
                await self._lines.save(existing_line)
            else:
                position = await self._lines.next_position(report_row.id)
                await self._lines.save(
                    ExpenseReportLine(
                        report_id=report_row.id,
                        billing_item_id=change.billing_item_id,
                        expense_date=change.expense_date,
                        amount=change.amount,
                        description=change.description,
                        vendor=change.vendor,
                        document_no=change.document_no,
                        position=position,
                    )
                )

        for line_id in command.delete_line_ids:
            line = await self._lines.get(line_id)
            if line is not None and line.report_id == report_row.id:
                await self._lines.delete(line)

        return await self.get_report(report_id=report_row.id, viewer_id=command.actor_id)

    async def delete_report(self, command: DeleteExpenseReport) -> None:
        report_row = await self._reports.get(command.report_id)
        if report_row is None:
            raise ExpenseReportNotFoundError(command.report_id)
        if report_row.status is not ExpenseReportStatus.DRAFT:
            raise ExpenseReportNotEditableError(report_row.id, report_row.status)
        await self._reports.delete(report_row)

    async def submit_report(self, command: SubmitExpenseReport) -> ExpenseReportDTO:
        report_row = await self._reports.get(command.report_id)
        if report_row is None:
            raise ExpenseReportNotFoundError(command.report_id)
        if report_row.status not in _EDITABLE_STATUSES:
            raise InvalidExpenseStatusTransitionError(report_row.id, report_row.status, "submit")

        report_row.status = ExpenseReportStatus.SUBMITTED
        report_row.submitted_at = utc_now()
        report_row.reviewed_at = None
        report_row.reviewed_by_id = None
        report_row.return_comment = None
        await self._reports.save(report_row)

        return await self.get_report(report_id=report_row.id, viewer_id=command.actor_id)

    async def approve_report(self, command: ApproveExpenseReport) -> ExpenseReportDTO:
        report_row = await self._reports.get(command.report_id)
        if report_row is None:
            raise ExpenseReportNotFoundError(command.report_id)
        self._ensure_not_self_review(report_row.user_id, command.reviewer_id)
        if report_row.status is not ExpenseReportStatus.SUBMITTED:
            raise InvalidExpenseStatusTransitionError(report_row.id, report_row.status, "approve")

        report_row.status = ExpenseReportStatus.APPROVED
        report_row.reviewed_at = utc_now()
        report_row.reviewed_by_id = command.reviewer_id
        report_row.return_comment = None
        await self._reports.save(report_row)

        project = await self._bus.query(GetProjectById(project_id=report_row.project_id))
        assert project is not None
        await self._bus.execute(
            RecordAuditEvent(
                actor_id=command.reviewer_id,
                action=AuditAction.EXPENSE_REPORT_APPROVED,
                entity_type="expense_report",
                entity_id=str(report_row.id),
                summary=(
                    f"Approved {project.customer.name} · {project.name} expense report "
                    f"({report_row.period_start:%Y-%m})"
                ),
            )
        )

        return await self.get_report(report_id=report_row.id, viewer_id=command.reviewer_id)

    async def return_report(self, command: ReturnExpenseReport) -> ExpenseReportDTO:
        report_row = await self._reports.get(command.report_id)
        if report_row is None:
            raise ExpenseReportNotFoundError(command.report_id)
        comment = command.comment.strip()
        if not comment:
            raise ExpenseReturnCommentRequiredError()
        self._ensure_not_self_review(report_row.user_id, command.reviewer_id)
        if report_row.status not in _REVIEWABLE_STATUSES:
            raise InvalidExpenseStatusTransitionError(report_row.id, report_row.status, "return")
        if report_row.locked_at is not None:
            raise ExpenseReportLockedError(report_row.id)

        report_row.status = ExpenseReportStatus.RETURNED
        report_row.reviewed_at = utc_now()
        report_row.reviewed_by_id = command.reviewer_id
        report_row.return_comment = comment
        await self._reports.save(report_row)

        project = await self._bus.query(GetProjectById(project_id=report_row.project_id))
        assert project is not None
        await self._bus.execute(
            RecordAuditEvent(
                actor_id=command.reviewer_id,
                action=AuditAction.EXPENSE_REPORT_RETURNED,
                entity_type="expense_report",
                entity_id=str(report_row.id),
                summary=(
                    f"Returned {project.customer.name} · {project.name} expense report "
                    f"({report_row.period_start:%Y-%m})"
                ),
                details={"comment": comment},
            )
        )

        return await self.get_report(report_id=report_row.id, viewer_id=command.reviewer_id)

    async def lock_project_month(self, command: LockProjectMonthExpenseReports) -> None:
        reports = await self._reports.list_for_project_period(
            project_id=command.project_id, period_start=command.period_start
        )
        now = utc_now()
        for report_row in reports:
            report_row.locked_at = now
            await self._reports.save(report_row)

    async def unlock_project_month(self, command: UnlockProjectMonthExpenseReports) -> None:
        reports = await self._reports.list_for_project_period(
            project_id=command.project_id, period_start=command.period_start
        )
        for report_row in reports:
            report_row.locked_at = None
            await self._reports.save(report_row)

    @staticmethod
    def _ensure_not_self_review(user_id: UUID, reviewer_id: UUID) -> None:
        if reviewer_id == user_id:
            raise ExpenseSelfReviewError()

    def _ensure_editable(self, report_row: ExpenseReport) -> None:
        if report_row.status not in _EDITABLE_STATUSES:
            raise ExpenseReportNotEditableError(report_row.id, report_row.status)
        # Reachable in principle even though today a locked report is always `approved` (and so
        # already rejected above): explicit rather than relying on that invariant holding forever.
        if report_row.locked_at is not None:
            raise ExpenseReportLockedError(report_row.id)

    async def _ensure_project_open(self, user_id: UUID, project_id: UUID) -> None:
        option = await self._matching_option(user_id, project_id)
        if option is None or not option.billing_items:
            raise ExpenseProjectClosedError(project_id)

    async def _open_items(
        self, user_id: UUID, project_id: UUID
    ) -> dict[UUID, ProjectBillingItemDTO]:
        option = await self._matching_option(user_id, project_id)
        if option is None:
            return {}
        return {item.id: item for item in option.billing_items}

    async def _matching_option(self, user_id: UUID, project_id: UUID) -> ProjectOptionDTO | None:
        options = await self._bus.query(
            ListMemberProjectsWithBillingItems(
                user_id=user_id, units=frozenset({BillingUnit.AMOUNT})
            )
        )
        return next((option for option in options if option.project.id == project_id), None)

    async def _reviewer_name(self, report_row: ExpenseReport) -> str | None:
        if report_row.reviewed_by_id is None:
            return None
        reviewer = await self._bus.query(GetUserById(user_id=report_row.reviewed_by_id))
        return reviewer.name if reviewer is not None else None


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    first = date(year, month, 1)
    last_day = monthrange(year, month)[1]
    return first, date(year, month, last_day)
