"""The dashboard summary and the month list the accountant package reads."""

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import AsyncClient

from support import ACCOUNTANT, EMPLOYEE, AuthHeaders, UserFactory
from test_currency import CCY, FakeRiksbank, install
from time_reporting.core.config import get_settings
from time_reporting.core.cqrs import Bus
from time_reporting.modules.purchases.contracts import (
    AddPurchaseDocument,
    CardReceiptLink,
    GetPurchasesSummary,
    LinkCardReceipts,
    ListMonthPurchases,
    MarkPurchasePaid,
    PaymentMethod,
    PaymentStatus,
    PurchaseDetails,
    PurchaseDocumentDTO,
    PurchaseKind,
    RegisterPurchaseDocument,
)
from time_reporting.modules.users.contracts import UserDTO

TODAY = date(2031, 3, 15)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    patched = get_settings().model_copy(update={"attachment_dir": str(tmp_path)})
    monkeypatch.setattr("time_reporting.modules.purchases.service.get_settings", lambda: patched)
    install(monkeypatch, FakeRiksbank())


@pytest.fixture
async def accountant(make_user: UserFactory) -> UserDTO:
    return await make_user(roles=ACCOUNTANT)


async def _inbox(bus: Bus) -> PurchaseDocumentDTO:
    return await bus.execute(
        AddPurchaseDocument(
            actor_id=None, file_name="x.pdf", content_type="application/pdf", content=b"%PDF-1"
        )
    )


async def _register(bus: Bus, actor: UserDTO, details: PurchaseDetails) -> PurchaseDocumentDTO:
    document = await _inbox(bus)
    return await bus.execute(
        RegisterPurchaseDocument(document_id=document.id, actor_id=actor.id, details=details)
    )


def _unpaid(due: date, *, currency: str = "SEK", amount: str = "100.00") -> PurchaseDetails:
    return PurchaseDetails(
        kind=PurchaseKind.INVOICE,
        document_date=date(2031, 3, 1),
        due_date=due,
        payment_status=PaymentStatus.UNPAID,
        amount=Decimal(amount),
        currency=currency,
    )


async def test_summary_counts_inbox_unpaid_overdue_and_due_soon(
    bus: Bus, accountant: UserDTO
) -> None:
    before = await bus.query(GetPurchasesSummary(today=TODAY))
    await _inbox(bus)
    await _register(bus, accountant, _unpaid(TODAY - timedelta(days=1)))  # overdue
    await _register(bus, accountant, _unpaid(TODAY))  # due soon (today counts)
    await _register(bus, accountant, _unpaid(TODAY + timedelta(days=6)))  # due soon (last day)
    await _register(bus, accountant, _unpaid(TODAY + timedelta(days=7)))  # later
    paid = await _register(bus, accountant, _unpaid(TODAY - timedelta(days=30)))
    await bus.execute(
        MarkPurchasePaid(
            document_id=paid.id,
            actor_id=accountant.id,
            paid_on=TODAY,
            payment_method=PaymentMethod.BANK_TRANSFER,
        )
    )

    after = await bus.query(GetPurchasesSummary(today=TODAY))

    assert after.inbox_count - before.inbox_count == 1
    assert after.unpaid_count - before.unpaid_count == 4
    assert after.overdue_count - before.overdue_count == 1
    assert after.due_soon_count - before.due_soon_count == 2
    assert after.unpaid_total_base - before.unpaid_total_base == Decimal("400.00")
    assert after.base_currency == "SEK"


async def test_summary_marks_provisional_and_unconverted_amounts(
    bus: Bus, accountant: UserDTO, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = await bus.query(GetPurchasesSummary(today=TODAY))
    # Converted, but an unpaid document's amount is only an estimate (the fake bank's latest
    # rate, 11.29, applies to any later date).
    await _register(bus, accountant, _unpaid(TODAY, currency=CCY))
    install(monkeypatch, FakeRiksbank(status=204))
    await _register(bus, accountant, _unpaid(TODAY, currency="QQQ"))

    after = await bus.query(GetPurchasesSummary(today=TODAY))

    assert after.unpaid_provisional is True
    assert after.unpaid_unconverted_count - before.unpaid_unconverted_count == 1
    assert after.unpaid_total_base - before.unpaid_total_base == Decimal("1129.00")


async def test_month_list_groups_card_receipts_under_their_card_invoice(
    bus: Bus, accountant: UserDTO
) -> None:
    def receipt(day: date, method: PaymentMethod) -> PurchaseDetails:
        return PurchaseDetails(
            kind=PurchaseKind.RECEIPT,
            document_date=day,
            amount=Decimal("10.00"),
            currency="SEK",
            payment_method=method,
        )

    card_invoice = await _register(
        bus,
        accountant,
        PurchaseDetails(
            kind=PurchaseKind.CARD_INVOICE,
            document_date=date(2031, 4, 2),
            due_date=date(2031, 4, 25),
            payment_status=PaymentStatus.UNPAID,
            amount=Decimal("50.00"),
            currency="SEK",
        ),
    )
    linked = await _register(bus, accountant, receipt(date(2031, 3, 20), PaymentMethod.CARD))
    loose_card = await _register(bus, accountant, receipt(date(2031, 4, 5), PaymentMethod.CARD))
    cash = await _register(bus, accountant, receipt(date(2031, 4, 9), PaymentMethod.CASH))
    await _register(bus, accountant, receipt(date(2031, 5, 1), PaymentMethod.CASH))  # other month
    await _inbox(bus)  # undated, never listed
    await bus.execute(
        LinkCardReceipts(
            card_invoice_id=card_invoice.id,
            actor_id=accountant.id,
            links=(CardReceiptLink(receipt_id=linked.id, amount_base=Decimal("45.00")),),
        )
    )

    april = await bus.query(ListMonthPurchases(year=2031, month=4))
    march = await bus.query(ListMonthPurchases(year=2031, month=3))

    assert [e.document.id for e in april] == [card_invoice.id, loose_card.id, cash.id]
    assert [r.id for r in april[0].card_receipts] == [linked.id]
    assert april[1].card_receipts == ()
    # The March receipt belongs to April's card invoice, so March lists nothing.
    assert march == ()


async def test_summary_and_month_routes_are_for_accountants(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    accountant = auth_headers(await make_user(roles=ACCOUNTANT))
    employee = auth_headers(await make_user(roles=EMPLOYEE))

    summary = await client.get(
        "/api/v1/purchases/summary", headers=accountant, params={"today": "2031-03-15"}
    )
    month = await client.get("/api/v1/purchases/months/2031/3", headers=accountant)

    assert summary.status_code == 200
    assert summary.json()["base_currency"] == "SEK"
    assert month.json() == []
    for url in ("/api/v1/purchases/summary", "/api/v1/purchases/months/2031/3"):
        assert (await client.get(url, headers=employee)).status_code == 403
