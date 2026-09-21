"""Registers the expenses module's handlers on the bus."""

from time_reporting.core.cqrs import HandlerRegistry
from time_reporting.modules.expenses.contracts import (
    AddExpenseAttachment,
    ApproveExpenseReport,
    CreateExpenseReport,
    DeleteExpenseAttachment,
    DeleteExpenseReport,
    GetAttachmentPath,
    GetExpenseReport,
    GetMonthExpenseTotals,
    ListAttachmentStorageKeys,
    ListExpenseOptions,
    ListMyExpenseReports,
    ListProjectMonthExpenseReportLines,
    ListProjectMonthExpenseReports,
    ListSubmittedExpenseReports,
    LockProjectMonthExpenseReports,
    ReturnExpenseReport,
    SaveExpenseReportLines,
    SetAttachmentLine,
    SubmitExpenseReport,
    UnlockProjectMonthExpenseReports,
)
from time_reporting.modules.expenses.handlers import (
    AddExpenseAttachmentHandler,
    ApproveExpenseReportHandler,
    CreateExpenseReportHandler,
    DeleteExpenseAttachmentHandler,
    DeleteExpenseReportHandler,
    GetAttachmentPathHandler,
    GetExpenseReportHandler,
    GetMonthExpenseTotalsHandler,
    ListAttachmentStorageKeysHandler,
    ListExpenseOptionsHandler,
    ListMyExpenseReportsHandler,
    ListProjectMonthExpenseReportLinesHandler,
    ListProjectMonthExpenseReportsHandler,
    ListSubmittedExpenseReportsHandler,
    LockProjectMonthExpenseReportsHandler,
    ReturnExpenseReportHandler,
    SaveExpenseReportLinesHandler,
    SetAttachmentLineHandler,
    SubmitExpenseReportHandler,
    UnlockProjectMonthExpenseReportsHandler,
)


def register(registry: HandlerRegistry) -> None:
    registry.query(GetExpenseReport, GetExpenseReportHandler)
    registry.query(GetMonthExpenseTotals, GetMonthExpenseTotalsHandler)
    registry.query(ListMyExpenseReports, ListMyExpenseReportsHandler)
    registry.query(ListExpenseOptions, ListExpenseOptionsHandler)
    registry.query(ListSubmittedExpenseReports, ListSubmittedExpenseReportsHandler)
    registry.query(ListProjectMonthExpenseReports, ListProjectMonthExpenseReportsHandler)
    registry.query(ListProjectMonthExpenseReportLines, ListProjectMonthExpenseReportLinesHandler)
    registry.query(GetAttachmentPath, GetAttachmentPathHandler)
    registry.query(ListAttachmentStorageKeys, ListAttachmentStorageKeysHandler)

    registry.command(CreateExpenseReport, CreateExpenseReportHandler)
    registry.command(SaveExpenseReportLines, SaveExpenseReportLinesHandler)
    registry.command(DeleteExpenseReport, DeleteExpenseReportHandler)
    registry.command(SubmitExpenseReport, SubmitExpenseReportHandler)
    registry.command(ApproveExpenseReport, ApproveExpenseReportHandler)
    registry.command(ReturnExpenseReport, ReturnExpenseReportHandler)
    registry.command(LockProjectMonthExpenseReports, LockProjectMonthExpenseReportsHandler)
    registry.command(UnlockProjectMonthExpenseReports, UnlockProjectMonthExpenseReportsHandler)
    registry.command(AddExpenseAttachment, AddExpenseAttachmentHandler)
    registry.command(DeleteExpenseAttachment, DeleteExpenseAttachmentHandler)
    registry.command(SetAttachmentLine, SetAttachmentLineHandler)
