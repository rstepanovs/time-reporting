"""Command and query handlers of the expenses module (registered in ``expenses.module``).

Handlers translate between bus messages and the service/repository and never return ORM entities.
"""

from collections.abc import Sequence
from decimal import Decimal

from time_reporting.core.cqrs import Bus
from time_reporting.modules.expenses.contracts import (
    AddExpenseAttachment,
    ApproveExpenseReport,
    AttachmentFileDTO,
    CreateExpenseReport,
    DeleteExpenseAttachment,
    DeleteExpenseReport,
    ExpenseAttachmentDTO,
    ExpenseReportDTO,
    ExpenseReportStatus,
    ExpenseReportSummaryDTO,
    GetAttachmentPath,
    GetExpenseReport,
    ListAttachmentStorageKeys,
    ListExpenseOptions,
    ListMyExpenseReports,
    ListProjectMonthExpenseReports,
    ListSubmittedExpenseReports,
    LockProjectMonthExpenseReports,
    ReturnExpenseReport,
    SaveExpenseReportLines,
    SubmitExpenseReport,
    UnlockProjectMonthExpenseReports,
)
from time_reporting.modules.expenses.models import ExpenseReport
from time_reporting.modules.expenses.repository import (
    ExpenseAttachmentRepository,
    ExpenseReportLineRepository,
    ExpenseReportRepository,
)
from time_reporting.modules.expenses.service import ExpenseService, _month_bounds
from time_reporting.modules.projects.contracts import (
    BillingUnit,
    GetProjectsByIds,
    ListManagedProjectsWithMembers,
    ListMemberProjectsWithBillingItems,
    ProjectOptionDTO,
)
from time_reporting.modules.users.contracts import GetUsersByIds


class CreateExpenseReportHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = ExpenseService(bus)

    async def handle(self, command: CreateExpenseReport) -> ExpenseReportDTO:
        return await self._service.create_report(command)


class GetExpenseReportHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = ExpenseService(bus)

    async def handle(self, query: GetExpenseReport) -> ExpenseReportDTO:
        return await self._service.get_report(report_id=query.report_id, viewer_id=query.viewer_id)


class SaveExpenseReportLinesHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = ExpenseService(bus)

    async def handle(self, command: SaveExpenseReportLines) -> ExpenseReportDTO:
        return await self._service.save_lines(command)


class DeleteExpenseReportHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = ExpenseService(bus)

    async def handle(self, command: DeleteExpenseReport) -> None:
        await self._service.delete_report(command)


class SubmitExpenseReportHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = ExpenseService(bus)

    async def handle(self, command: SubmitExpenseReport) -> ExpenseReportDTO:
        return await self._service.submit_report(command)


class ApproveExpenseReportHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = ExpenseService(bus)

    async def handle(self, command: ApproveExpenseReport) -> ExpenseReportDTO:
        return await self._service.approve_report(command)


class ReturnExpenseReportHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = ExpenseService(bus)

    async def handle(self, command: ReturnExpenseReport) -> ExpenseReportDTO:
        return await self._service.return_report(command)


class LockProjectMonthExpenseReportsHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = ExpenseService(bus)

    async def handle(self, command: LockProjectMonthExpenseReports) -> None:
        await self._service.lock_project_month(command)


class UnlockProjectMonthExpenseReportsHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = ExpenseService(bus)

    async def handle(self, command: UnlockProjectMonthExpenseReports) -> None:
        await self._service.unlock_project_month(command)


class AddExpenseAttachmentHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = ExpenseService(bus)

    async def handle(self, command: AddExpenseAttachment) -> ExpenseAttachmentDTO:
        return await self._service.add_attachment(command)


class DeleteExpenseAttachmentHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = ExpenseService(bus)

    async def handle(self, command: DeleteExpenseAttachment) -> None:
        await self._service.delete_attachment(command)


class GetAttachmentPathHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = ExpenseService(bus)

    async def handle(self, query: GetAttachmentPath) -> AttachmentFileDTO:
        return await self._service.get_attachment_path(query)


class ListMyExpenseReportsHandler:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._reports = ExpenseReportRepository(bus.session)
        self._lines = ExpenseReportLineRepository(bus.session)

    async def handle(self, query: ListMyExpenseReports) -> tuple[ExpenseReportSummaryDTO, ...]:
        period_start, _period_end = _month_bounds(query.year, query.month)
        report_rows = await self._reports.list_for_user_period(
            user_id=query.user_id, period_start=period_start
        )
        return await _summaries(self._bus, self._lines, report_rows)


class ListExpenseOptionsHandler:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus

    async def handle(self, query: ListExpenseOptions) -> tuple[ProjectOptionDTO, ...]:
        return await self._bus.query(
            ListMemberProjectsWithBillingItems(
                user_id=query.user_id, units=frozenset({BillingUnit.AMOUNT})
            )
        )


class ListAttachmentStorageKeysHandler:
    def __init__(self, bus: Bus) -> None:
        self._attachments = ExpenseAttachmentRepository(bus.session)

    async def handle(self, query: ListAttachmentStorageKeys) -> frozenset[str]:
        return await self._attachments.list_all_storage_keys()


class ListSubmittedExpenseReportsHandler:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._reports = ExpenseReportRepository(bus.session)
        self._lines = ExpenseReportLineRepository(bus.session)

    async def handle(
        self, query: ListSubmittedExpenseReports
    ) -> tuple[ExpenseReportSummaryDTO, ...]:
        report_rows = await self._reports.list_by_status(ExpenseReportStatus.SUBMITTED)
        if query.manager_id is not None:
            managed = await self._bus.query(
                ListManagedProjectsWithMembers(manager_id=query.manager_id)
            )
            managed_project_ids = frozenset(entry.project.id for entry in managed)
            report_rows = [row for row in report_rows if row.project_id in managed_project_ids]
        return await _summaries(self._bus, self._lines, report_rows)


class ListProjectMonthExpenseReportsHandler:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._reports = ExpenseReportRepository(bus.session)
        self._lines = ExpenseReportLineRepository(bus.session)

    async def handle(
        self, query: ListProjectMonthExpenseReports
    ) -> tuple[ExpenseReportSummaryDTO, ...]:
        report_rows = await self._reports.list_for_project_period(
            project_id=query.project_id, period_start=query.period_start
        )
        return await _summaries(self._bus, self._lines, report_rows)


async def _summaries(
    bus: Bus, lines: ExpenseReportLineRepository, report_rows: Sequence[ExpenseReport]
) -> tuple[ExpenseReportSummaryDTO, ...]:
    if not report_rows:
        return ()
    project_ids = frozenset(row.project_id for row in report_rows)
    user_ids = frozenset(row.user_id for row in report_rows)
    projects = await bus.query(GetProjectsByIds(project_ids=project_ids))
    projects_by_id = {project.id: project for project in projects}
    users_by_id = {user.id: user for user in await bus.query(GetUsersByIds(user_ids=user_ids))}
    totals = await lines.sum_and_count_by_report(frozenset(row.id for row in report_rows))

    summaries: list[ExpenseReportSummaryDTO] = []
    for row in report_rows:
        project = projects_by_id.get(row.project_id)
        user = users_by_id.get(row.user_id)
        if project is None or user is None:
            continue
        total, line_count = totals.get(row.id, (Decimal("0"), 0))
        summaries.append(
            ExpenseReportSummaryDTO(
                id=row.id,
                project=project,
                user=user,
                period_start=row.period_start,
                period_end=row.period_end,
                status=row.status,
                submitted_at=row.submitted_at,
                total=total,
                line_count=line_count,
            )
        )
    return tuple(summaries)
