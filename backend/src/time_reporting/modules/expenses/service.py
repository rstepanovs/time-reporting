"""Expense report domain logic.

Changes are flushed through the repository; the bus commits. Reads projects and users only through
their modules' ``contracts.py`` messages, dispatched on the shared ``Bus``.
"""

import hashlib
from calendar import monthrange
from datetime import date
from decimal import Decimal
from uuid import UUID

from time_reporting.core.config import get_settings
from time_reporting.core.cqrs import Bus
from time_reporting.db.mixins import utc_now
from time_reporting.modules.audit.contracts import AuditAction, RecordAuditEvent
from time_reporting.modules.company.contracts import GetCompanySettings
from time_reporting.modules.expenses.contracts import (
    AddExpenseAttachment,
    ApproveExpenseReport,
    AttachmentFileDTO,
    AttachmentNotFoundError,
    CreateExpenseReport,
    DeleteExpenseAttachment,
    DeleteExpenseReport,
    ExpenseAttachmentDTO,
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
    GetAttachmentPath,
    InvalidExpenseStatusTransitionError,
    LockProjectMonthExpenseReports,
    ReturnExpenseReport,
    SaveExpenseReportLines,
    SubmitExpenseReport,
    UnlockProjectMonthExpenseReports,
)
from time_reporting.modules.expenses.models import (
    ExpenseAttachment,
    ExpenseReport,
    ExpenseReportLine,
)
from time_reporting.modules.expenses.repository import (
    ExpenseAttachmentRepository,
    ExpenseReportLineRepository,
    ExpenseReportRepository,
)
from time_reporting.modules.expenses.storage import ExpenseAttachmentStorage
from time_reporting.modules.projects.contracts import (
    BillingUnit,
    GetProjectBillingItemsByIds,
    GetProjectById,
    ListMemberProjectsWithBillingItems,
    ProjectBillingItemDTO,
    ProjectOptionDTO,
)
from time_reporting.modules.users.contracts import GetUserById, GetUsersByIds, UserDTO, UserRole

_EDITABLE_STATUSES = frozenset({ExpenseReportStatus.DRAFT, ExpenseReportStatus.RETURNED})
_REVIEWABLE_STATUSES = frozenset({ExpenseReportStatus.SUBMITTED, ExpenseReportStatus.APPROVED})


class ExpenseService:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._reports = ExpenseReportRepository(bus.session)
        self._lines = ExpenseReportLineRepository(bus.session)
        self._attachments = ExpenseAttachmentRepository(bus.session)
        self._storage = ExpenseAttachmentStorage(get_settings())

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
        # Read access is broader than write: the owner, any manager, or an accountant (who will
        # eventually consume sent-to-billing reports). Anyone else gets the same
        # ``ExpenseReportNotFoundError`` a truly unknown id would — information-hiding, like
        # ``RequireRole`` rendering ``NotFoundPage`` rather than revealing a route exists.
        if viewer_id != report_row.user_id and not _has_read_access(viewer):
            raise ExpenseReportNotFoundError(report_id)
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

        attachments = await self._attachments.list_for_report(report_id)
        uploaders_by_id = {
            uploader.id: uploader
            for uploader in await self._bus.query(
                GetUsersByIds(
                    user_ids=frozenset(
                        attachment.uploaded_by_id
                        for attachment in attachments
                        if attachment.uploaded_by_id is not None
                    )
                )
            )
        }
        attachment_dtos = tuple(
            ExpenseAttachmentDTO(
                id=attachment.id,
                file_name=attachment.file_name,
                content_type=attachment.content_type,
                size_bytes=attachment.size_bytes,
                uploaded_by_name=(
                    uploaders_by_id[attachment.uploaded_by_id].name
                    if attachment.uploaded_by_id in uploaders_by_id
                    else None
                ),
                created_at=attachment.created_at,
            )
            for attachment in attachments
        )

        reviewed_by_name = await self._reviewer_name(report_row)
        is_locked = report_row.locked_at is not None
        is_owner_editable = (
            viewer_id == report_row.user_id
            and report_row.status in _EDITABLE_STATUSES
            and not is_locked
        )
        self_review_allowed = False
        if viewer_id == report_row.user_id:
            settings = await self._bus.query(GetCompanySettings())
            self_review_allowed = settings.allow_self_review
        can_review = (
            viewer is not None
            and UserRole.MANAGER in viewer.roles
            and report_row.status in _REVIEWABLE_STATUSES
            and (viewer_id != report_row.user_id or self_review_allowed)
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
            attachments=attachment_dtos,
        )

    async def save_lines(self, command: SaveExpenseReportLines) -> ExpenseReportDTO:
        report_row = await self._get_own_report(command.report_id, command.actor_id)
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
        report_row = await self._get_own_report(command.report_id, command.actor_id)
        if report_row.status is not ExpenseReportStatus.DRAFT:
            raise ExpenseReportNotEditableError(report_row.id, report_row.status)
        await self._reports.delete(report_row)

    async def submit_report(self, command: SubmitExpenseReport) -> ExpenseReportDTO:
        report_row = await self._get_own_report(command.report_id, command.actor_id)
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
        await self._ensure_review_allowed(report_row.user_id, command.reviewer_id)
        if report_row.status is not ExpenseReportStatus.SUBMITTED:
            raise InvalidExpenseStatusTransitionError(report_row.id, report_row.status, "approve")

        is_self_review = report_row.user_id == command.reviewer_id
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
                details={"self_review": True} if is_self_review else None,
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
        await self._ensure_review_allowed(report_row.user_id, command.reviewer_id)
        if report_row.status not in _REVIEWABLE_STATUSES:
            raise InvalidExpenseStatusTransitionError(report_row.id, report_row.status, "return")
        if report_row.locked_at is not None:
            raise ExpenseReportLockedError(report_row.id)

        is_self_review = report_row.user_id == command.reviewer_id
        report_row.status = ExpenseReportStatus.RETURNED
        report_row.reviewed_at = utc_now()
        report_row.reviewed_by_id = command.reviewer_id
        report_row.return_comment = comment
        await self._reports.save(report_row)

        project = await self._bus.query(GetProjectById(project_id=report_row.project_id))
        assert project is not None
        details: dict[str, object] = {"comment": comment}
        if is_self_review:
            details["self_review"] = True
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
                details=details,
            )
        )

        return await self.get_report(report_id=report_row.id, viewer_id=command.reviewer_id)

    async def lock_project_month(self, command: LockProjectMonthExpenseReports) -> None:
        reports = await self._reports.list_for_projects_period(
            project_ids=frozenset({command.project_id}), period_start=command.period_start
        )
        now = utc_now()
        for report_row in reports:
            report_row.locked_at = now
            await self._reports.save(report_row)

    async def unlock_project_month(self, command: UnlockProjectMonthExpenseReports) -> None:
        reports = await self._reports.list_for_projects_period(
            project_ids=frozenset({command.project_id}), period_start=command.period_start
        )
        for report_row in reports:
            report_row.locked_at = None
            await self._reports.save(report_row)

    async def add_attachment(self, command: AddExpenseAttachment) -> ExpenseAttachmentDTO:
        report_row = await self._get_own_report(command.report_id, command.actor_id)
        self._ensure_editable(report_row)

        # Raised here too (not just inside `storage.save`) so a rejected upload never computes a
        # hash or touches the filesystem at all.
        self._storage.ensure_allowed(
            content_type=command.content_type, size_bytes=len(command.content)
        )
        sha256 = hashlib.sha256(command.content).hexdigest()
        storage_key = self._storage.save(content=command.content, content_type=command.content_type)

        attachment = ExpenseAttachment(
            report_id=report_row.id,
            file_name=command.file_name,
            content_type=command.content_type,
            size_bytes=len(command.content),
            sha256=sha256,
            storage_key=storage_key,
            uploaded_by_id=command.actor_id,
        )
        await self._attachments.save(attachment)

        uploader = await self._bus.query(GetUserById(user_id=command.actor_id))
        return ExpenseAttachmentDTO(
            id=attachment.id,
            file_name=attachment.file_name,
            content_type=attachment.content_type,
            size_bytes=attachment.size_bytes,
            uploaded_by_name=uploader.name if uploader is not None else None,
            created_at=attachment.created_at,
        )

    async def delete_attachment(self, command: DeleteExpenseAttachment) -> None:
        attachment = await self._attachments.get(command.attachment_id)
        if attachment is None:
            raise AttachmentNotFoundError(command.attachment_id)
        report_row = await self._reports.get(attachment.report_id)
        # `expense_attachments.report_id` is `ON DELETE CASCADE`, so the report row can only be
        # missing if this attachment row is also gone by the time we get here.
        assert report_row is not None
        if report_row.user_id != command.actor_id:
            raise AttachmentNotFoundError(command.attachment_id)
        self._ensure_editable(report_row)

        self._storage.delete(attachment.storage_key)
        await self._attachments.delete(attachment)

    async def get_attachment_path(self, query: GetAttachmentPath) -> AttachmentFileDTO:
        """Raises ``AttachmentNotFoundError`` for an unknown id, a file missing from disk, *or* a
        viewer who is neither the report's owner nor a manager/accountant — the attachment has no
        HTTP route of its own to check that in the router, so the read-access check that
        ``get_report`` does lives here too, via ``_has_read_access``."""
        attachment = await self._attachments.get(query.attachment_id)
        if attachment is None:
            raise AttachmentNotFoundError(query.attachment_id)
        report_row = await self._reports.get(attachment.report_id)
        assert report_row is not None
        if report_row.user_id != query.viewer_id:
            viewer = await self._bus.query(GetUserById(user_id=query.viewer_id))
            if not _has_read_access(viewer):
                raise AttachmentNotFoundError(query.attachment_id)
        path = self._storage.path_for(attachment.storage_key)
        if path is None:
            raise AttachmentNotFoundError(query.attachment_id)
        return AttachmentFileDTO(
            path=path, file_name=attachment.file_name, content_type=attachment.content_type
        )

    async def _ensure_review_allowed(self, user_id: UUID, reviewer_id: UUID) -> None:
        """Nobody reviews their own report — unless ``company.allow_self_review`` is on and the
        reviewer holds ``manager`` (the router's ``ManagerDep`` normally guarantees the latter, but
        this is checked here too since a self-review is otherwise indistinguishable from a regular
        one at this point)."""
        if reviewer_id != user_id:
            return
        settings = await self._bus.query(GetCompanySettings())
        if not settings.allow_self_review:
            raise ExpenseSelfReviewError()
        reviewer = await self._bus.query(GetUserById(user_id=reviewer_id))
        if reviewer is None or UserRole.MANAGER not in reviewer.roles:
            raise ExpenseSelfReviewError()

    async def _get_own_report(self, report_id: UUID, actor_id: UUID) -> ExpenseReport:
        """Fetch a report the caller must own. A report belonging to someone else raises the same
        ``ExpenseReportNotFoundError`` a truly unknown id would — this module's writes are
        addressed by an opaque ``report_id`` rather than a key that already includes the owner
        (contrast ``timesheets``, keyed by ``(user_id, week_start)``), so this check has to live
        here rather than in the router, which has no other way to learn the owner first."""
        report_row = await self._reports.get(report_id)
        if report_row is None or report_row.user_id != actor_id:
            raise ExpenseReportNotFoundError(report_id)
        return report_row

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


def _has_read_access(viewer: UserDTO | None) -> bool:
    """Whether ``viewer`` may read a report/attachment they don't own: a manager (to approve/
    return it) or an accountant (who will eventually consume sent-to-billing reports)."""
    return viewer is not None and bool(viewer.roles & {UserRole.MANAGER, UserRole.ACCOUNTANT})
