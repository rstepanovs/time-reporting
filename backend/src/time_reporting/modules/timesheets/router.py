"""Timesheets HTTP API.

Every authenticated user reads and writes their own week/dashboard; managers may also read (but
not write) another user's data.
"""

from datetime import date
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Query, status

from time_reporting.api.deps import BusDep
from time_reporting.modules.auth.dependencies import AdminDep, CurrentUserDep, ManagerDep
from time_reporting.modules.timesheets.contracts import (
    ApproveTimesheetWeek,
    BillingPeriodAlreadySentError,
    BillingPeriodLockedError,
    BillingPeriodNotFoundError,
    BillingPeriodNotReadyError,
    DailyHoursExceededError,
    DuplicateChangeError,
    EntryDateOutsideWeekError,
    GetMonthCalendar,
    GetMonthTimeSummary,
    GetTeamMonthOverview,
    GetTimesheetWeek,
    GetWeeklyHours,
    GetYearHours,
    InvalidWeekStatusTransitionError,
    ListBillingPeriods,
    ListSubmittedTimesheetWeeks,
    ListTimesheetOptions,
    QuantityOutOfRangeError,
    ReopenProjectBillingPeriod,
    ReturnCommentRequiredError,
    ReturnTimesheetWeek,
    RowCommentChange,
    SaveTimesheetWeek,
    SelfReviewError,
    SendProjectMonthToBilling,
    SubmitTimesheetWeek,
    TimeEntryChange,
    TimesheetBillingItemNotFoundError,
    TimesheetProjectNotFoundError,
    TimesheetRowClosedError,
    TimesheetWeekLockedError,
    WeekRangeOutOfBoundsError,
    WeekStartNotMondayError,
)
from time_reporting.modules.timesheets.schemas import (
    BillingPeriodPageResponse,
    MonthCalendarResponse,
    MonthTimeSummaryResponse,
    ProjectBillingPeriodResponse,
    ReturnTimesheetWeekRequest,
    SaveTimesheetWeekRequest,
    SendProjectMonthToBillingRequest,
    TeamMonthOverviewResponse,
    TimesheetOptionResponse,
    TimesheetWeekResponse,
    TimesheetWeekSummaryResponse,
    WeeklyHoursResponse,
    YearHoursResponse,
)
from time_reporting.modules.users.contracts import UserDTO, UserNotFoundError, UserRole

Scope = Literal["mine", "all"]

router = APIRouter(prefix="/timesheets", tags=["timesheets"])

_USER_NOT_FOUND_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"description": "User not found"}
}
_RULE_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_400_BAD_REQUEST: {"description": "The week/entries violate a timesheet rule"}
}
_STATUS_CONFLICT_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_409_CONFLICT: {"description": "The week's status does not allow this action"}
}


def _week_not_monday(exc: WeekStartNotMondayError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _user_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _resolve_target_user(current_user: UserDTO, user_id: UUID | None) -> UUID:
    """The user whose data is being requested: ``current_user`` unless ``user_id`` names someone
    else, which is only allowed for a manager."""
    target_user_id = current_user.id if user_id is None else user_id
    if target_user_id != current_user.id and UserRole.MANAGER not in current_user.roles:
        raise _forbidden("Cannot view another user's timesheet")
    return target_user_id


@router.get("/weeks/{week_start}", responses={**_USER_NOT_FOUND_RESPONSE, **_RULE_RESPONSE})
async def get_timesheet_week(
    week_start: date,
    current_user: CurrentUserDep,
    bus: BusDep,
    user_id: Annotated[UUID | None, Query()] = None,
) -> TimesheetWeekResponse:
    target_user_id = _resolve_target_user(current_user, user_id)

    try:
        week = await bus.query(
            GetTimesheetWeek(
                user_id=target_user_id, week_start=week_start, viewer_id=current_user.id
            )
        )
    except WeekStartNotMondayError as exc:
        raise _week_not_monday(exc) from exc
    except UserNotFoundError as exc:
        raise _user_not_found() from exc
    return TimesheetWeekResponse.model_validate(week)


@router.put(
    "/weeks/{week_start}/entries",
    responses={**_USER_NOT_FOUND_RESPONSE, **_RULE_RESPONSE, **_STATUS_CONFLICT_RESPONSE},
)
async def save_timesheet_week(
    week_start: date, body: SaveTimesheetWeekRequest, current_user: CurrentUserDep, bus: BusDep
) -> TimesheetWeekResponse:
    changes = tuple(
        TimeEntryChange(
            billing_item_id=change.billing_item_id,
            date=change.date,
            quantity=change.quantity,
            note=change.note,
        )
        for change in body.changes
    )
    row_comments = tuple(
        RowCommentChange(billing_item_id=change.billing_item_id, comment=change.comment)
        for change in body.row_comments
    )
    try:
        week = await bus.execute(
            SaveTimesheetWeek(
                user_id=current_user.id,
                week_start=week_start,
                changes=changes,
                row_comments=row_comments,
            )
        )
    except WeekStartNotMondayError as exc:
        raise _week_not_monday(exc) from exc
    except UserNotFoundError as exc:
        raise _user_not_found() from exc
    except TimesheetBillingItemNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (TimesheetWeekLockedError, BillingPeriodLockedError) as exc:
        raise _conflict(str(exc)) from exc
    except (
        EntryDateOutsideWeekError,
        DuplicateChangeError,
        TimesheetRowClosedError,
        QuantityOutOfRangeError,
        DailyHoursExceededError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return TimesheetWeekResponse.model_validate(week)


@router.post(
    "/weeks/{week_start}/submit",
    responses={**_USER_NOT_FOUND_RESPONSE, **_STATUS_CONFLICT_RESPONSE},
)
async def submit_timesheet_week(
    week_start: date, current_user: CurrentUserDep, bus: BusDep
) -> TimesheetWeekResponse:
    try:
        week = await bus.execute(
            SubmitTimesheetWeek(user_id=current_user.id, week_start=week_start)
        )
    except WeekStartNotMondayError as exc:
        raise _week_not_monday(exc) from exc
    except UserNotFoundError as exc:
        raise _user_not_found() from exc
    except InvalidWeekStatusTransitionError as exc:
        raise _conflict(str(exc)) from exc
    return TimesheetWeekResponse.model_validate(week)


@router.post(
    "/weeks/{week_start}/approve",
    responses={**_USER_NOT_FOUND_RESPONSE, **_STATUS_CONFLICT_RESPONSE},
)
async def approve_timesheet_week(
    week_start: date,
    current_user: ManagerDep,
    bus: BusDep,
    user_id: Annotated[UUID, Query()],
) -> TimesheetWeekResponse:
    try:
        week = await bus.execute(
            ApproveTimesheetWeek(
                user_id=user_id, week_start=week_start, reviewer_id=current_user.id
            )
        )
    except WeekStartNotMondayError as exc:
        raise _week_not_monday(exc) from exc
    except UserNotFoundError as exc:
        raise _user_not_found() from exc
    except SelfReviewError as exc:
        raise _forbidden(str(exc)) from exc
    except InvalidWeekStatusTransitionError as exc:
        raise _conflict(str(exc)) from exc
    return TimesheetWeekResponse.model_validate(week)


@router.post(
    "/weeks/{week_start}/return",
    responses={**_USER_NOT_FOUND_RESPONSE, **_RULE_RESPONSE, **_STATUS_CONFLICT_RESPONSE},
)
async def return_timesheet_week(
    week_start: date,
    body: ReturnTimesheetWeekRequest,
    current_user: ManagerDep,
    bus: BusDep,
    user_id: Annotated[UUID, Query()],
) -> TimesheetWeekResponse:
    try:
        week = await bus.execute(
            ReturnTimesheetWeek(
                user_id=user_id,
                week_start=week_start,
                reviewer_id=current_user.id,
                comment=body.comment,
            )
        )
    except WeekStartNotMondayError as exc:
        raise _week_not_monday(exc) from exc
    except UserNotFoundError as exc:
        raise _user_not_found() from exc
    except SelfReviewError as exc:
        raise _forbidden(str(exc)) from exc
    except ReturnCommentRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except (InvalidWeekStatusTransitionError, BillingPeriodLockedError) as exc:
        raise _conflict(str(exc)) from exc
    return TimesheetWeekResponse.model_validate(week)


@router.get("/submissions")
async def list_submitted_timesheet_weeks(
    current_user: ManagerDep,
    bus: BusDep,
    scope: Annotated[Scope, Query()] = "all",
) -> list[TimesheetWeekSummaryResponse]:
    manager_id = None if scope == "all" else current_user.id
    summaries = await bus.query(ListSubmittedTimesheetWeeks(manager_id=manager_id))
    return [TimesheetWeekSummaryResponse.model_validate(summary) for summary in summaries]


@router.get("/team/{year}/{month}")
async def get_team_month_overview(
    year: Annotated[int, Path(ge=2000, le=2100)],
    month: Annotated[int, Path(ge=1, le=12)],
    current_user: ManagerDep,
    bus: BusDep,
    scope: Annotated[Scope, Query()] = "mine",
) -> TeamMonthOverviewResponse:
    manager_id = None if scope == "all" else current_user.id
    overview = await bus.query(
        GetTeamMonthOverview(manager_id=manager_id, year=year, month=month, today=date.today())
    )
    return TeamMonthOverviewResponse.model_validate(overview)


@router.get("/billing-periods")
async def list_billing_periods(
    _admin: AdminDep,
    bus: BusDep,
    project_id: Annotated[UUID | None, Query()] = None,
    customer_id: Annotated[UUID | None, Query()] = None,
    month_from: Annotated[date | None, Query()] = None,
    month_to: Annotated[date | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> BillingPeriodPageResponse:
    page = await bus.query(
        ListBillingPeriods(
            project_id=project_id,
            customer_id=customer_id,
            month_from=month_from,
            month_to=month_to,
            limit=limit,
            offset=offset,
        )
    )
    return BillingPeriodPageResponse.model_validate(page)


@router.post(
    "/billing-periods",
    status_code=status.HTTP_201_CREATED,
    responses={
        **_USER_NOT_FOUND_RESPONSE,
        status.HTTP_409_CONFLICT: {"description": "Not ready to send, or already sent"},
    },
)
async def send_project_month_to_billing(
    body: SendProjectMonthToBillingRequest, current_user: ManagerDep, bus: BusDep
) -> ProjectBillingPeriodResponse:
    try:
        period = await bus.execute(
            SendProjectMonthToBilling(
                project_id=body.project_id,
                year=body.year,
                month=body.month,
                sent_by_id=current_user.id,
            )
        )
    except TimesheetProjectNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except UserNotFoundError as exc:
        raise _user_not_found() from exc
    except (BillingPeriodNotReadyError, BillingPeriodAlreadySentError) as exc:
        raise _conflict(str(exc)) from exc
    return ProjectBillingPeriodResponse.model_validate(period)


@router.delete(
    "/billing-periods/{project_id}/{period_start}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={status.HTTP_404_NOT_FOUND: {"description": "No sent period found"}},
)
async def reopen_project_billing_period(
    project_id: UUID, period_start: date, _admin: AdminDep, bus: BusDep
) -> None:
    try:
        await bus.execute(
            ReopenProjectBillingPeriod(project_id=project_id, period_start=period_start)
        )
    except BillingPeriodNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/options")
async def list_timesheet_options(
    current_user: CurrentUserDep, bus: BusDep
) -> list[TimesheetOptionResponse]:
    options = await bus.query(ListTimesheetOptions(user_id=current_user.id))
    return [TimesheetOptionResponse.model_validate(option) for option in options]


@router.get("/calendar", responses=_USER_NOT_FOUND_RESPONSE)
async def get_month_calendar(
    current_user: CurrentUserDep,
    bus: BusDep,
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
    month: Annotated[int | None, Query(ge=1, le=12)] = None,
    user_id: Annotated[UUID | None, Query()] = None,
) -> MonthCalendarResponse:
    target_user_id = _resolve_target_user(current_user, user_id)
    today = date.today()

    try:
        calendar = await bus.query(
            GetMonthCalendar(
                user_id=target_user_id,
                year=year if year is not None else today.year,
                month=month if month is not None else today.month,
                today=today,
            )
        )
    except UserNotFoundError as exc:
        raise _user_not_found() from exc
    return MonthCalendarResponse.model_validate(calendar)


@router.get("/years/{year}", responses=_USER_NOT_FOUND_RESPONSE)
async def get_year_hours(
    year: Annotated[int, Path(ge=2000, le=2100)],
    current_user: CurrentUserDep,
    bus: BusDep,
    user_id: Annotated[UUID | None, Query()] = None,
) -> YearHoursResponse:
    target_user_id = _resolve_target_user(current_user, user_id)

    try:
        result = await bus.query(
            GetYearHours(user_id=target_user_id, year=year, today=date.today())
        )
    except UserNotFoundError as exc:
        raise _user_not_found() from exc
    return YearHoursResponse.model_validate(result)


@router.get("/months/{year}/{month}/summary", responses=_USER_NOT_FOUND_RESPONSE)
async def get_month_time_summary(
    year: Annotated[int, Path(ge=2000, le=2100)],
    month: Annotated[int, Path(ge=1, le=12)],
    current_user: CurrentUserDep,
    bus: BusDep,
    user_id: Annotated[UUID | None, Query()] = None,
) -> MonthTimeSummaryResponse:
    target_user_id = _resolve_target_user(current_user, user_id)

    try:
        summary = await bus.query(
            GetMonthTimeSummary(user_id=target_user_id, year=year, month=month, today=date.today())
        )
    except UserNotFoundError as exc:
        raise _user_not_found() from exc
    return MonthTimeSummaryResponse.model_validate(summary)


@router.get("/weekly-hours", responses={**_USER_NOT_FOUND_RESPONSE, **_RULE_RESPONSE})
async def get_weekly_hours(
    current_user: CurrentUserDep,
    bus: BusDep,
    weeks: Annotated[int, Query(ge=1, le=26)] = 6,
    user_id: Annotated[UUID | None, Query()] = None,
) -> WeeklyHoursResponse:
    target_user_id = _resolve_target_user(current_user, user_id)

    try:
        result = await bus.query(
            GetWeeklyHours(user_id=target_user_id, weeks=weeks, today=date.today())
        )
    except UserNotFoundError as exc:
        raise _user_not_found() from exc
    except WeekRangeOutOfBoundsError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return WeeklyHoursResponse.model_validate(result)
