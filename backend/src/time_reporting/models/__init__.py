"""ORM models.

Import every model module here so that ``Base.metadata`` is complete when
Alembic runs autogenerate.
"""

from time_reporting.db.base import Base
from time_reporting.modules.audit.models import AuditEvent
from time_reporting.modules.company.models import CompanySettings
from time_reporting.modules.customers.models import Customer
from time_reporting.modules.expenses.models import (
    ExpenseAttachment,
    ExpenseReport,
    ExpenseReportLine,
)
from time_reporting.modules.invoices.models import Invoice, InvoiceBillingPeriod, InvoiceLine
from time_reporting.modules.projects.models import Project, ProjectBillingItem, ProjectMember
from time_reporting.modules.timesheets.models import (
    TimeEntry,
    TimesheetRowComment,
    TimesheetWeek,
)
from time_reporting.modules.users.models import User
from time_reporting.modules.work_calendar.models import NonWorkingDay

__all__ = [
    "AuditEvent",
    "Base",
    "CompanySettings",
    "Customer",
    "ExpenseAttachment",
    "ExpenseReport",
    "ExpenseReportLine",
    "Invoice",
    "InvoiceBillingPeriod",
    "InvoiceLine",
    "NonWorkingDay",
    "Project",
    "ProjectBillingItem",
    "ProjectMember",
    "TimeEntry",
    "TimesheetRowComment",
    "TimesheetWeek",
    "User",
]
