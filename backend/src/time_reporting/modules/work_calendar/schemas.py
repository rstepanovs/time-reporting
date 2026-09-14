"""HTTP request/response models of the work_calendar API."""

from datetime import date
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from time_reporting.modules.work_calendar.contracts import NonWorkingDayKind

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class NonWorkingDayCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: date
    name: ShortText
    kind: NonWorkingDayKind


class NonWorkingDayUpdateRequest(BaseModel):
    """Partial update: omitted fields are left unchanged. ``kind`` is immutable."""

    model_config = ConfigDict(extra="forbid")

    day: date | None = None
    name: ShortText | None = None


class NonWorkingDayResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    day: date
    name: str
    kind: NonWorkingDayKind


class CalendarDayResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    day: date
    is_weekend: bool
    non_working_day: NonWorkingDayResponse | None


class ImportHolidaysRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    year: Annotated[int, Field(ge=1900, le=2200)]


class ImportHolidaysResponse(BaseModel):
    added: int
