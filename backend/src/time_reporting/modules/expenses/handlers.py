"""Command and query handlers of the expenses module (registered in ``expenses.module``).

Handlers translate between bus messages and the service and never return ORM entities.
"""

from time_reporting.core.cqrs import Bus
from time_reporting.modules.expenses.contracts import (
    CreateExpenseReport,
    DeleteExpenseReport,
    ExpenseReportDTO,
    GetExpenseReport,
    SaveExpenseReportLines,
)
from time_reporting.modules.expenses.service import ExpenseService


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
