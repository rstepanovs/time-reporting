"""Public contract of the expenses module.

Other modules may import only this file: DTOs, commands, queries and domain exceptions. Handlers
for these messages are registered in ``expenses.module``; ORM entities never leave the module.

Depends on ``projects.contracts`` (``ListMemberProjectsWithBillingItems`` with
``units={BillingUnit.AMOUNT}`` — the same membership check timesheets uses, narrowed to expense
billing items), ``users.contracts`` and ``audit.contracts``. Never depends on
``timesheets.contracts`` — the dependency runs the other way: a nested
``timesheets.SendProjectMonthToBilling`` executes ``LockProjectMonthExpenseReports`` so the lock is
written in the same transaction as the billing handoff, without this module ever reading
``ProjectBillingPeriod``.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from uuid import UUID

from time_reporting.core.cqrs import Command, Query
from time_reporting.modules.projects.contracts import (
    ProjectBillingItemDTO,
    ProjectDTO,
    ProjectOptionDTO,
)
from time_reporting.modules.users.contracts import UserDTO

# What an uploaded receipt/invoice scan may be. A frozenset constant, not a setting, since it's a
# format decision, not something an operator would tune per deployment.
ALLOWED_ATTACHMENT_CONTENT_TYPES: frozenset[str] = frozenset(
    {"application/pdf", "image/jpeg", "image/png", "image/webp", "image/heic"}
)


class ExpenseReportStatus(StrEnum):
    """A report's place in the submit/review workflow.

    Unlike ``timesheets.TimesheetWeekStatus``, ``DRAFT`` *is* persisted: the document (and its
    lines and attachments) must exist before it has anything to submit, so there is no "no row
    means draft" shortcut here.
    """

    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    RETURNED = "returned"


# --- DTOs ---


@dataclass(frozen=True, slots=True, kw_only=True)
class ExpenseReportLineDTO:
    id: UUID
    expense_date: date
    billing_item: ProjectBillingItemDTO
    amount: Decimal
    description: str
    vendor: str | None
    document_no: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ExpenseAttachmentDTO:
    id: UUID
    file_name: str
    content_type: str
    size_bytes: int
    uploaded_by_name: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class ExpenseReportDTO:
    """One employee's expense claim for one project and one calendar month.

    ``can_edit``/``can_submit``/``can_review`` are advisory, computed for the caller to render
    around — as with ``timesheets.TimesheetWeekDTO``, the router still owns authorization.
    ``is_locked`` mirrors ``locked_at is not None`` (the report's project-month was sent to
    billing); ``total`` is the sum of ``lines``' amounts, in the project's customer's currency.
    """

    id: UUID
    project: ProjectDTO
    user: UserDTO
    period_start: date
    period_end: date
    status: ExpenseReportStatus
    submitted_at: datetime | None
    reviewed_at: datetime | None
    reviewed_by_name: str | None
    return_comment: str | None
    locked_at: datetime | None
    can_edit: bool
    can_submit: bool
    can_review: bool
    is_locked: bool
    total: Decimal
    lines: tuple[ExpenseReportLineDTO, ...]
    attachments: tuple[ExpenseAttachmentDTO, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class ExpenseReportSummaryDTO:
    """A report's row in a list view (``ListSubmittedExpenseReports``,
    ``ListProjectMonthExpenseReports``) — without its lines, for a lighter payload."""

    id: UUID
    project: ProjectDTO
    user: UserDTO
    period_start: date
    period_end: date
    status: ExpenseReportStatus
    submitted_at: datetime | None
    total: Decimal
    line_count: int


# --- Queries ---


@dataclass(frozen=True, slots=True, kw_only=True)
class GetExpenseReport(Query[ExpenseReportDTO]):
    """Raises ``ExpenseReportNotFoundError`` if ``report_id`` doesn't exist."""

    report_id: UUID
    viewer_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ListMyExpenseReports(Query[tuple[ExpenseReportSummaryDTO, ...]]):
    """``user_id``'s reports whose ``period_start`` falls in ``year``/``month`` (there can be more
    than one — one per project)."""

    user_id: UUID
    year: int
    month: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ListExpenseOptions(Query[tuple[ProjectOptionDTO, ...]]):
    """The projects/``amount`` billing items ``user_id`` may currently claim expenses against;
    used to build the "new report" project picker. Same shape as
    ``projects.contracts.ListMemberProjectsWithBillingItems``, exposed here so the HTTP layer only
    ever dispatches messages owned by this module — mirrors ``timesheets.ListTimesheetOptions``."""

    user_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ListSubmittedExpenseReports(Query[tuple[ExpenseReportSummaryDTO, ...]]):
    """Reports awaiting review, oldest submission first, for a manager's approvals list.
    ``manager_id=None`` covers every project; otherwise only reports on a project that manager
    manages — mirrors ``timesheets.ListSubmittedTimesheetWeeks``."""

    manager_id: UUID | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ListProjectMonthExpenseReports(Query[tuple[ExpenseReportSummaryDTO, ...]]):
    """Every report (any status, any user) for any of ``project_ids`` at ``period_start`` — a
    batch query so ``timesheets``' team overview (many managed projects at once) doesn't do one
    round trip per project; ``billing.py`` calls it with a single-project frozenset. Also backs
    ``LockProjectMonthExpenseReports``/``UnlockProjectMonthExpenseReports`` and, from
    ``timesheets``, billing readiness and totals — the one place the dependency between the two
    modules runs ``timesheets`` → ``expenses``."""

    project_ids: frozenset[UUID]
    period_start: date


@dataclass(frozen=True, slots=True, kw_only=True)
class ExpenseReportLineExportDTO:
    """One line of an *approved* report plus its owner, for ``timesheets``' billing-period CSV
    export — the one place outside this module that needs line-level detail rather than
    ``ExpenseReportSummaryDTO``'s per-report total."""

    user: UserDTO
    expense_date: date
    billing_item: ProjectBillingItemDTO
    amount: Decimal
    description: str
    vendor: str | None
    document_no: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ListProjectMonthExpenseReportLines(Query[tuple[ExpenseReportLineExportDTO, ...]]):
    """Every line of every *approved* report for ``project_id`` at ``period_start`` — a report not
    yet approved contributed nothing to the period's expense total and is excluded, mirroring
    ``billing.py``'s own summing of only-approved reports."""

    project_id: UUID
    period_start: date


@dataclass(frozen=True, slots=True, kw_only=True)
class ExpenseCurrencyTotalDTO:
    currency: str
    amount: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class GetMonthExpenseTotals(Query[tuple[ExpenseCurrencyTotalDTO, ...]]):
    """``user_id``'s total claimed amount per currency across *all* their reports (any status) for
    ``year``/``month`` — one report can only ever hold one currency (its project's), but a user can
    have several reports (different projects, possibly different currencies) in the same month.
    Every status counts, not just ``approved``: mirrors the pre-expenses-module behavior where an
    entered amount showed up in the employee dashboard's running total immediately, before any
    workflow existed. Used by ``timesheets.contracts.MonthTimeSummaryDTO.expenses``."""

    user_id: UUID
    year: int
    month: int


@dataclass(frozen=True, slots=True, kw_only=True)
class AttachmentFileDTO:
    """Enough for the router to stream an attachment back as a ``FileResponse``. Unlike
    ``system.contracts.GetBackupPath`` (whose generated file name already doubles as its own
    display name and content type), an attachment's ``storage_key`` carries neither, so this DTO
    wraps the path with the original upload's metadata."""

    path: Path
    file_name: str
    content_type: str


@dataclass(frozen=True, slots=True, kw_only=True)
class GetAttachmentPath(Query[AttachmentFileDTO]):
    """Raises ``AttachmentNotFoundError`` if ``attachment_id`` doesn't exist, its file is missing
    from disk, or ``viewer_id`` may not read it (see ``ExpenseService.get_attachment_path``)."""

    attachment_id: UUID
    viewer_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ListAttachmentStorageKeys(Query[frozenset[str]]):
    """Every attachment's ``storage_key``, for ``time-reporting prune-attachments`` to tell which
    files on disk are still referenced by a row."""


# --- Commands ---


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateExpenseReport(Command[ExpenseReportDTO]):
    """Create an empty draft report for ``user_id`` on ``project_id``'s ``year``/``month``.

    Raises ``ExpenseProjectClosedError`` (the project doesn't exist, isn't active, the user isn't
    currently a member, or the project has no active ``amount`` billing item to claim against) or
    ``ExpenseReportAlreadyExistsError`` (one already exists for this user/project/month).
    """

    user_id: UUID
    project_id: UUID
    year: int
    month: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ExpenseLineChange:
    """One line's new value. ``line_id=None`` creates a line; given, it updates that line (the
    service resolves it against the report, raising ``ExpenseLineNotFoundError`` if it doesn't
    belong to the report)."""

    line_id: UUID | None
    billing_item_id: UUID
    expense_date: date
    amount: Decimal
    description: str
    vendor: str | None = None
    document_no: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class SaveExpenseReportLines(Command[ExpenseReportDTO]):
    """Apply ``lines`` (creates and updates) and ``delete_line_ids`` to ``report_id`` in one batch
    and return the updated report.

    Every change is validated before any is applied, so a rejected batch leaves the report
    unchanged (the bus also rolls back the whole command on any exception). Raises
    ``ExpenseReportNotFoundError``, ``ExpenseReportNotEditableError`` (the report isn't draft or
    returned), ``ExpenseReportLockedError`` (its project-month was sent to billing),
    ``ExpenseLineNotFoundError``, ``ExpenseBillingItemNotFoundError`` or
    ``ExpenseDateOutsidePeriodError``. A ``line_id`` present in both ``lines`` and
    ``delete_line_ids`` is deleted (the delete wins); a ``line_id`` in ``delete_line_ids`` that
    doesn't belong to the report is a no-op.
    """

    report_id: UUID
    actor_id: UUID
    lines: tuple[ExpenseLineChange, ...]
    delete_line_ids: frozenset[UUID] = frozenset()


@dataclass(frozen=True, slots=True, kw_only=True)
class DeleteExpenseReport(Command[None]):
    """Permanently delete a draft report (and its lines/attachments, by cascade). Raises
    ``ExpenseReportNotFoundError`` or ``ExpenseReportNotEditableError`` (not a draft)."""

    report_id: UUID
    actor_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class SubmitExpenseReport(Command[ExpenseReportDTO]):
    """Move the report from draft/returned to submitted. Raises ``ExpenseReportNotFoundError`` or
    ``InvalidExpenseStatusTransitionError``."""

    report_id: UUID
    actor_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ApproveExpenseReport(Command[ExpenseReportDTO]):
    """Move the report from submitted to approved. Raises ``ExpenseReportNotFoundError``,
    ``InvalidExpenseStatusTransitionError`` or ``ExpenseSelfReviewError`` (nobody, not even an
    admin, reviews their own report)."""

    report_id: UUID
    reviewer_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ReturnExpenseReport(Command[ExpenseReportDTO]):
    """Move the report from submitted/approved back to returned, with an explanatory ``comment``.
    Raises ``ExpenseReportNotFoundError``, ``InvalidExpenseStatusTransitionError``,
    ``ExpenseSelfReviewError``, ``ExpenseReturnCommentRequiredError`` or
    ``ExpenseReportLockedError`` (its project-month was already sent to billing — un-approving
    hours already handed off is refused, mirroring ``timesheets.ReturnTimesheetWeek``)."""

    report_id: UUID
    reviewer_id: UUID
    comment: str


@dataclass(frozen=True, slots=True, kw_only=True)
class LockProjectMonthExpenseReports(Command[None]):
    """Set ``locked_at`` on every report of ``project_id``'s ``period_start``. Nested-only: executed
    from ``timesheets.SendProjectMonthToBilling``, never called directly from a router — this
    module has no HTTP route for it."""

    project_id: UUID
    period_start: date


@dataclass(frozen=True, slots=True, kw_only=True)
class UnlockProjectMonthExpenseReports(Command[None]):
    """Clear ``locked_at`` on every report of ``project_id``'s ``period_start``. Nested-only:
    executed from ``timesheets.ReopenProjectBillingPeriod``."""

    project_id: UUID
    period_start: date


@dataclass(frozen=True, slots=True, kw_only=True)
class AddExpenseAttachment(Command[ExpenseAttachmentDTO]):
    """Store one uploaded file against ``report_id``. ``content`` is the already-read request
    body — the router is responsible for enforcing ``attachment_max_bytes`` while reading it, so a
    huge upload is rejected without ever being buffered here in full. Raises
    ``ExpenseReportNotFoundError``, ``ExpenseReportNotEditableError``, ``ExpenseReportLockedError``,
    ``AttachmentTypeNotAllowedError`` or ``AttachmentTooLargeError``."""

    report_id: UUID
    actor_id: UUID
    file_name: str
    content_type: str
    content: bytes


@dataclass(frozen=True, slots=True, kw_only=True)
class DeleteExpenseAttachment(Command[None]):
    """Remove one attachment (its row and its file). Raises ``AttachmentNotFoundError``,
    ``ExpenseReportNotEditableError`` or ``ExpenseReportLockedError``."""

    attachment_id: UUID
    actor_id: UUID


# --- Exceptions ---


class ExpenseError(Exception):
    """Base class for expenses module domain errors."""


class ExpenseReportNotFoundError(ExpenseError):
    def __init__(self, report_id: UUID) -> None:
        super().__init__(f"Expense report {report_id} not found")
        self.report_id = report_id


class ExpenseLineNotFoundError(ExpenseError):
    """Raised by ``SaveExpenseReportLines`` when a change names a ``line_id`` that isn't one of
    the report's own lines."""

    def __init__(self, line_id: UUID) -> None:
        super().__init__(f"Expense line {line_id} not found on this report")
        self.line_id = line_id


class ExpenseReportAlreadyExistsError(ExpenseError):
    def __init__(self, user_id: UUID, project_id: UUID, period_start: date) -> None:
        super().__init__(
            f"User {user_id} already has a report for project {project_id} starting {period_start}"
        )
        self.user_id = user_id
        self.project_id = project_id
        self.period_start = period_start


class ExpenseReportNotEditableError(ExpenseError):
    """Raised when a change is attempted on a report that isn't draft/returned (edit) or isn't
    draft (delete)."""

    def __init__(self, report_id: UUID, status: ExpenseReportStatus) -> None:
        super().__init__(f"Expense report {report_id} is {status} and cannot be changed")
        self.report_id = report_id
        self.status = status


class ExpenseReportLockedError(ExpenseError):
    """Raised when a report's project-month was already sent to billing."""

    def __init__(self, report_id: UUID) -> None:
        super().__init__(f"Expense report {report_id} is locked: already sent to billing")
        self.report_id = report_id


class InvalidExpenseStatusTransitionError(ExpenseError):
    def __init__(self, report_id: UUID, status: ExpenseReportStatus, action: str) -> None:
        super().__init__(f"Cannot {action} expense report {report_id}: it is {status}")
        self.report_id = report_id
        self.status = status
        self.action = action


class ExpenseSelfReviewError(ExpenseError):
    def __init__(self) -> None:
        super().__init__("Cannot approve or return your own expense report")


class ExpenseReturnCommentRequiredError(ExpenseError):
    def __init__(self) -> None:
        super().__init__("Returning an expense report requires a non-empty comment")


class ExpenseProjectClosedError(ExpenseError):
    """Raised by ``CreateExpenseReport`` when the project doesn't exist, isn't active, or the user
    isn't currently a member of it (or it has no active ``amount`` billing item)."""

    def __init__(self, project_id: UUID) -> None:
        super().__init__(f"Project {project_id} is not open for expense reports for this user")
        self.project_id = project_id


class ExpenseBillingItemNotFoundError(ExpenseError):
    """Raised when a line's billing item isn't one of the report's project's active ``amount``
    items (unknown id, wrong project, wrong unit, or archived)."""

    def __init__(self, billing_item_id: UUID) -> None:
        super().__init__(f"Billing item {billing_item_id} is not open for this expense report")
        self.billing_item_id = billing_item_id


class ExpenseDateOutsidePeriodError(ExpenseError):
    def __init__(self, expense_date: date, period_start: date, period_end: date) -> None:
        super().__init__(
            f"{expense_date} is outside the report's period {period_start} - {period_end}"
        )
        self.expense_date = expense_date
        self.period_start = period_start
        self.period_end = period_end


class AttachmentNotFoundError(ExpenseError):
    def __init__(self, attachment_id: UUID) -> None:
        super().__init__(f"Attachment {attachment_id} not found")
        self.attachment_id = attachment_id


class AttachmentTooLargeError(ExpenseError):
    def __init__(self, size_bytes: int, max_bytes: int) -> None:
        super().__init__(f"Attachment is {size_bytes} bytes, more than the {max_bytes} byte limit")
        self.size_bytes = size_bytes
        self.max_bytes = max_bytes


class AttachmentTypeNotAllowedError(ExpenseError):
    def __init__(self, content_type: str) -> None:
        super().__init__(f"Attachment type {content_type!r} is not allowed")
        self.content_type = content_type
