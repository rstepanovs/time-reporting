"""Registers the expenses module's handlers on the bus."""

from time_reporting.core.cqrs import HandlerRegistry
from time_reporting.modules.expenses.contracts import (
    ApproveExpenseReport,
    CreateExpenseReport,
    DeleteExpenseReport,
    GetExpenseReport,
    ListProjectMonthExpenseReports,
    ListSubmittedExpenseReports,
    LockProjectMonthExpenseReports,
    ReturnExpenseReport,
    SaveExpenseReportLines,
    SubmitExpenseReport,
    UnlockProjectMonthExpenseReports,
)
from time_reporting.modules.expenses.handlers import (
    ApproveExpenseReportHandler,
    CreateExpenseReportHandler,
    DeleteExpenseReportHandler,
    GetExpenseReportHandler,
    ListProjectMonthExpenseReportsHandler,
    ListSubmittedExpenseReportsHandler,
    LockProjectMonthExpenseReportsHandler,
    ReturnExpenseReportHandler,
    SaveExpenseReportLinesHandler,
    SubmitExpenseReportHandler,
    UnlockProjectMonthExpenseReportsHandler,
)


def register(registry: HandlerRegistry) -> None:
    registry.query(GetExpenseReport, GetExpenseReportHandler)
    registry.query(ListSubmittedExpenseReports, ListSubmittedExpenseReportsHandler)
    registry.query(ListProjectMonthExpenseReports, ListProjectMonthExpenseReportsHandler)

    registry.command(CreateExpenseReport, CreateExpenseReportHandler)
    registry.command(SaveExpenseReportLines, SaveExpenseReportLinesHandler)
    registry.command(DeleteExpenseReport, DeleteExpenseReportHandler)
    registry.command(SubmitExpenseReport, SubmitExpenseReportHandler)
    registry.command(ApproveExpenseReport, ApproveExpenseReportHandler)
    registry.command(ReturnExpenseReport, ReturnExpenseReportHandler)
    registry.command(LockProjectMonthExpenseReports, LockProjectMonthExpenseReportsHandler)
    registry.command(UnlockProjectMonthExpenseReports, UnlockProjectMonthExpenseReportsHandler)
