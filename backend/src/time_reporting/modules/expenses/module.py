"""Registers the expenses module's handlers on the bus."""

from time_reporting.core.cqrs import HandlerRegistry
from time_reporting.modules.expenses.contracts import (
    CreateExpenseReport,
    DeleteExpenseReport,
    GetExpenseReport,
    SaveExpenseReportLines,
)
from time_reporting.modules.expenses.handlers import (
    CreateExpenseReportHandler,
    DeleteExpenseReportHandler,
    GetExpenseReportHandler,
    SaveExpenseReportLinesHandler,
)


def register(registry: HandlerRegistry) -> None:
    registry.query(GetExpenseReport, GetExpenseReportHandler)

    registry.command(CreateExpenseReport, CreateExpenseReportHandler)
    registry.command(SaveExpenseReportLines, SaveExpenseReportLinesHandler)
    registry.command(DeleteExpenseReport, DeleteExpenseReportHandler)
