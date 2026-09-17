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
    ListAttachmentStorageKeys,
    ListProjectMonthExpenseReports,
    ListSubmittedExpenseReports,
    LockProjectMonthExpenseReports,
    ReturnExpenseReport,
    SaveExpenseReportLines,
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
    ListAttachmentStorageKeysHandler,
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
