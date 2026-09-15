"""ORM models.

Import every model module here so that ``Base.metadata`` is complete when
Alembic runs autogenerate.
"""

from time_reporting.db.base import Base
from time_reporting.modules.customers.models import Customer
from time_reporting.modules.projects.models import Project, ProjectBillingItem, ProjectMember
from time_reporting.modules.timesheets.models import (
    TimeEntry,
    TimesheetRowComment,
    TimesheetWeek,
)
from time_reporting.modules.users.models import User
from time_reporting.modules.work_calendar.models import NonWorkingDay

__all__ = [
    "Base",
    "Customer",
    "NonWorkingDay",
    "Project",
    "ProjectBillingItem",
    "ProjectMember",
    "TimeEntry",
    "TimesheetRowComment",
    "TimesheetWeek",
    "User",
]
