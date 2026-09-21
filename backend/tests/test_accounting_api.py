"""HTTP-level tests for the accounting router.

``test_accounting_handlers.py`` exercises ``AccountingService`` directly over the bus, never
through FastAPI's actual routing — so it can't catch a route-declaration-order bug like the one
this file exists to guard against (see ``accounting/CLAUDE.md``'s "HTTP API" section: the `.zip`
route must be declared before the plain status route, or Starlette's unconstrained `{month}`
pattern on the status route greedily swallows a `.zip`-suffixed request first).
"""

import zipfile
from io import BytesIO

from httpx import AsyncClient

from support import ACCOUNTANT, AuthHeaders, UserFactory


async def test_status_and_zip_routes_are_both_reachable(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    accountant = await make_user(roles=ACCOUNTANT)
    headers = auth_headers(accountant)

    status_response = await client.get("/api/v1/accounting/packages/2026/9", headers=headers)
    assert status_response.status_code == 200
    body = status_response.json()
    assert (body["year"], body["month"]) == (2026, 9)

    zip_response = await client.get("/api/v1/accounting/packages/2026/9.zip", headers=headers)
    assert zip_response.status_code == 200
    assert zip_response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(BytesIO(zip_response.content)) as archive:
        # A subset, not an exact match: the test database doubles as the dev database (see
        # `seed-test-data` skill), so a real September 2026 invoice/receipt may already be there.
        assert {"summary.pdf", "summary.xlsx"} <= set(archive.namelist())
