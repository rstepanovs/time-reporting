"""Timesheets HTTP API.

Every authenticated user reads and writes their own week; admins and project managers may also
read (but not write) another user's week.
"""

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from time_reporting.api.deps import BusDep
from time_reporting.modules.auth.dependencies import CurrentUserDep
from time_reporting.modules.timesheets.contracts import (
    DailyHoursExceededError,
    DuplicateChangeError,
    EntryDateOutsideWeekError,
    GetTimesheetWeek,
    ListTimesheetOptions,
    QuantityOutOfRangeError,
    SaveTimesheetWeek,
    TimeEntryChange,
    TimesheetBillingItemNotFoundError,
    TimesheetRowClosedError,
    WeekStartNotMondayError,
)
from time_reporting.modules.timesheets.schemas import (
    SaveTimesheetWeekRequest,
    TimesheetOptionResponse,
    TimesheetWeekResponse,
)
from time_reporting.modules.users.contracts import UserNotFoundError, UserRole

router = APIRouter(prefix="/timesheets", tags=["timesheets"])

_VIEW_ANY_ROLES = frozenset({UserRole.ADMIN, UserRole.PROJECT_MANAGER})

_USER_NOT_FOUND_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"description": "User not found"}
}
_RULE_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_400_BAD_REQUEST: {"description": "The week/entries violate a timesheet rule"}
}


def _week_not_monday(exc: WeekStartNotMondayError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _user_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


@router.get("/weeks/{week_start}", responses={**_USER_NOT_FOUND_RESPONSE, **_RULE_RESPONSE})
async def get_timesheet_week(
    week_start: date,
    current_user: CurrentUserDep,
    bus: BusDep,
    user_id: Annotated[UUID | None, Query()] = None,
) -> TimesheetWeekResponse:
    target_user_id = current_user.id if user_id is None else user_id
    if target_user_id != current_user.id and current_user.role not in _VIEW_ANY_ROLES:
        raise _forbidden("Cannot view another user's timesheet")

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
    responses={**_USER_NOT_FOUND_RESPONSE, **_RULE_RESPONSE},
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
    try:
        week = await bus.execute(
            SaveTimesheetWeek(user_id=current_user.id, week_start=week_start, changes=changes)
        )
    except WeekStartNotMondayError as exc:
        raise _week_not_monday(exc) from exc
    except UserNotFoundError as exc:
        raise _user_not_found() from exc
    except TimesheetBillingItemNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (
        EntryDateOutsideWeekError,
        DuplicateChangeError,
        TimesheetRowClosedError,
        QuantityOutOfRangeError,
        DailyHoursExceededError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return TimesheetWeekResponse.model_validate(week)


@router.get("/options")
async def list_timesheet_options(
    current_user: CurrentUserDep, bus: BusDep
) -> list[TimesheetOptionResponse]:
    options = await bus.query(ListTimesheetOptions(user_id=current_user.id))
    return [TimesheetOptionResponse.model_validate(option) for option in options]
