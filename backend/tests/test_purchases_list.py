"""Filtering, sorting and paging the purchase list."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import AsyncClient

from support import ACCOUNTANT, AuthHeaders, UserFactory
from time_reporting.core.config import get_settings
from time_reporting.core.cqrs import Bus
from time_reporting.modules.purchases.contracts import (
    AddPurchaseDocument,
    ListPurchaseDocuments,
    PaymentMethod,
    PaymentStatus,
    PurchaseDetails,
    PurchaseDocumentDTO,
    PurchaseKind,
    PurchaseSort,
    PurchaseStage,
    RegisterPurchaseDocument,
)
from time_reporting.modules.users.contracts import UserDTO

# A year no other test's data uses, so the date filters isolate this file's documents.
YEAR = 2033


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    patched = get_settings().model_copy(update={"attachment_dir": str(tmp_path)})
    monkeypatch.setattr("time_reporting.modules.purchases.service.get_settings", lambda: patched)


async def _register(bus: Bus, actor: UserDTO, details: PurchaseDetails) -> PurchaseDocumentDTO:
    inbox = await bus.execute(
        AddPurchaseDocument(
            actor_id=None, file_name="x.pdf", content_type="application/pdf", content=b"%PDF-1"
        )
    )
    return await bus.execute(
        RegisterPurchaseDocument(document_id=inbox.id, actor_id=actor.id, details=details)
    )


def _invoice(vendor: str, doc_date: date, due: date) -> PurchaseDetails:
    return PurchaseDetails(
        kind=PurchaseKind.INVOICE,
        vendor=vendor,
        document_no=f"N-{vendor}",
        description="Consulting_work 100%",
        document_date=doc_date,
        due_date=due,
        payment_status=PaymentStatus.UNPAID,
        amount=Decimal("10.00"),
        currency="SEK",
    )


async def _seed(bus: Bus, actor: UserDTO) -> dict[str, PurchaseDocumentDTO]:
    return {
        "late": await _register(bus, actor, _invoice("Zeta", date(YEAR, 1, 10), date(YEAR, 3, 1))),
        "early": await _register(bus, actor, _invoice("Alfa", date(YEAR, 2, 5), date(YEAR, 2, 1))),
        "receipt": await _register(
            bus,
            actor,
            PurchaseDetails(
                kind=PurchaseKind.RECEIPT,
                vendor="Shop",
                document_date=date(YEAR, 3, 7),
                amount=Decimal("5.00"),
                currency="SEK",
                payment_method=PaymentMethod.CASH,
            ),
        ),
    }


async def _ids(bus: Bus, **filters: object) -> list[object]:
    page = await bus.query(
        ListPurchaseDocuments(
            date_from=date(YEAR, 1, 1),
            date_to=date(YEAR, 12, 31),
            **filters,  # type: ignore[arg-type]
        )
    )
    return [item.id for item in page.items]


async def test_filters_by_kind_and_payment_status(bus: Bus, make_user: UserFactory) -> None:
    actor = await make_user(roles=ACCOUNTANT)
    docs = await _seed(bus, actor)

    assert set(await _ids(bus, kind=PurchaseKind.RECEIPT)) == {docs["receipt"].id}
    assert set(await _ids(bus, payment_status=PaymentStatus.UNPAID)) == {
        docs["late"].id,
        docs["early"].id,
    }
    assert len(await _ids(bus, stage=PurchaseStage.REGISTERED)) == 3
    assert await _ids(bus, stage=PurchaseStage.INBOX) == []


async def test_searches_vendor_number_and_description_literally(
    bus: Bus, make_user: UserFactory
) -> None:
    actor = await make_user(roles=ACCOUNTANT)
    docs = await _seed(bus, actor)

    assert await _ids(bus, search="alfa") == [docs["early"].id]  # case-insensitive vendor
    assert await _ids(bus, search="N-Zeta") == [docs["late"].id]  # document number
    assert len(await _ids(bus, search="work 100%")) == 2  # description, `%` taken literally
    assert await _ids(bus, search="_") != []  # `_` literal: matches "Consulting_work" only
    assert await _ids(bus, search="nothing like this") == []


async def test_sorts_by_due_date_and_document_date(bus: Bus, make_user: UserFactory) -> None:
    actor = await make_user(roles=ACCOUNTANT)
    docs = await _seed(bus, actor)

    by_due = await _ids(bus, sort=PurchaseSort.DUE_DATE)
    by_date = await _ids(bus, sort=PurchaseSort.DOCUMENT_DATE)

    # Earliest due first; the receipt has no due date and goes last.
    assert by_due == [docs["early"].id, docs["late"].id, docs["receipt"].id]
    assert by_date == [docs["receipt"].id, docs["early"].id, docs["late"].id]


async def test_pages_with_a_total(bus: Bus, make_user: UserFactory) -> None:
    actor = await make_user(roles=ACCOUNTANT)
    await _seed(bus, actor)
    window = {"date_from": date(YEAR, 1, 1), "date_to": date(YEAR, 12, 31)}

    first = await bus.query(ListPurchaseDocuments(limit=2, offset=0, **window))  # type: ignore[arg-type]
    second = await bus.query(ListPurchaseDocuments(limit=2, offset=2, **window))  # type: ignore[arg-type]

    assert (first.total, len(first.items), len(second.items)) == (3, 2, 1)
    assert {i.id for i in first.items}.isdisjoint({i.id for i in second.items})


async def test_the_list_route_takes_the_filters(
    client: AsyncClient, bus: Bus, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    actor = await make_user(roles=ACCOUNTANT)
    docs = await _seed(bus, actor)

    response = await client.get(
        "/api/v1/purchases/documents",
        headers=auth_headers(actor),
        params={
            "stage": "registered",
            "payment_status": "unpaid",
            "sort": "due_date",
            "search": "alfa",
            "date_from": f"{YEAR}-01-01",
            "date_to": f"{YEAR}-12-31",
            "limit": 10,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1 and body["limit"] == 10 and body["offset"] == 0
    assert [item["id"] for item in body["items"]] == [str(docs["early"].id)]
