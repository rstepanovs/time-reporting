from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient

from support import ADMIN, EMPLOYEE, MANAGER, AuthHeaders, CustomerFactory, UserFactory
from time_reporting.modules.users.contracts import UserRole


def _payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "Acme",
        "billing_address": {
            "line1": "1 Main Street",
            "city": "Berlin",
            "postal_code": "10115",
            "country": "de",
        },
        "billing_period": {
            "interval_count": 1,
            "interval_unit": "month",
            "anchor_date": "2026-09-01",
        },
        "currency": "eur",
    }
    return payload | overrides


@pytest.mark.parametrize("roles", [ADMIN, MANAGER])
async def test_manager_can_create_and_update_customer(
    client: AsyncClient,
    make_user: UserFactory,
    auth_headers: AuthHeaders,
    roles: frozenset[UserRole],
) -> None:
    headers = auth_headers(await make_user(roles=roles))

    created = await client.post(
        "/api/v1/customers", headers=headers, json=_payload(legal_name="Acme GmbH")
    )

    assert created.status_code == 201
    body = created.json()
    assert body["billing_address"]["country"] == "DE"
    assert body["billing_address"]["line2"] is None
    assert body["currency"] == "EUR"
    assert body["payment_terms_days"] == 30
    assert body["is_active"] is True

    updated = await client.patch(
        f"/api/v1/customers/{body['id']}",
        headers=headers,
        json={"legal_name": None, "payment_terms_days": 14},
    )

    assert updated.status_code == 200
    assert updated.json()["legal_name"] is None
    assert updated.json()["payment_terms_days"] == 14
    assert updated.json()["name"] == "Acme"


async def test_customer_number_is_auto_allocated_when_omitted(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))

    first = await client.post("/api/v1/customers", headers=headers, json=_payload(name="Auto 1"))
    second = await client.post("/api/v1/customers", headers=headers, json=_payload(name="Auto 2"))

    assert first.status_code == 201
    assert second.status_code == 201
    first_number = first.json()["customer_number"]
    second_number = second.json()["customer_number"]
    assert first_number is not None
    assert int(second_number) == int(first_number) + 1


async def test_invoicing_fields_round_trip_and_clear(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))

    created = await client.post(
        "/api/v1/customers",
        headers=headers,
        json=_payload(
            vat_rate="25.00",
            vat_note="Reverse charge",
            invoice_locale="sv",
            customer_number="CUST-1",
            your_reference="Jane Doe",
        ),
    )

    assert created.status_code == 201
    body = created.json()
    assert body["vat_rate"] == "25.00"
    assert body["vat_note"] == "Reverse charge"
    assert body["invoice_locale"] == "sv"
    assert body["customer_number"] == "CUST-1"
    assert body["your_reference"] == "Jane Doe"

    cleared = await client.patch(
        f"/api/v1/customers/{body['id']}",
        headers=headers,
        json={
            "vat_rate": None,
            "vat_note": None,
            "invoice_locale": None,
            "customer_number": None,
            "your_reference": None,
        },
    )

    assert cleared.status_code == 200
    cleared_body = cleared.json()
    assert cleared_body["vat_rate"] is None
    assert cleared_body["vat_note"] is None
    assert cleared_body["invoice_locale"] is None
    assert cleared_body["customer_number"] is None
    assert cleared_body["your_reference"] is None


async def test_worker_can_read_but_not_write(
    client: AsyncClient,
    make_user: UserFactory,
    make_customer: CustomerFactory,
    auth_headers: AuthHeaders,
) -> None:
    headers = auth_headers(await make_user(roles=EMPLOYEE))
    customer = await make_customer()
    url = f"/api/v1/customers/{customer.id}"

    listed = await client.get("/api/v1/customers", headers=headers, params={"limit": 100})
    read = await client.get(url, headers=headers)
    created = await client.post("/api/v1/customers", headers=headers, json=_payload())
    updated = await client.patch(url, headers=headers, json={"name": "Renamed"})

    assert listed.status_code == 200
    assert str(customer.id) in {item["id"] for item in listed.json()["items"]}
    assert read.status_code == 200
    assert read.json()["billing_period"]["interval_unit"] == "month"
    assert created.status_code == 403
    assert updated.status_code == 403


async def test_list_customers_supports_search(
    client: AsyncClient,
    make_user: UserFactory,
    make_customer: CustomerFactory,
    auth_headers: AuthHeaders,
) -> None:
    headers = auth_headers(await make_user())
    match = await make_customer(name="Findable Customer")
    await make_customer(name="Unrelated")

    response = await client.get("/api/v1/customers", headers=headers, params={"search": "Findable"})

    assert response.status_code == 200
    assert {item["id"] for item in response.json()["items"]} == {str(match.id)}


async def test_customers_require_authentication(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/customers")).status_code == 401
    assert (await client.post("/api/v1/customers", json=_payload())).status_code == 401


async def test_unknown_customer_returns_404(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))
    url = f"/api/v1/customers/{uuid4()}"

    assert (await client.get(url, headers=headers)).status_code == 404
    assert (await client.patch(url, headers=headers, json={"name": "X"})).status_code == 404


async def test_duplicate_name_returns_409(
    client: AsyncClient,
    make_user: UserFactory,
    make_customer: CustomerFactory,
    auth_headers: AuthHeaders,
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))
    await make_customer(name="Taken")
    other = await make_customer()

    created = await client.post("/api/v1/customers", headers=headers, json=_payload(name="Taken"))
    renamed = await client.patch(
        f"/api/v1/customers/{other.id}", headers=headers, json={"name": "Taken"}
    )

    assert created.status_code == 409
    assert renamed.status_code == 409


@pytest.mark.parametrize(
    "payload",
    [
        _payload(
            billing_address={"line1": "1 Main Street", "city": "Berlin", "country": "Germany"}
        ),
        _payload(currency="euro"),
        _payload(
            billing_period={
                "interval_count": 0,
                "interval_unit": "month",
                "anchor_date": "2026-09-01",
            }
        ),
        _payload(
            billing_period={
                "interval_count": 1,
                "interval_unit": "fortnight",
                "anchor_date": "2026-09-01",
            }
        ),
        _payload(payment_terms_days=-1),
        _payload(unexpected="field"),
        _payload(vat_rate="150.00"),
        _payload(invoice_locale="xx"),
    ],
    ids=[
        "country",
        "currency",
        "interval-count",
        "interval-unit",
        "payment-terms",
        "extra-field",
        "vat-rate",
        "invoice-locale",
    ],
)
async def test_invalid_create_payload_returns_422(
    client: AsyncClient,
    make_user: UserFactory,
    auth_headers: AuthHeaders,
    payload: dict[str, Any],
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))

    response = await client.post("/api/v1/customers", headers=headers, json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize("field", ["name", "billing_address", "currency", "is_active"])
async def test_update_rejects_null_for_required_fields(
    client: AsyncClient,
    make_user: UserFactory,
    make_customer: CustomerFactory,
    auth_headers: AuthHeaders,
    field: str,
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))
    customer = await make_customer()

    response = await client.patch(
        f"/api/v1/customers/{customer.id}", headers=headers, json={field: None}
    )

    assert response.status_code == 422
