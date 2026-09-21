"""Expenses HTTP API.

An employee reads and writes their own reports; a manager or accountant may also read (but not
write) another user's. Managers additionally approve/return any report.
"""

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse

from time_reporting.api.deps import BusDep
from time_reporting.modules.auth.dependencies import CurrentUserDep, ManagerDep
from time_reporting.modules.expenses.contracts import (
    ALLOWED_ATTACHMENT_CONTENT_TYPES,
    AddExpenseAttachment,
    ApproveExpenseReport,
    AttachmentNotFoundError,
    AttachmentTooLargeError,
    AttachmentTypeNotAllowedError,
    CreateExpenseReport,
    DeleteExpenseAttachment,
    DeleteExpenseReport,
    ExpenseBillingItemNotFoundError,
    ExpenseDateOutsidePeriodError,
    ExpenseLineChange,
    ExpenseLineNotFoundError,
    ExpenseProjectClosedError,
    ExpenseReportAlreadyExistsError,
    ExpenseReportLockedError,
    ExpenseReportNotEditableError,
    ExpenseReportNotFoundError,
    ExpenseReturnCommentRequiredError,
    ExpenseSelfReviewError,
    GetAttachmentPath,
    GetExpenseReport,
    InvalidExpenseStatusTransitionError,
    ListExpenseOptions,
    ListMyExpenseReports,
    ListSubmittedExpenseReports,
    ReturnExpenseReport,
    SaveExpenseReportLines,
    SetAttachmentLine,
    SubmitExpenseReport,
)
from time_reporting.modules.expenses.schemas import (
    CreateExpenseReportRequest,
    ExpenseAttachmentResponse,
    ExpenseOptionResponse,
    ExpenseReportResponse,
    ExpenseReportSummaryResponse,
    ReturnExpenseReportRequest,
    SaveExpenseReportLinesRequest,
    SetAttachmentLineRequest,
)
from time_reporting.modules.users.contracts import UserRole

Scope = Literal["mine", "all"]

router = APIRouter(prefix="/expenses", tags=["expenses"])

_NOT_FOUND_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"description": "Report or attachment not found"}
}
_RULE_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_400_BAD_REQUEST: {"description": "The report/lines violate an expenses rule"}
}
_STATUS_CONFLICT_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_409_CONFLICT: {"description": "The report's status does not allow this action"}
}


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


@router.get("/options")
async def list_expense_options(
    current_user: CurrentUserDep, bus: BusDep
) -> list[ExpenseOptionResponse]:
    options = await bus.query(ListExpenseOptions(user_id=current_user.id))
    return [ExpenseOptionResponse.model_validate(option) for option in options]


@router.get("/reports")
async def list_my_expense_reports(
    current_user: CurrentUserDep,
    bus: BusDep,
    year: Annotated[int, Query(ge=2000, le=2100)],
    month: Annotated[int, Query(ge=1, le=12)],
    user_id: Annotated[UUID | None, Query()] = None,
) -> list[ExpenseReportSummaryResponse]:
    target_user_id = current_user.id if user_id is None else user_id
    if target_user_id != current_user.id and UserRole.MANAGER not in current_user.roles:
        raise _forbidden("Cannot view another user's expense reports")
    reports = await bus.query(ListMyExpenseReports(user_id=target_user_id, year=year, month=month))
    return [ExpenseReportSummaryResponse.model_validate(report) for report in reports]


@router.post("/reports", status_code=status.HTTP_201_CREATED, responses=_RULE_RESPONSE)
async def create_expense_report(
    body: CreateExpenseReportRequest, current_user: CurrentUserDep, bus: BusDep
) -> ExpenseReportResponse:
    try:
        report = await bus.execute(
            CreateExpenseReport(
                user_id=current_user.id,
                project_id=body.project_id,
                year=body.year,
                month=body.month,
            )
        )
    except ExpenseProjectClosedError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ExpenseReportAlreadyExistsError as exc:
        raise _conflict(str(exc)) from exc
    return ExpenseReportResponse.model_validate(report)


@router.get("/reports/{report_id}", responses=_NOT_FOUND_RESPONSE)
async def get_expense_report(
    report_id: UUID, current_user: CurrentUserDep, bus: BusDep
) -> ExpenseReportResponse:
    try:
        report = await bus.query(GetExpenseReport(report_id=report_id, viewer_id=current_user.id))
    except ExpenseReportNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    return ExpenseReportResponse.model_validate(report)


@router.put(
    "/reports/{report_id}/lines",
    responses={**_NOT_FOUND_RESPONSE, **_RULE_RESPONSE, **_STATUS_CONFLICT_RESPONSE},
)
async def save_expense_report_lines(
    report_id: UUID, body: SaveExpenseReportLinesRequest, current_user: CurrentUserDep, bus: BusDep
) -> ExpenseReportResponse:
    lines = tuple(
        ExpenseLineChange(
            line_id=change.line_id,
            billing_item_id=change.billing_item_id,
            expense_date=change.expense_date,
            amount=change.amount,
            description=change.description,
            vendor=change.vendor,
            document_no=change.document_no,
        )
        for change in body.lines
    )
    try:
        report = await bus.execute(
            SaveExpenseReportLines(
                report_id=report_id,
                actor_id=current_user.id,
                lines=lines,
                delete_line_ids=frozenset(body.delete_line_ids),
            )
        )
    except ExpenseReportNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    except (ExpenseLineNotFoundError, ExpenseBillingItemNotFoundError) as exc:
        raise _not_found(str(exc)) from exc
    except (ExpenseReportNotEditableError, ExpenseReportLockedError) as exc:
        raise _conflict(str(exc)) from exc
    except ExpenseDateOutsidePeriodError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ExpenseReportResponse.model_validate(report)


@router.delete(
    "/reports/{report_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**_NOT_FOUND_RESPONSE, **_STATUS_CONFLICT_RESPONSE},
)
async def delete_expense_report(report_id: UUID, current_user: CurrentUserDep, bus: BusDep) -> None:
    try:
        await bus.execute(DeleteExpenseReport(report_id=report_id, actor_id=current_user.id))
    except ExpenseReportNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    except ExpenseReportNotEditableError as exc:
        raise _conflict(str(exc)) from exc


@router.post(
    "/reports/{report_id}/submit",
    responses={**_NOT_FOUND_RESPONSE, **_STATUS_CONFLICT_RESPONSE},
)
async def submit_expense_report(
    report_id: UUID, current_user: CurrentUserDep, bus: BusDep
) -> ExpenseReportResponse:
    try:
        report = await bus.execute(
            SubmitExpenseReport(report_id=report_id, actor_id=current_user.id)
        )
    except ExpenseReportNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    except InvalidExpenseStatusTransitionError as exc:
        raise _conflict(str(exc)) from exc
    return ExpenseReportResponse.model_validate(report)


@router.post(
    "/reports/{report_id}/approve",
    responses={**_NOT_FOUND_RESPONSE, **_STATUS_CONFLICT_RESPONSE},
)
async def approve_expense_report(
    report_id: UUID, current_user: ManagerDep, bus: BusDep
) -> ExpenseReportResponse:
    try:
        report = await bus.execute(
            ApproveExpenseReport(report_id=report_id, reviewer_id=current_user.id)
        )
    except ExpenseReportNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    except ExpenseSelfReviewError as exc:
        raise _forbidden(str(exc)) from exc
    except InvalidExpenseStatusTransitionError as exc:
        raise _conflict(str(exc)) from exc
    return ExpenseReportResponse.model_validate(report)


@router.post(
    "/reports/{report_id}/return",
    responses={**_NOT_FOUND_RESPONSE, **_RULE_RESPONSE, **_STATUS_CONFLICT_RESPONSE},
)
async def return_expense_report(
    report_id: UUID,
    body: ReturnExpenseReportRequest,
    current_user: ManagerDep,
    bus: BusDep,
) -> ExpenseReportResponse:
    try:
        report = await bus.execute(
            ReturnExpenseReport(
                report_id=report_id, reviewer_id=current_user.id, comment=body.comment
            )
        )
    except ExpenseReportNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    except ExpenseSelfReviewError as exc:
        raise _forbidden(str(exc)) from exc
    except ExpenseReturnCommentRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except (InvalidExpenseStatusTransitionError, ExpenseReportLockedError) as exc:
        raise _conflict(str(exc)) from exc
    return ExpenseReportResponse.model_validate(report)


@router.get("/submissions")
async def list_submitted_expense_reports(
    current_user: ManagerDep,
    bus: BusDep,
    scope: Annotated[Scope, Query()] = "all",
) -> list[ExpenseReportSummaryResponse]:
    manager_id = None if scope == "all" else current_user.id
    reports = await bus.query(ListSubmittedExpenseReports(manager_id=manager_id))
    return [ExpenseReportSummaryResponse.model_validate(report) for report in reports]


@router.post(
    "/reports/{report_id}/attachments",
    status_code=status.HTTP_201_CREATED,
    responses={
        **_NOT_FOUND_RESPONSE,
        **_STATUS_CONFLICT_RESPONSE,
        status.HTTP_413_CONTENT_TOO_LARGE: {"description": "The file is too large"},
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {"description": "The file type isn't allowed"},
    },
)
async def add_expense_attachment(
    report_id: UUID,
    current_user: CurrentUserDep,
    bus: BusDep,
    file: Annotated[UploadFile, File()],
    file_name: Annotated[str | None, Form()] = None,
    line_id: Annotated[UUID | None, Form()] = None,
) -> ExpenseAttachmentResponse:
    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_ATTACHMENT_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Attachment type {content_type!r} is not allowed",
        )
    content = await file.read()
    try:
        attachment = await bus.execute(
            AddExpenseAttachment(
                report_id=report_id,
                actor_id=current_user.id,
                file_name=file_name or file.filename or "attachment",
                content_type=content_type,
                content=content,
                line_id=line_id,
            )
        )
    except (ExpenseReportNotFoundError, ExpenseLineNotFoundError) as exc:
        raise _not_found(str(exc)) from exc
    except (ExpenseReportNotEditableError, ExpenseReportLockedError) as exc:
        raise _conflict(str(exc)) from exc
    except AttachmentTooLargeError as exc:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(exc)) from exc
    except AttachmentTypeNotAllowedError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)
        ) from exc
    return ExpenseAttachmentResponse.model_validate(attachment)


@router.get("/attachments/{attachment_id}", responses=_NOT_FOUND_RESPONSE)
async def download_expense_attachment(
    attachment_id: UUID, current_user: CurrentUserDep, bus: BusDep
) -> FileResponse:
    try:
        file = await bus.query(
            GetAttachmentPath(attachment_id=attachment_id, viewer_id=current_user.id)
        )
    except AttachmentNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    return FileResponse(file.path, filename=file.file_name, media_type=file.content_type)


@router.delete(
    "/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**_NOT_FOUND_RESPONSE, **_STATUS_CONFLICT_RESPONSE},
)
async def delete_expense_attachment(
    attachment_id: UUID, current_user: CurrentUserDep, bus: BusDep
) -> None:
    try:
        await bus.execute(
            DeleteExpenseAttachment(attachment_id=attachment_id, actor_id=current_user.id)
        )
    except AttachmentNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    except (ExpenseReportNotEditableError, ExpenseReportLockedError) as exc:
        raise _conflict(str(exc)) from exc


@router.put(
    "/attachments/{attachment_id}/line",
    responses={**_NOT_FOUND_RESPONSE, **_STATUS_CONFLICT_RESPONSE},
)
async def set_expense_attachment_line(
    attachment_id: UUID,
    body: SetAttachmentLineRequest,
    current_user: CurrentUserDep,
    bus: BusDep,
) -> ExpenseAttachmentResponse:
    try:
        attachment = await bus.execute(
            SetAttachmentLine(
                attachment_id=attachment_id, actor_id=current_user.id, line_id=body.line_id
            )
        )
    except (AttachmentNotFoundError, ExpenseLineNotFoundError) as exc:
        raise _not_found(str(exc)) from exc
    except (ExpenseReportNotEditableError, ExpenseReportLockedError) as exc:
        raise _conflict(str(exc)) from exc
    return ExpenseAttachmentResponse.model_validate(attachment)
