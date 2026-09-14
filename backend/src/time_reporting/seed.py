"""Demo data for local development: one user per role, a few customers, and their projects.

Seeding is idempotent: users whose email, customers whose name, or projects whose (customer, name)
already exist are left untouched.
"""

from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from time_reporting.core.cqrs import Bus
from time_reporting.modules.customers.contracts import (
    BillingAddressDTO,
    BillingIntervalUnit,
    BillingPeriodDTO,
    CreateCustomer,
    CustomerNameAlreadyExistsError,
    ListCustomers,
    UpdateCustomer,
)
from time_reporting.modules.projects.contracts import (
    AddProjectMember,
    CreateProject,
    ListProjects,
    ProjectCustomerArchivedError,
    ProjectNameAlreadyExistsError,
    UpdateProject,
)
from time_reporting.modules.users.contracts import (
    CreateUser,
    EmailAlreadyExistsError,
    GetUserCredentialsByEmail,
    UserRole,
)

DEFAULT_DEMO_PASSWORD = "demo-password"


@dataclass(frozen=True, slots=True, kw_only=True)
class DemoUser:
    name: str
    email: str
    role: UserRole


@dataclass(frozen=True, slots=True, kw_only=True)
class DemoCustomer:
    create: CreateCustomer
    archived: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class DemoProject:
    customer_name: str
    name: str
    description: str | None = None
    member_emails: tuple[str, ...] = ()
    archived: bool = False


DEMO_USERS: tuple[DemoUser, ...] = (
    DemoUser(name="Alice Admin", email="admin@example.com", role=UserRole.ADMIN),
    DemoUser(name="Mark Manager", email="manager@example.com", role=UserRole.PROJECT_MANAGER),
    DemoUser(name="Wendy Worker", email="worker@example.com", role=UserRole.WORKER),
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
        member_emails=("manager@example.com", "worker@example.com"),
    ),
    DemoProject(
        customer_name="Acme Corporation",
        name="Internal Tooling",
        description="Roll out time tracking internally.",
        member_emails=("worker@example.com",),
    ),
    DemoProject(
        customer_name="Globex",
        name="Platform Migration",
        description="Move billing to the new platform.",
        member_emails=("manager@example.com",),
    ),
    DemoProject(
        customer_name="Initech",
        name="Legacy Support",
        description="Wind-down support after the contract ended.",
        member_emails=("worker@example.com",),
        archived=True,
    ),
)


@dataclass(slots=True)
class SeedReport:
    created_users: list[str] = field(default_factory=list)
    existing_users: list[str] = field(default_factory=list)
    created_customers: list[str] = field(default_factory=list)
    existing_customers: list[str] = field(default_factory=list)
    created_projects: list[str] = field(default_factory=list)
    existing_projects: list[str] = field(default_factory=list)


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


async def _project_exists(bus: Bus, customer_id: UUID, name: str) -> bool:
    page = await bus.query(
        ListProjects(limit=1, offset=0, customer_id=customer_id, search=name, include_inactive=True)
    )
    return any(project.name == name for project in page.items)


async def seed_demo_data(
    bus: Bus,
    *,
    password: str = DEFAULT_DEMO_PASSWORD,
    users: tuple[DemoUser, ...] = DEMO_USERS,
    customers: tuple[DemoCustomer, ...] = DEMO_CUSTOMERS,
    projects: tuple[DemoProject, ...] = DEMO_PROJECTS,
) -> SeedReport:
    """Create the missing demo records; each one is committed by its own top-level command."""
    report = SeedReport()
    user_ids_by_email: dict[str, UUID] = {}
    customer_ids_by_name: dict[str, UUID] = {}

    for user in users:
        try:
            created_user = await bus.execute(
                CreateUser(name=user.name, email=user.email, role=user.role, password=password)
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
            created_project = await bus.execute(
                CreateProject(
                    customer_id=customer_id, name=project.name, description=project.description
                )
            )
        except ProjectNameAlreadyExistsError:
            report.existing_projects.append(project.name)
            continue
        except ProjectCustomerArchivedError:
            # The customer was archived by an earlier run of this function (see below) after
            # this same project was created — re-running against that state hits the
            # customer-active check before the name check ever runs. Confirm the project is
            # indeed already there; otherwise this is a genuine seeding problem, so re-raise.
            if not await _project_exists(bus, customer_id, project.name):
                raise
            report.existing_projects.append(project.name)
            continue
        report.created_projects.append(project.name)
        # The project was just created, so it cannot already have these members.
        for email in project.member_emails:
            await bus.execute(
                AddProjectMember(project_id=created_project.id, user_id=user_ids_by_email[email])
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

    return report
