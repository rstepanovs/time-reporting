from typing import Any

import pytest
from httpx import AsyncClient

from support import ACCOUNTANT, ADMIN, EMPLOYEE, MANAGER, AuthHeaders, UserFactory
from time_reporting.modules.users.contracts import UserRole

_SVG_LOGO = b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"


def _payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "legal_name": "Belt & Braces Software AB",
        "org_number": "556677-8899",
        "vat_number": "SE556677889901",
        "address": {
            "street": "1 Main Street",
            "postal_code": "123 45",
            "city": "Lund",
            "country": "se",
        },
        "email": "info@example.se",
        "phone": "070-000 00 00",
        "registered_office": "Lund",
        "bankgiro": "123-4567",
        "f_tax_approved": True,
        "default_invoice_locale": "sv",
        "invoice_number_prefix": "INV-",
        "next_invoice_number": 42,
        "customer_number_prefix": "CUST-",
        "next_customer_number": 7,
        "allow_self_review": True,
    }
    return payload | overrides


@pytest.mark.parametrize("roles", [ADMIN, ACCOUNTANT])
async def test_admin_or_accountant_can_read(
    client: AsyncClient,
    make_user: UserFactory,
    auth_headers: AuthHeaders,
    roles: frozenset[UserRole],
) -> None:
    headers = auth_headers(await make_user(roles=roles))

    response = await client.get("/api/v1/company", headers=headers)

    assert response.status_code == 200
    assert response.json()["next_invoice_number"] == 1


@pytest.mark.parametrize("roles", [MANAGER, EMPLOYEE])
async def test_others_cannot_read(
    client: AsyncClient,
    make_user: UserFactory,
    auth_headers: AuthHeaders,
    roles: frozenset[UserRole],
) -> None:
    headers = auth_headers(await make_user(roles=roles))

    response = await client.get("/api/v1/company", headers=headers)

    assert response.status_code == 403


async def test_admin_can_replace_settings(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))

    updated = await client.put("/api/v1/company", headers=headers, json=_payload())

    assert updated.status_code == 200
    body = updated.json()
    assert body["legal_name"] == "Belt & Braces Software AB"
    assert body["address"]["country"] == "SE"
    assert body["invoice_number_prefix"] == "INV-"
    assert body["next_invoice_number"] == 42
    assert body["customer_number_prefix"] == "CUST-"
    assert body["next_customer_number"] == 7

    read_back = await client.get("/api/v1/company", headers=headers)
    assert read_back.json() == body


@pytest.mark.parametrize("roles", [ACCOUNTANT, MANAGER, EMPLOYEE])
async def test_only_admin_can_write(
    client: AsyncClient,
    make_user: UserFactory,
    auth_headers: AuthHeaders,
    roles: frozenset[UserRole],
) -> None:
    headers = auth_headers(await make_user(roles=roles))

    response = await client.put("/api/v1/company", headers=headers, json=_payload())

    assert response.status_code == 403


async def test_unknown_locale_is_rejected(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))

    response = await client.put(
        "/api/v1/company", headers=headers, json=_payload(default_invoice_locale="xx")
    )

    assert response.status_code == 422


async def test_logo_round_trip(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    admin_headers = auth_headers(await make_user(roles=ADMIN))
    accountant_headers = auth_headers(await make_user(roles=ACCOUNTANT))

    missing = await client.get("/api/v1/company/logo", headers=admin_headers)
    assert missing.status_code == 404

    uploaded = await client.put(
        "/api/v1/company/logo",
        headers=admin_headers,
        files={"file": ("logo.svg", _SVG_LOGO, "image/svg+xml")},
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["has_logo"] is True

    fetched = await client.get("/api/v1/company/logo", headers=accountant_headers)
    assert fetched.status_code == 200
    assert fetched.content == _SVG_LOGO
    assert fetched.headers["content-type"] == "image/svg+xml"

    cleared = await client.delete("/api/v1/company/logo", headers=admin_headers)
    assert cleared.status_code == 200
    assert cleared.json()["has_logo"] is False


async def test_logo_rejects_disallowed_type(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))

    response = await client.put(
        "/api/v1/company/logo",
        headers=headers,
        files={"file": ("logo.pdf", b"%PDF", "application/pdf")},
    )

    assert response.status_code == 415


async def test_logo_rejects_oversize(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))

    response = await client.put(
        "/api/v1/company/logo",
        headers=headers,
        files={"file": ("logo.png", b"\x00" * (512 * 1024 + 1), "image/png")},
    )

    assert response.status_code == 413


@pytest.mark.parametrize("roles", [ACCOUNTANT, MANAGER, EMPLOYEE])
async def test_only_admin_can_write_logo(
    client: AsyncClient,
    make_user: UserFactory,
    auth_headers: AuthHeaders,
    roles: frozenset[UserRole],
) -> None:
    headers = auth_headers(await make_user(roles=roles))

    response = await client.put(
        "/api/v1/company/logo",
        headers=headers,
        files={"file": ("logo.svg", _SVG_LOGO, "image/svg+xml")},
    )

    assert response.status_code == 403
