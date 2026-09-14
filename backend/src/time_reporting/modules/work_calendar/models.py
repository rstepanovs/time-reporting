"""Work calendar ORM entities, internal to the module — other modules use
``work_calendar.contracts``."""

import uuid
from datetime import date

from sqlalchemy import Date, Enum, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from time_reporting.db.base import Base
from time_reporting.db.mixins import TimestampMixin
from time_reporting.modules.work_calendar.contracts import NonWorkingDayKind


class NonWorkingDay(TimestampMixin, Base):
    """A single company-wide non-working day: a public holiday, a bridge day or a day off."""

    __tablename__ = "non_working_days"
    __table_args__ = (UniqueConstraint("day", name="uq_non_working_days_day"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    day: Mapped[date] = mapped_column(Date)
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[NonWorkingDayKind] = mapped_column(
        Enum(
            NonWorkingDayKind,
            name="non_working_day_kind",
            values_callable=lambda kinds: [k.value for k in kinds],
        )
    )
