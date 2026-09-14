"""Work calendar HTTP API: readable by any authenticated user, writable by admins."""

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from time_reporting.api.deps import BusDep
from time_reporting.modules.auth.dependencies import AdminDep, CurrentUserDep
from time_reporting.modules.work_calendar.contracts import (
    AddNonWorkingDay,
    CalendarRangeTooWideError,
    DeleteNonWorkingDay,
    GetCalendarDays,
    HolidayCountryNotSupportedError,
    ImportPublicHolidays,
    ListNonWorkingDays,
    NonWorkingDayAlreadyExistsError,
    NonWorkingDayNotFoundError,
    UpdateNonWorkingDay,
)
from time_reporting.modules.work_calendar.schemas import (
    CalendarDayResponse,
    ImportHolidaysRequest,
    ImportHolidaysResponse,
    NonWorkingDayCreateRequest,
    NonWorkingDayResponse,
    NonWorkingDayUpdateRequest,
)

router = APIRouter(prefix="/calendar", tags=["calendar"])

_NOT_FOUND_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"description": "Non-working day not found"}
}
_DATE_CONFLICT_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_409_CONFLICT: {"description": "A non-working day already exists on this date"}
}


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Non-working day not found")


def _date_conflict(day: date) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"A non-working day already exists on {day}",
    )


@router.get("/days")
async def get_calendar_days(
    _user: CurrentUserDep,
    bus: BusDep,
    date_from: Annotated[date, Query(alias="from")],
    date_to: Annotated[date, Query(alias="to")],
) -> list[CalendarDayResponse]:
    try:
        days = await bus.query(GetCalendarDays(date_from=date_from, date_to=date_to))
    except CalendarRangeTooWideError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return [CalendarDayResponse.model_validate(day) for day in days]


@router.get("/non-working-days")
async def list_non_working_days(
    _user: CurrentUserDep, bus: BusDep, year: Annotated[int | None, Query()] = None
) -> list[NonWorkingDayResponse]:
    days = await bus.query(ListNonWorkingDays(year=year))
    return [NonWorkingDayResponse.model_validate(day) for day in days]


@router.post(
    "/non-working-days", status_code=status.HTTP_201_CREATED, responses=_DATE_CONFLICT_RESPONSE
)
async def add_non_working_day(
    body: NonWorkingDayCreateRequest, _admin: AdminDep, bus: BusDep
) -> NonWorkingDayResponse:
    try:
        non_working_day = await bus.execute(
            AddNonWorkingDay(day=body.day, name=body.name, kind=body.kind)
        )
    except NonWorkingDayAlreadyExistsError as exc:
        raise _date_conflict(body.day) from exc
    return NonWorkingDayResponse.model_validate(non_working_day)


@router.patch(
    "/non-working-days/{non_working_day_id}",
    responses={**_NOT_FOUND_RESPONSE, **_DATE_CONFLICT_RESPONSE},
)
async def update_non_working_day(
    non_working_day_id: UUID,
    body: NonWorkingDayUpdateRequest,
    _admin: AdminDep,
    bus: BusDep,
) -> NonWorkingDayResponse:
    try:
        non_working_day = await bus.execute(
            UpdateNonWorkingDay(non_working_day_id=non_working_day_id, day=body.day, name=body.name)
        )
    except NonWorkingDayNotFoundError as exc:
        raise _not_found() from exc
    except NonWorkingDayAlreadyExistsError as exc:
        raise _date_conflict(exc.day) from exc
    return NonWorkingDayResponse.model_validate(non_working_day)


@router.delete(
    "/non-working-days/{non_working_day_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_NOT_FOUND_RESPONSE,
)
async def delete_non_working_day(non_working_day_id: UUID, _admin: AdminDep, bus: BusDep) -> None:
    try:
        await bus.execute(DeleteNonWorkingDay(non_working_day_id=non_working_day_id))
    except NonWorkingDayNotFoundError as exc:
        raise _not_found() from exc


@router.post("/non-working-days/import")
async def import_public_holidays(
    body: ImportHolidaysRequest, _admin: AdminDep, bus: BusDep
) -> ImportHolidaysResponse:
    try:
        added = await bus.execute(ImportPublicHolidays(year=body.year))
    except HolidayCountryNotSupportedError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ImportHolidaysResponse(added=added)
