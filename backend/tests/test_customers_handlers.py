from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from support import DEFAULT_BILLING_ADDRESS, DEFAULT_BILLING_PERIOD, CustomerFactory, ProjectFactory
from time_reporting.core.cqrs import Bus
from time_reporting.modules.customers.contracts import (
    BillingAddressDTO,
    BillingIntervalUnit,
    BillingPeriodDTO,
    CreateCustomer,
    CustomerInUseError,
    CustomerNameAlreadyExistsError,
    CustomerNotFoundError,
    DeleteCustomer,
    GetCustomerById,
    GetCustomersByIds,
    InvalidInvoiceLocaleError,
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


async def test_create_and_update_invoicing_fields_round_trip(bus: Bus) -> None:
    customer = await bus.execute(
        CreateCustomer(
            name="Invoicing Fields",
            billing_address=DEFAULT_BILLING_ADDRESS,
            billing_period=DEFAULT_BILLING_PERIOD,
            currency="EUR",
            vat_rate=Decimal("25.00"),
            vat_note="Omvänd betalningsskyldighet / Reverse charge",
            invoice_locale="sv",
            customer_number="CUST-042",
            your_reference="Jane Doe",
        )
    )

    assert customer.vat_rate == Decimal("25.00")
    assert customer.vat_note == "Omvänd betalningsskyldighet / Reverse charge"
    assert customer.invoice_locale == "sv"
    assert customer.customer_number == "CUST-042"
    assert customer.your_reference == "Jane Doe"

    updated = await bus.execute(
        UpdateCustomer(customer_id=customer.id, vat_rate=Decimal("0.00"), invoice_locale="en")
    )

    assert updated.vat_rate == Decimal("0.00")
    assert updated.invoice_locale == "en"
    assert updated.customer_number == "CUST-042"


async def test_create_customer_defaults_invoicing_fields_to_none(bus: Bus) -> None:
    customer = await bus.execute(
        CreateCustomer(
            name="No Invoicing Fields",
            billing_address=DEFAULT_BILLING_ADDRESS,
            billing_period=DEFAULT_BILLING_PERIOD,
            currency="EUR",
        )
    )

    assert customer.vat_rate is None
    assert customer.vat_note is None
    assert customer.invoice_locale is None
    assert customer.customer_number is None
    assert customer.your_reference is None


async def test_update_customer_clears_invoicing_fields(
    bus: Bus, make_customer: CustomerFactory
) -> None:
    customer = await bus.execute(
        UpdateCustomer(
            customer_id=(await make_customer()).id,
            vat_rate=Decimal("25.00"),
            vat_note="Some note",
            invoice_locale="sv",
            customer_number="CUST-1",
            your_reference="Ref",
        )
    )

    cleared = await bus.execute(
        UpdateCustomer(
            customer_id=customer.id,
            clear_fields=frozenset(
                {"vat_rate", "vat_note", "invoice_locale", "customer_number", "your_reference"}
            ),
        )
    )

    assert cleared.vat_rate is None
    assert cleared.vat_note is None
    assert cleared.invoice_locale is None
    assert cleared.customer_number is None
    assert cleared.your_reference is None


async def test_create_customer_rejects_unknown_invoice_locale(bus: Bus) -> None:
    with pytest.raises(InvalidInvoiceLocaleError):
        await bus.execute(
            CreateCustomer(
                name="Bad Locale",
                billing_address=DEFAULT_BILLING_ADDRESS,
                billing_period=DEFAULT_BILLING_PERIOD,
                currency="EUR",
                invoice_locale="xx",
            )
        )


async def test_update_customer_rejects_unknown_invoice_locale(
    bus: Bus, make_customer: CustomerFactory
) -> None:
    customer = await make_customer()

    with pytest.raises(InvalidInvoiceLocaleError):
        await bus.execute(UpdateCustomer(customer_id=customer.id, invoice_locale="xx"))


async def test_database_rejects_vat_rate_out_of_range(bus: Bus) -> None:
    with pytest.raises(IntegrityError, match="ck_customers_vat_rate_range"):
        await bus.execute(
            CreateCustomer(
                name="Bad VAT",
                billing_address=DEFAULT_BILLING_ADDRESS,
                billing_period=DEFAULT_BILLING_PERIOD,
                currency="EUR",
                vat_rate=Decimal("150.00"),
            )
        )


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


async def test_list_customers_filters_by_search_against_name_and_legal_name(
    bus: Bus, make_customer: CustomerFactory
) -> None:
    by_name = await make_customer(name="Searchable Customer")
    by_legal_name = await bus.execute(
        CreateCustomer(
            name="Other Name",
            legal_name="Searchable Legal Entity Ltd.",
            billing_address=DEFAULT_BILLING_ADDRESS,
            billing_period=DEFAULT_BILLING_PERIOD,
            currency="EUR",
        )
    )
    await make_customer(name="Unrelated")

    page = await bus.query(ListCustomers(limit=100, offset=0, search="Searchable"))

    assert {c.id for c in page.items} == {by_name.id, by_legal_name.id}


async def test_list_customers_search_treats_wildcards_as_literal(
    bus: Bus, make_customer: CustomerFactory
) -> None:
    await make_customer(name="100% Match")
    await make_customer(name="Other")

    page = await bus.query(ListCustomers(limit=100, offset=0, search="100% Match"))

    assert [c.name for c in page.items] == ["100% Match"]


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


async def test_delete_customer_removes_the_row(bus: Bus, make_customer: CustomerFactory) -> None:
    customer = await make_customer()

    await bus.execute(DeleteCustomer(customer_id=customer.id))

    assert await bus.query(GetCustomerById(customer_id=customer.id)) is None


async def test_delete_unknown_customer_raises(bus: Bus) -> None:
    with pytest.raises(CustomerNotFoundError):
        await bus.execute(DeleteCustomer(customer_id=uuid4()))


async def test_delete_customer_blocked_by_project(
    bus: Bus, make_customer: CustomerFactory, make_project: ProjectFactory
) -> None:
    customer = await make_customer()
    await make_project(customer_id=customer.id)

    with pytest.raises(CustomerInUseError):
        await bus.execute(DeleteCustomer(customer_id=customer.id))

    assert await bus.query(GetCustomerById(customer_id=customer.id)) is not None
