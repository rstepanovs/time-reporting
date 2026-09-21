"""Demo data for local development: one user per access level plus a plain employee, a few
customers, and their projects.

Seeding is idempotent: users whose email, customers whose name, or projects whose (customer, name)
already exist are left untouched.
"""

import contextlib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from time_reporting.core.cqrs import Bus
from time_reporting.modules.company.contracts import (
    CompanyAddressDTO,
    GetCompanySettings,
    UpdateCompanySettings,
)
from time_reporting.modules.customers.contracts import (
    BillingAddressDTO,
    BillingIntervalUnit,
    BillingPeriodDTO,
    CreateCustomer,
    CustomerNameAlreadyExistsError,
    ListCustomers,
    UpdateCustomer,
)
from time_reporting.modules.expenses.contracts import (
    ApproveExpenseReport,
    CreateExpenseReport,
    ExpenseLineChange,
    ListExpenseOptions,
    ListMyExpenseReports,
    SaveExpenseReportLines,
    SubmitExpenseReport,
)
from time_reporting.modules.invoices.contracts import (
    CompanyProfileIncompleteError,
    CreateInvoiceDraft,
    InvoicePeriodNotEligibleError,
    IssueInvoice,
)
from time_reporting.modules.projects.contracts import (
    AddProjectBillingItem,
    AddProjectMember,
    BillingItemPreset,
    BillingUnit,
    CreateProject,
    ListProjectBillingItems,
    ListProjects,
    ProjectCustomerArchivedError,
    ProjectNameAlreadyExistsError,
    ProjectOptionDTO,
    UpdateProject,
    UpdateProjectBillingItem,
)
from time_reporting.modules.timesheets.contracts import (
    ApproveTimesheetWeek,
    BillingPeriodAlreadySentError,
    BillingPeriodRef,
    CountTimeEntries,
    ListTimesheetOptions,
    SaveTimesheetWeek,
    SendProjectMonthToBilling,
    SubmitTimesheetWeek,
    TimeEntryChange,
)
from time_reporting.modules.users.contracts import (
    CreateUser,
    EmailAlreadyExistsError,
    GetUserCredentialsByEmail,
    UserRole,
)
from time_reporting.modules.work_calendar.contracts import (
    AddNonWorkingDay,
    GetCalendarDays,
    HolidayCountryNotSupportedError,
    ImportPublicHolidays,
    ListNonWorkingDays,
    NonWorkingDayAlreadyExistsError,
    NonWorkingDayKind,
)

DEFAULT_DEMO_PASSWORD = "demo-password"


@dataclass(frozen=True, slots=True, kw_only=True)
class DemoUser:
    name: str
    email: str
    roles: frozenset[UserRole]


@dataclass(frozen=True, slots=True, kw_only=True)
class DemoCustomer:
    create: CreateCustomer
    archived: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class DemoBillingItem:
    """A custom billing item to add to a newly created demo project."""

    name: str
    unit: BillingUnit
    unit_rate: Decimal | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class DemoProject:
    customer_name: str
    name: str
    description: str | None = None
    member_emails: tuple[str, ...] = ()
    manager_email: str | None = None
    archived: bool = False
    # Give the six default billing items the rates in DEMO_BILLING_RATES/DEMO_PURCHASING_MARKUP.
    billing_rates: bool = False
    custom_billing_items: tuple[DemoBillingItem, ...] = ()
    # Never sent to billing, no rates needed; the demo accountant's own expense report on it
    # shows up in the accountant package as an internal cost, never rebilled — see
    # `_seed_expense_reports`.
    is_internal: bool = False


DEMO_USERS: tuple[DemoUser, ...] = (
    DemoUser(name="Alice Admin", email="admin@example.com", roles=frozenset({UserRole.ADMIN})),
    DemoUser(name="Mark Manager", email="manager@example.com", roles=frozenset({UserRole.MANAGER})),
    DemoUser(name="Emma Employee", email="employee@example.com", roles=frozenset()),
    DemoUser(
        name="Andy Accountant",
        email="accountant@example.com",
        roles=frozenset({UserRole.ACCOUNTANT}),
    ),
    DemoUser(
        name="Max Multi",
        email="lead@example.com",
        roles=frozenset({UserRole.ADMIN, UserRole.MANAGER}),
    ),
)

DEMO_CUSTOMERS: tuple[DemoCustomer, ...] = (
    DemoCustomer(
        create=CreateCustomer(
            name="Acme Corporation",
            legal_name="Acme Corporation GmbH",
            tax_id="DE123456789",
            billing_email="billing@acme.example",
            billing_address=BillingAddressDTO(
                line1="Unter den Linden 10", city="Berlin", postal_code="10117", country="DE"
            ),
            billing_period=BillingPeriodDTO(
                interval_count=1,
                interval_unit=BillingIntervalUnit.MONTH,
                anchor_date=date(2026, 1, 1),
            ),
            currency="EUR",
        )
    ),
    DemoCustomer(
        create=CreateCustomer(
            name="Globex",
            legal_name="Globex Ltd",
            tax_id="GB123456789",
            billing_email="accounts@globex.example",
            billing_address=BillingAddressDTO(
                line1="221B Baker Street", city="London", postal_code="NW1 6XE", country="GB"
            ),
            billing_period=BillingPeriodDTO(
                interval_count=2,
                interval_unit=BillingIntervalUnit.WEEK,
                anchor_date=date(2026, 1, 5),
            ),
            currency="GBP",
            payment_terms_days=14,
        )
    ),
    DemoCustomer(
        create=CreateCustomer(
            name="Initech",
            legal_name="Initech LLC",
            billing_address=BillingAddressDTO(
                line1="4120 Freidrich Lane",
                city="Austin",
                region="TX",
                postal_code="78744",
                country="US",
            ),
            billing_period=BillingPeriodDTO(
                interval_count=3,
                interval_unit=BillingIntervalUnit.MONTH,
                anchor_date=date(2026, 1, 1),
            ),
            currency="USD",
            payment_terms_days=45,
            notes="Contract ended; kept for billing history.",
        ),
        archived=True,
    ),
)

DEMO_PROJECTS: tuple[DemoProject, ...] = (
    DemoProject(
        customer_name="Acme Corporation",
        name="Website Revamp",
        description="Redesign the public marketing site.",
        member_emails=("manager@example.com", "employee@example.com", "lead@example.com"),
        manager_email="manager@example.com",
        billing_rates=True,
        custom_billing_items=(
            DemoBillingItem(
                name="On-call standby", unit=BillingUnit.HOUR, unit_rate=Decimal("50.00")
            ),
        ),
    ),
    DemoProject(
        customer_name="Acme Corporation",
        name="Internal Tooling",
        description="Roll out time tracking internally.",
        member_emails=("employee@example.com", "accountant@example.com"),
        manager_email="manager@example.com",
        billing_rates=True,
    ),
    DemoProject(
        customer_name="Acme Corporation",
        name="Company Overhead",
        description="Internal costs, never billed to a customer.",
        member_emails=("accountant@example.com",),
        manager_email="manager@example.com",
        is_internal=True,
    ),
    DemoProject(
        customer_name="Globex",
        name="Platform Migration",
        description="Move billing to the new platform.",
        member_emails=("manager@example.com",),
        manager_email="manager@example.com",
        billing_rates=True,
    ),
    DemoProject(
        customer_name="Initech",
        name="Legacy Support",
        description="Wind-down support after the contract ended.",
        member_emails=("employee@example.com",),
        archived=True,
        billing_rates=True,
    ),
)

# Applied to a newly created demo project's default items when DemoProject.billing_rates is set;
# rates are in whichever currency the project's customer bills in (a demo simplification — see
# DemoProject.billing_rates). Purchasing expenses get a markup instead of a rate; other expenses
# are left unset, like a real project would start out.
DEMO_BILLING_RATES: dict[BillingItemPreset, Decimal] = {
    BillingItemPreset.NORMAL_HOURS: Decimal("90.00"),
    BillingItemPreset.OVERTIME_HOURS: Decimal("135.00"),
    BillingItemPreset.TRAVEL_TIME: Decimal("45.00"),
    BillingItemPreset.PER_DIEM: Decimal("60.00"),
}
DEMO_PURCHASING_MARKUP = Decimal("10.00")

# The public holiday whose following day becomes the demo bridge day (a Thursday holiday, so the
# Friday after it is the classic "long weekend" bridge day).
DEMO_BRIDGE_DAY_AFTER_HOLIDAY = "Ascension Day"
DEMO_DAILY_HOURS = Decimal("8")
DEMO_OVERTIME_HOURS = Decimal("2")
DEMO_TRAVEL_HOURS = Decimal("3")
# How many months of history to book (this month plus the two before it), so the dashboard's
# year-hours table shows more than a single row.
DEMO_TIME_ENTRY_MONTHS = 3


@dataclass(slots=True)
class SeedReport:
    created_users: list[str] = field(default_factory=list)
    existing_users: list[str] = field(default_factory=list)
    created_customers: list[str] = field(default_factory=list)
    existing_customers: list[str] = field(default_factory=list)
    created_projects: list[str] = field(default_factory=list)
    existing_projects: list[str] = field(default_factory=list)
    imported_holidays: int = 0
    created_bridge_day: bool = False
    seeded_time_entries_for: list[str] = field(default_factory=list)
    # Demo users (all but whichever reviewed them) whose seeded weeks were pushed through the
    # submit/approve workflow, so a fresh checkout also has an example of that on the Timesheet
    # page.
    submitted_weeks_for: list[str] = field(default_factory=list)
    # Demo users who got one approved and one submitted expense report this month (a member of at
    # least two projects with an active `amount` item), so a fresh checkout has an example on the
    # Expenses page and a real blocker on the manager's approvals/team pages.
    seeded_expense_reports_for: list[str] = field(default_factory=list)
    # Set only the first time this runs: the company profile was still at the migration's
    # placeholder defaults (empty `legal_name`/`org_number`) and was filled with demo values.
    seeded_company_profile: bool = False
    # Set only the first time this runs: "Website Revamp"'s earliest booked month was sent to
    # billing and issued as an invoice, so a fresh checkout has a real one on `/invoices` and
    # `/accounting` instead of both pages being empty.
    seeded_invoice: bool = False


async def _find_customer_id_by_name(bus: Bus, name: str) -> UUID:
    """Page through all customers (including archived) to find one by exact name.

    Used only to resolve a customer that already existed before this seeding run, so its id
    wasn't captured when creating it.
    """
    offset = 0
    limit = 100
    while True:
        page = await bus.query(ListCustomers(limit=limit, offset=offset, include_inactive=True))
        for customer in page.items:
            if customer.name == name:
                return customer.id
        if offset + limit >= page.total:
            raise LookupError(f"No customer named {name!r} found while seeding projects")
        offset += limit


async def _apply_demo_billing_rates(bus: Bus, project_id: UUID) -> None:
    """Give the just-created project's default items their demo rates.

    Only called for a project just created by this run, so it can't yet have been priced.
    """
    items = await bus.query(ListProjectBillingItems(project_id=project_id, include_inactive=True))
    for item in items:
        if item.preset in DEMO_BILLING_RATES:
            await bus.execute(
                UpdateProjectBillingItem(
                    project_id=project_id,
                    item_id=item.id,
                    unit_rate=DEMO_BILLING_RATES[item.preset],
                )
            )
        elif item.preset is BillingItemPreset.PURCHASING_EXPENSES:
            await bus.execute(
                UpdateProjectBillingItem(
                    project_id=project_id, item_id=item.id, markup_percent=DEMO_PURCHASING_MARKUP
                )
            )


async def _seed_calendar(bus: Bus, report: SeedReport, *, today: date) -> None:
    """Import this and next year's public holidays, and add one demo bridge day.

    Both steps are idempotent by nature (``ImportPublicHolidays`` only adds missing dates, and a
    taken date is skipped), so re-running changes nothing once seeded.
    """
    for year in (today.year, today.year + 1):
        try:
            report.imported_holidays += await bus.execute(ImportPublicHolidays(year=year))
        except HolidayCountryNotSupportedError:
            # Demo data is best-effort: an unconfigured HOLIDAY_COUNTRY just skips the calendar.
            return

    holiday_dates_by_name = {
        day.name: day.day for day in await bus.query(ListNonWorkingDays(year=today.year))
    }
    holiday_date = holiday_dates_by_name.get(DEMO_BRIDGE_DAY_AFTER_HOLIDAY)
    if holiday_date is None:
        return
    try:
        await bus.execute(
            AddNonWorkingDay(
                day=holiday_date + timedelta(days=1),
                name="Bridge day",
                kind=NonWorkingDayKind.BRIDGE_DAY,
            )
        )
    except NonWorkingDayAlreadyExistsError:
        pass
    else:
        report.created_bridge_day = True


def _month_start_n_months_ago(today: date, months_ago: int) -> date:
    total_months = today.year * 12 + (today.month - 1) - months_ago
    return date(total_months // 12, total_months % 12 + 1, 1)


def _week_start(day: date) -> date:
    return day - timedelta(days=day.isoweekday() - 1)


def _option_with_normal_hours(
    options: tuple[ProjectOptionDTO, ...],
) -> ProjectOptionDTO | None:
    return next(
        (
            option
            for option in options
            if any(item.preset is BillingItemPreset.NORMAL_HOURS for item in option.billing_items)
        ),
        None,
    )


def _item_id_for_preset(option: ProjectOptionDTO, preset: BillingItemPreset) -> UUID | None:
    return next((item.id for item in option.billing_items if item.preset is preset), None)


def _reviewer_id(
    users: tuple[DemoUser, ...], user_ids_by_email: dict[str, UUID], *, owner_email: str
) -> UUID | None:
    """A ``manager``-level demo user other than ``owner_email``, to review that user's submitted
    weeks (nobody, not even an admin, may review their own). ``None`` if no other demo user holds
    ``manager``."""
    reviewer = next(
        (user for user in users if UserRole.MANAGER in user.roles and user.email != owner_email),
        None,
    )
    return user_ids_by_email.get(reviewer.email) if reviewer is not None else None


async def _submit_and_approve_demo_weeks(
    bus: Bus,
    report: SeedReport,
    user: DemoUser,
    user_id: UUID,
    week_starts: list[date],
    *,
    reviewer_id: UUID,
) -> None:
    """Push a just-seeded demo user's weeks through the submit/review workflow: every week but
    the most recent is submitted and then approved, and the most recent is left submitted (so
    the demo reviewer has something waiting on the approvals page). Only ever called for a
    freshly seeded user (guarded by the ``CountTimeEntries`` check above), so this always starts
    from an all-draft state and needs no idempotency check of its own."""
    for week_start in week_starts[:-1]:
        await bus.execute(SubmitTimesheetWeek(user_id=user_id, week_start=week_start))
        await bus.execute(
            ApproveTimesheetWeek(user_id=user_id, week_start=week_start, reviewer_id=reviewer_id)
        )
    await bus.execute(SubmitTimesheetWeek(user_id=user_id, week_start=week_starts[-1]))
    report.submitted_weeks_for.append(user.email)


async def _seed_time_entries(
    bus: Bus,
    report: SeedReport,
    users: tuple[DemoUser, ...],
    user_ids_by_email: dict[str, UUID],
    *,
    today: date,
) -> None:
    """Book normal working hours on every working day of the last ``DEMO_TIME_ENTRY_MONTHS``
    months up to today, plus a little overtime and travel time, for each demo user who is a
    project member (so has a booking option — this naturally skips ``admin@example.com``, who
    isn't a member of any demo project) and doesn't already have any time entries — so a fresh
    checkout has something to show on both the Timesheet page and the personal dashboard's month
    calendar and year-hours table."""
    range_from = _month_start_n_months_ago(today, DEMO_TIME_ENTRY_MONTHS - 1)
    calendar_days = await bus.query(GetCalendarDays(date_from=range_from, date_to=today))
    working_days = [
        day.day for day in calendar_days if not day.is_weekend and day.non_working_day is None
    ]
    if not working_days:
        return

    # The first and last working day booked in each calendar month get a couple of hours of
    # overtime/travel time on top of the normal hours, so the year-hours table isn't all one
    # column — a small, deterministic stand-in for "some weeks have a late day or a trip".
    first_working_day_of_month: dict[tuple[int, int], date] = {}
    last_working_day_of_month: dict[tuple[int, int], date] = {}
    for day in working_days:
        month_key = (day.year, day.month)
        first_working_day_of_month.setdefault(month_key, day)
        last_working_day_of_month[month_key] = day
    overtime_dates = frozenset(first_working_day_of_month.values())
    travel_dates = frozenset(last_working_day_of_month.values())

    working_days_by_week: dict[date, list[date]] = defaultdict(list)
    for day in working_days:
        working_days_by_week[_week_start(day)].append(day)

    for user in users:
        user_id = user_ids_by_email.get(user.email)
        if user_id is None:
            continue
        if await bus.query(CountTimeEntries(user_id=user_id)):
            continue
        options = await bus.query(ListTimesheetOptions(user_id=user_id))
        option = _option_with_normal_hours(options)
        if option is None:
            continue
        normal_item_id = _item_id_for_preset(option, BillingItemPreset.NORMAL_HOURS)
        assert normal_item_id is not None
        overtime_item_id = _item_id_for_preset(option, BillingItemPreset.OVERTIME_HOURS)
        travel_item_id = _item_id_for_preset(option, BillingItemPreset.TRAVEL_TIME)

        for week_start, days_in_week in sorted(working_days_by_week.items()):
            changes = [
                TimeEntryChange(billing_item_id=normal_item_id, date=day, quantity=DEMO_DAILY_HOURS)
                for day in days_in_week
            ]
            if overtime_item_id is not None:
                changes += [
                    TimeEntryChange(
                        billing_item_id=overtime_item_id, date=day, quantity=DEMO_OVERTIME_HOURS
                    )
                    for day in days_in_week
                    if day in overtime_dates
                ]
            if travel_item_id is not None:
                changes += [
                    TimeEntryChange(
                        billing_item_id=travel_item_id, date=day, quantity=DEMO_TRAVEL_HOURS
                    )
                    for day in days_in_week
                    if day in travel_dates
                ]
            await bus.execute(
                SaveTimesheetWeek(user_id=user_id, week_start=week_start, changes=tuple(changes))
            )
        report.seeded_time_entries_for.append(user.email)

        reviewer_id = _reviewer_id(users, user_ids_by_email, owner_email=user.email)
        if reviewer_id is not None:
            await _submit_and_approve_demo_weeks(
                bus,
                report,
                user,
                user_id,
                sorted(working_days_by_week),
                reviewer_id=reviewer_id,
            )


async def _seed_expense_reports(
    bus: Bus,
    report: SeedReport,
    users: tuple[DemoUser, ...],
    user_ids_by_email: dict[str, UUID],
    *,
    today: date,
) -> None:
    """One approved and one submitted expense report this month, for every demo user who is a
    member of at least two active projects with an active ``amount`` item (today,
    ``manager@example.com`` and ``employee@example.com``) and doesn't already have any reports
    this month — so a fresh checkout has an example on the Expenses page, and the manager's
    approvals/team pages have a real expense-report blocker to show, not just the
    always-submitted last timesheet week."""
    for user in users:
        user_id = user_ids_by_email.get(user.email)
        if user_id is None:
            continue
        if await bus.query(
            ListMyExpenseReports(user_id=user_id, year=today.year, month=today.month)
        ):
            continue
        options = [
            option
            for option in await bus.query(ListExpenseOptions(user_id=user_id))
            if option.billing_items
        ]
        if len(options) < 2:
            continue
        reviewer_id = _reviewer_id(users, user_ids_by_email, owner_email=user.email)
        if reviewer_id is None:
            continue

        approved_option, submitted_option = options[0], options[1]
        first_of_month = today.replace(day=1)

        approved_report = await bus.execute(
            CreateExpenseReport(
                user_id=user_id,
                project_id=approved_option.project.id,
                year=today.year,
                month=today.month,
            )
        )
        await bus.execute(
            SaveExpenseReportLines(
                report_id=approved_report.id,
                actor_id=user_id,
                lines=(
                    ExpenseLineChange(
                        line_id=None,
                        billing_item_id=approved_option.billing_items[0].id,
                        expense_date=first_of_month,
                        amount=Decimal("42.50"),
                        description="Client dinner",
                        vendor="Bella Italia",
                    ),
                ),
            )
        )
        await bus.execute(SubmitExpenseReport(report_id=approved_report.id, actor_id=user_id))
        await bus.execute(
            ApproveExpenseReport(report_id=approved_report.id, reviewer_id=reviewer_id)
        )

        submitted_report = await bus.execute(
            CreateExpenseReport(
                user_id=user_id,
                project_id=submitted_option.project.id,
                year=today.year,
                month=today.month,
            )
        )
        await bus.execute(
            SaveExpenseReportLines(
                report_id=submitted_report.id,
                actor_id=user_id,
                lines=(
                    ExpenseLineChange(
                        line_id=None,
                        billing_item_id=submitted_option.billing_items[0].id,
                        expense_date=first_of_month,
                        amount=Decimal("18.90"),
                        description="Taxi to client site",
                    ),
                ),
            )
        )
        await bus.execute(SubmitExpenseReport(report_id=submitted_report.id, actor_id=user_id))

        report.seeded_expense_reports_for.append(user.email)


async def _project_exists(bus: Bus, customer_id: UUID, name: str) -> bool:
    page = await bus.query(
        ListProjects(limit=1, offset=0, customer_id=customer_id, search=name, include_inactive=True)
    )
    return any(project.name == name for project in page.items)


async def _find_project_id_by_name(bus: Bus, customer_id: UUID, name: str) -> UUID:
    """Used only to resolve a project that already existed before this seeding run, so its id
    wasn't captured when creating it — see `_find_customer_id_by_name`."""
    page = await bus.query(
        ListProjects(limit=1, offset=0, customer_id=customer_id, search=name, include_inactive=True)
    )
    for project in page.items:
        if project.name == name:
            return project.id
    raise LookupError(f"No project named {name!r} found while seeding invoices")


async def _seed_company_profile(bus: Bus, report: SeedReport, *, today: date) -> None:
    """Fill in the singleton company profile with demo values, but only if it's still at the
    placeholder defaults the migration inserted (empty `legal_name`/`org_number`) — an admin who
    has already customized it, even partially, is never overwritten."""
    settings = await bus.query(GetCompanySettings())
    if settings.legal_name or settings.org_number:
        return
    await bus.execute(
        UpdateCompanySettings(
            actor_id=None,
            legal_name="Demo Consulting AB",
            org_number="556677-8899",
            vat_number="SE556677889901",
            address=CompanyAddressDTO(
                street="Sveavägen 1",
                street2=None,
                postal_code="111 34",
                city="Stockholm",
                country="SE",
            ),
            email="hello@democonsulting.example",
            phone="+46 8 123 45 67",
            registered_office="Stockholm",
            bankgiro="123-4567",
            iban="SE35 5000 0000 0549 1000 0003",
            bic="ESSESESS",
            f_tax_approved=True,
            default_invoice_locale="en",
            late_interest="8% per annum",
            invoice_number_prefix=f"{today.year}-",
            next_invoice_number=1,
            allow_self_review=False,
        )
    )
    report.seeded_company_profile = True


async def _seed_sent_invoice(
    bus: Bus,
    report: SeedReport,
    users: tuple[DemoUser, ...],
    user_ids_by_email: dict[str, UUID],
    project_ids_by_name: dict[str, UUID],
    customer_ids_by_name: dict[str, UUID],
    projects: tuple[DemoProject, ...],
    *,
    today: date,
) -> None:
    """Send the earliest booked month of the first non-internal, rated demo project to billing
    and issue an invoice for it, so a fresh checkout's `/invoices` and `/accounting` aren't both
    empty. The earliest of the `DEMO_TIME_ENTRY_MONTHS` booked months is used, never the current
    one — its last week is deliberately left submitted (see `_submit_and_approve_demo_weeks`), so
    every week of the earliest month is guaranteed already approved regardless of where in the
    month `today` falls. Picks the project/customer/reviewer/actor from the arguments (rather than
    hardcoding "Website Revamp"/"Acme Corporation"/emails) so this also works against the
    uniquely-renamed copies tests seed."""
    invoice_project = next(
        (
            project
            for project in projects
            if project.billing_rates and not project.is_internal and not project.archived
        ),
        None,
    )
    if invoice_project is None:
        return
    project_id = project_ids_by_name.get(invoice_project.name)
    customer_id = customer_ids_by_name.get(invoice_project.customer_name)
    reviewer = next((user for user in users if UserRole.MANAGER in user.roles), None)
    manager_id = user_ids_by_email.get(reviewer.email) if reviewer is not None else None
    accountant = next((user for user in users if UserRole.ACCOUNTANT in user.roles), None)
    accountant_id = user_ids_by_email.get(accountant.email) if accountant is not None else None
    if project_id is None or customer_id is None or manager_id is None or accountant_id is None:
        return

    period_start = _month_start_n_months_ago(today, DEMO_TIME_ENTRY_MONTHS - 1)
    with contextlib.suppress(BillingPeriodAlreadySentError):
        await bus.execute(
            SendProjectMonthToBilling(
                project_id=project_id,
                year=period_start.year,
                month=period_start.month,
                sent_by_id=manager_id,
            )
        )

    try:
        invoice = await bus.execute(
            CreateInvoiceDraft(
                customer_id=customer_id,
                periods=(BillingPeriodRef(project_id=project_id, period_start=period_start),),
                invoice_date=today,
                actor_id=accountant_id,
            )
        )
    except InvoicePeriodNotEligibleError:
        # Already invoiced by an earlier run of this function.
        return

    try:
        await bus.execute(IssueInvoice(invoice_id=invoice.id, actor_id=accountant_id))
    except CompanyProfileIncompleteError:
        # The profile is customized (so `_seed_company_profile` left it alone) but missing an
        # essential field — leave the draft as-is rather than failing the whole seeding run.
        return
    report.seeded_invoice = True


async def seed_demo_data(
    bus: Bus,
    *,
    password: str = DEFAULT_DEMO_PASSWORD,
    users: tuple[DemoUser, ...] = DEMO_USERS,
    customers: tuple[DemoCustomer, ...] = DEMO_CUSTOMERS,
    projects: tuple[DemoProject, ...] = DEMO_PROJECTS,
    today: date | None = None,
) -> SeedReport:
    """Create the missing demo records; each one is committed by its own top-level command."""
    report = SeedReport()
    user_ids_by_email: dict[str, UUID] = {}
    customer_ids_by_name: dict[str, UUID] = {}
    project_ids_by_name: dict[str, UUID] = {}
    today = today or date.today()

    await _seed_calendar(bus, report, today=today)
    await _seed_company_profile(bus, report, today=today)

    for user in users:
        try:
            created_user = await bus.execute(
                CreateUser(name=user.name, email=user.email, roles=user.roles, password=password)
            )
        except EmailAlreadyExistsError:
            report.existing_users.append(user.email)
            credentials = await bus.query(GetUserCredentialsByEmail(email=user.email))
            assert credentials is not None
            user_ids_by_email[user.email] = credentials.id
        else:
            report.created_users.append(user.email)
            user_ids_by_email[user.email] = created_user.id

    # Projects are created for every customer while it is still active, before any archiving
    # below — creating a project requires (and re-activating one requires) an active customer.
    for customer in customers:
        try:
            created_customer = await bus.execute(customer.create)
        except CustomerNameAlreadyExistsError:
            report.existing_customers.append(customer.create.name)
            customer_ids_by_name[customer.create.name] = await _find_customer_id_by_name(
                bus, customer.create.name
            )
            continue
        report.created_customers.append(customer.create.name)
        customer_ids_by_name[customer.create.name] = created_customer.id

    for project in projects:
        customer_id = customer_ids_by_name[project.customer_name]
        try:
            manager_id = (
                user_ids_by_email.get(project.manager_email) if project.manager_email else None
            )
            created_project = await bus.execute(
                CreateProject(
                    customer_id=customer_id,
                    name=project.name,
                    description=project.description,
                    is_internal=project.is_internal,
                    manager_id=manager_id,
                )
            )
        except ProjectNameAlreadyExistsError:
            report.existing_projects.append(project.name)
            project_ids_by_name[project.name] = await _find_project_id_by_name(
                bus, customer_id, project.name
            )
            continue
        except ProjectCustomerArchivedError:
            # The customer was archived by an earlier run of this function (see below) after
            # this same project was created — re-running against that state hits the
            # customer-active check before the name check ever runs. Confirm the project is
            # indeed already there; otherwise this is a genuine seeding problem, so re-raise.
            if not await _project_exists(bus, customer_id, project.name):
                raise
            report.existing_projects.append(project.name)
            project_ids_by_name[project.name] = await _find_project_id_by_name(
                bus, customer_id, project.name
            )
            continue
        report.created_projects.append(project.name)
        project_ids_by_name[project.name] = created_project.id
        # The project was just created, so it cannot already have these members or billing items.
        for email in project.member_emails:
            await bus.execute(
                AddProjectMember(project_id=created_project.id, user_id=user_ids_by_email[email])
            )
        if project.billing_rates:
            await _apply_demo_billing_rates(bus, created_project.id)
        for demo_item in project.custom_billing_items:
            await bus.execute(
                AddProjectBillingItem(
                    project_id=created_project.id,
                    name=demo_item.name,
                    unit=demo_item.unit,
                    unit_rate=demo_item.unit_rate,
                )
            )
        if project.archived:
            await bus.execute(UpdateProject(project_id=created_project.id, is_active=False))

    for customer in customers:
        if customer.archived:
            await bus.execute(
                UpdateCustomer(
                    customer_id=customer_ids_by_name[customer.create.name], is_active=False
                )
            )

    await _seed_time_entries(bus, report, users, user_ids_by_email, today=today)
    await _seed_expense_reports(bus, report, users, user_ids_by_email, today=today)
    await _seed_sent_invoice(
        bus,
        report,
        users,
        user_ids_by_email,
        project_ids_by_name,
        customer_ids_by_name,
        projects,
        today=today,
    )

    return report
