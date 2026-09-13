"""Demo data for local development: one user per role and a few customers.

Seeding is idempotent: users whose email or customers whose name already exist are left untouched.
"""

from dataclasses import dataclass, field
from datetime import date

from time_reporting.core.cqrs import Bus
from time_reporting.modules.customers.contracts import (
    BillingAddressDTO,
    BillingIntervalUnit,
    BillingPeriodDTO,
    CreateCustomer,
    CustomerNameAlreadyExistsError,
    UpdateCustomer,
)
from time_reporting.modules.users.contracts import CreateUser, EmailAlreadyExistsError, UserRole

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


@dataclass(slots=True)
class SeedReport:
    created_users: list[str] = field(default_factory=list)
    existing_users: list[str] = field(default_factory=list)
    created_customers: list[str] = field(default_factory=list)
    existing_customers: list[str] = field(default_factory=list)


async def seed_demo_data(
    bus: Bus,
    *,
    password: str = DEFAULT_DEMO_PASSWORD,
    users: tuple[DemoUser, ...] = DEMO_USERS,
    customers: tuple[DemoCustomer, ...] = DEMO_CUSTOMERS,
) -> SeedReport:
    """Create the missing demo records; each one is committed by its own top-level command."""
    report = SeedReport()

    for user in users:
        try:
            await bus.execute(
                CreateUser(name=user.name, email=user.email, role=user.role, password=password)
            )
        except EmailAlreadyExistsError:
            report.existing_users.append(user.email)
        else:
            report.created_users.append(user.email)

    for customer in customers:
        try:
            created = await bus.execute(customer.create)
        except CustomerNameAlreadyExistsError:
            report.existing_customers.append(customer.create.name)
            continue
        if customer.archived:
            await bus.execute(UpdateCustomer(customer_id=created.id, is_active=False))
        report.created_customers.append(customer.create.name)

    return report
