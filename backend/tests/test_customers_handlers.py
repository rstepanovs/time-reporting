from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from support import DEFAULT_BILLING_ADDRESS, DEFAULT_BILLING_PERIOD, CustomerFactory
from time_reporting.core.cqrs import Bus
from time_reporting.modules.customers.contracts import (
    BillingAddressDTO,
    BillingIntervalUnit,
    BillingPeriodDTO,
    CreateCustomer,
    CustomerNameAlreadyExistsError,
    CustomerNotFoundError,
    GetCustomerById,
    GetCustomersByIds,
    ListCustomers,
    UpdateCustomer,
)


async def test_create_customer_normalizes_codes(bus: Bus) -> None:
    period = BillingPeriodDTO(
        interval_count=2, interval_unit=BillingIntervalUnit.WEEK, anchor_date=date(2026, 9, 7)
    )

    customer = await bus.execute(
        CreateCustomer(
            name="Acme",
            legal_name="Acme Corporation Ltd.",
            tax_id="GB123456789",
            billing_email="billing@acme.example",
            billing_address=BillingAddressDTO(
                line1="1 Main Street", city="London", postal_code="EC1A 1BB", country="gb"
            ),
            billing_period=period,
            currency="gbp",
        )
    )

    assert customer.billing_address.country == "GB"
    assert customer.billing_address.line2 is None
    assert customer.billing_period == period
    assert customer.currency == "GBP"
    assert customer.payment_terms_days == 30
    assert customer.is_active
    assert await bus.query(GetCustomerById(customer_id=customer.id)) == customer


async def test_duplicate_name_is_rejected_and_session_stays_usable(
    bus: Bus, make_customer: CustomerFactory
) -> None:
    existing = await make_customer(name="Duplicate")

    with pytest.raises(CustomerNameAlreadyExistsError):
        await make_customer(name="Duplicate")

    assert await bus.query(GetCustomerById(customer_id=existing.id)) == existing


async def test_unknown_customer(bus: Bus) -> None:
    assert await bus.query(GetCustomerById(customer_id=uuid4())) is None

    with pytest.raises(CustomerNotFoundError):
        await bus.execute(UpdateCustomer(customer_id=uuid4(), name="Nobody"))


async def test_update_customer_changes_only_given_fields(
    bus: Bus, make_customer: CustomerFactory
) -> None:
    customer = await make_customer(name="Old Name")
    period = BillingPeriodDTO(
        interval_count=3, interval_unit=BillingIntervalUnit.MONTH, anchor_date=date(2026, 10, 1)
    )

    updated = await bus.execute(
        UpdateCustomer(
            customer_id=customer.id,
            tax_id="DE999999999",
            billing_period=period,
            currency="usd",
            payment_terms_days=14,
        )
    )

    assert updated.name == "Old Name"
    assert updated.billing_address == customer.billing_address
    assert updated.billing_period == period
    assert updated.tax_id == "DE999999999"
    assert updated.currency == "USD"
    assert updated.payment_terms_days == 14
    assert updated.updated_at >= customer.updated_at


async def test_update_customer_clears_listed_fields(bus: Bus) -> None:
    customer = await bus.execute(
        CreateCustomer(
            name="Clearable",
            legal_name="Clearable Ltd.",
            notes="Invoice by post",
            billing_address=DEFAULT_BILLING_ADDRESS,
            billing_period=DEFAULT_BILLING_PERIOD,
            currency="EUR",
        )
    )

    updated = await bus.execute(
        UpdateCustomer(customer_id=customer.id, clear_fields=frozenset({"legal_name"}))
    )

    assert updated.legal_name is None
    assert updated.notes == "Invoice by post"


async def test_rename_to_taken_name_is_rejected(bus: Bus, make_customer: CustomerFactory) -> None:
    await make_customer(name="Taken")
    customer = await make_customer()

    with pytest.raises(CustomerNameAlreadyExistsError):
        await bus.execute(UpdateCustomer(customer_id=customer.id, name="Taken"))


async def test_archived_customers_are_listed_only_on_request(
    bus: Bus, make_customer: CustomerFactory
) -> None:
    active = await make_customer()
    archived = await make_customer()
    await bus.execute(UpdateCustomer(customer_id=archived.id, is_active=False))

    default_page = await bus.query(ListCustomers(limit=100, offset=0))
    full_page = await bus.query(ListCustomers(limit=100, offset=0, include_inactive=True))

    default_ids = {customer.id for customer in default_page.items}
    assert active.id in default_ids
    assert archived.id not in default_ids
    assert {active.id, archived.id} <= {customer.id for customer in full_page.items}
    assert full_page.total == default_page.total + 1


async def test_list_customers_is_paginated_and_ordered_by_name(
    bus: Bus, make_customer: CustomerFactory
) -> None:
    before = (await bus.query(ListCustomers(limit=1, offset=0))).total
    created_ids = {(await make_customer(name=name)).id for name in ("Charlie", "Alpha", "Bravo")}

    page = await bus.query(ListCustomers(limit=2, offset=1))
    everything = await bus.query(ListCustomers(limit=100, offset=0))

    assert page.total == before + 3
    assert (len(page.items), page.limit, page.offset) == (2, 2, 1)
    assert [c.name for c in everything.items if c.id in created_ids] == [
        "Alpha",
        "Bravo",
        "Charlie",
    ]


async def test_database_rejects_non_positive_billing_interval(bus: Bus) -> None:
    period = BillingPeriodDTO(
        interval_count=0, interval_unit=BillingIntervalUnit.DAY, anchor_date=date(2026, 1, 1)
    )

    with pytest.raises(IntegrityError, match="ck_customers_billing_interval_count_positive"):
        await bus.execute(
            CreateCustomer(
                name="Invalid",
                billing_address=DEFAULT_BILLING_ADDRESS,
                billing_period=period,
                currency="EUR",
            )
        )


async def test_get_customers_by_ids_orders_by_name_and_includes_archived(
    bus: Bus, make_customer: CustomerFactory
) -> None:
    zed = await make_customer(name="Zed Customer")
    ann = await make_customer(name="Ann Customer")
    await bus.execute(UpdateCustomer(customer_id=ann.id, is_active=False))

    result = await bus.query(GetCustomersByIds(customer_ids=frozenset({zed.id, ann.id, uuid4()})))

    assert [c.id for c in result] == [ann.id, zed.id]
    assert next(c for c in result if c.id == ann.id).is_active is False


async def test_get_customers_by_ids_with_empty_set_returns_empty(bus: Bus) -> None:
    assert await bus.query(GetCustomersByIds(customer_ids=frozenset())) == ()
