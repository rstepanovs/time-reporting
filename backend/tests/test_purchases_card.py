"""Card invoices: linking card receipts, their amounts from the card invoice, sums."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import AsyncClient

from support import ACCOUNTANT, AuthHeaders, UserFactory
from test_currency import CCY, FakeRiksbank, install
from time_reporting.core.config import get_settings
from time_reporting.core.cqrs import Bus
from time_reporting.modules.purchases.contracts import (
    AddPurchaseDocument,
    CardInvoiceDTO,
    CardReceiptLink,
    DiscardPurchaseDocument,
    GetCardInvoice,
    LinkCardReceipts,
    ListUnlinkedCardReceipts,
    PaymentMethod,
    PaymentStatus,
    PurchaseDetails,
    PurchaseDocumentDTO,
    PurchaseDocumentStateError,
    PurchaseKind,
    PurchaseValidationError,
    RateSource,
    RegisterPurchaseDocument,
    ReturnPurchaseToInbox,
    UnlinkCardReceipt,
    UpdateCardReceiptAmount,
)
from time_reporting.modules.users.contracts import UserDTO


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    patched = get_settings().model_copy(update={"attachment_dir": str(tmp_path)})
    monkeypatch.setattr("time_reporting.modules.purchases.service.get_settings", lambda: patched)
    install(monkeypatch, FakeRiksbank())


@pytest.fixture
async def accountant(make_user: UserFactory) -> UserDTO:
    return await make_user(roles=ACCOUNTANT)


async def _register(bus: Bus, actor: UserDTO, details: PurchaseDetails) -> PurchaseDocumentDTO:
    inbox = await bus.execute(
        AddPurchaseDocument(
            actor_id=None, file_name="x.pdf", content_type="application/pdf", content=b"%PDF-1"
        )
    )
    return await bus.execute(
        RegisterPurchaseDocument(document_id=inbox.id, actor_id=actor.id, details=details)
    )


async def _card_receipt(
    bus: Bus, actor: UserDTO, day: date = date(2026, 9, 24), amount: str = "10.00"
) -> PurchaseDocumentDTO:
    return await _register(
        bus,
        actor,
        PurchaseDetails(
            kind=PurchaseKind.RECEIPT,
            document_date=day,
            amount=Decimal(amount),
            currency=CCY,
            payment_method=PaymentMethod.CARD,
        ),
    )


async def _card_invoice(bus: Bus, actor: UserDTO, total: str = "300.00") -> PurchaseDocumentDTO:
    return await _register(
        bus,
        actor,
        PurchaseDetails(
            kind=PurchaseKind.CARD_INVOICE,
            document_date=date(2026, 10, 1),
            due_date=date(2026, 10, 25),
            payment_status=PaymentStatus.UNPAID,
            amount=Decimal(total),
            currency="SEK",
        ),
    )


async def _link(
    bus: Bus, actor: UserDTO, invoice: PurchaseDocumentDTO, *pairs: tuple[PurchaseDocumentDTO, str]
) -> CardInvoiceDTO:
    return await bus.execute(
        LinkCardReceipts(
            card_invoice_id=invoice.id,
            actor_id=actor.id,
            links=tuple(CardReceiptLink(receipt_id=r.id, amount_base=Decimal(a)) for r, a in pairs),
        )
    )


async def test_linking_makes_the_amounts_final_and_sums_with_the_difference(
    bus: Bus, accountant: UserDTO
) -> None:
    invoice = await _card_invoice(bus, accountant, total="300.00")
    first = await _card_receipt(bus, accountant)
    second = await _card_receipt(bus, accountant, amount="20.00")
    assert first.amount_base is None

    card_invoice = await _link(bus, accountant, invoice, (first, "112.50"), (second, "187.00"))

    assert {r.id for r in card_invoice.receipts} == {first.id, second.id}
    assert all(r.card_invoice_id == invoice.id for r in card_invoice.receipts)
    assert all(r.rate_source is RateSource.CARD_INVOICE for r in card_invoice.receipts)
    assert all(r.amount_base_final for r in card_invoice.receipts)
    assert card_invoice.receipts_total_base == Decimal("299.50")
    assert card_invoice.difference_base == Decimal("0.50")
    assert await bus.query(GetCardInvoice(card_invoice_id=invoice.id)) == card_invoice


async def test_unlinked_picker_excludes_linked_and_out_of_range_receipts(
    bus: Bus, accountant: UserDTO
) -> None:
    invoice = await _card_invoice(bus, accountant)
    linked = await _card_receipt(bus, accountant)
    early = await _card_receipt(bus, accountant, day=date(2026, 8, 1))
    inside = await _card_receipt(bus, accountant, day=date(2026, 9, 26))
    await _link(bus, accountant, invoice, (linked, "50"))

    picker = await bus.query(
        ListUnlinkedCardReceipts(date_from=date(2026, 9, 1), date_to=date(2026, 9, 30))
    )

    ids = {r.id for r in picker}
    assert inside.id in ids
    assert linked.id not in ids and early.id not in ids


async def test_unlink_returns_the_amount_to_open_and_update_changes_it(
    bus: Bus, accountant: UserDTO
) -> None:
    invoice = await _card_invoice(bus, accountant)
    receipt = await _card_receipt(bus, accountant)
    await _link(bus, accountant, invoice, (receipt, "100"))

    updated = await bus.execute(
        UpdateCardReceiptAmount(
            receipt_id=receipt.id, actor_id=accountant.id, amount_base=Decimal("110.00")
        )
    )
    assert updated.amount_base == Decimal("110.00")

    unlinked = await bus.execute(UnlinkCardReceipt(receipt_id=receipt.id, actor_id=accountant.id))
    assert unlinked.card_invoice_id is None
    assert unlinked.amount_base is None and unlinked.rate_source is None
    assert unlinked.amount_base_final is False
    with pytest.raises(PurchaseDocumentStateError):
        await bus.execute(UnlinkCardReceipt(receipt_id=receipt.id, actor_id=accountant.id))
    with pytest.raises(PurchaseDocumentStateError):
        await bus.execute(
            UpdateCardReceiptAmount(
                receipt_id=receipt.id, actor_id=accountant.id, amount_base=Decimal(5)
            )
        )


async def test_only_card_receipts_link_and_only_once(bus: Bus, accountant: UserDTO) -> None:
    invoice = await _card_invoice(bus, accountant)
    other_invoice = await _card_invoice(bus, accountant)
    transfer = await _register(
        bus,
        accountant,
        PurchaseDetails(
            kind=PurchaseKind.RECEIPT,
            document_date=date(2026, 9, 24),
            amount=Decimal(10),
            currency=CCY,
            payment_method=PaymentMethod.BANK_TRANSFER,
        ),
    )
    receipt = await _card_receipt(bus, accountant)
    good = await _card_receipt(bus, accountant)

    with pytest.raises(PurchaseDocumentStateError):
        await _link(bus, accountant, invoice, (transfer, "10"))
    with pytest.raises(PurchaseDocumentStateError):  # the target must be a card invoice
        await _link(bus, accountant, transfer, (receipt, "10"))
    with pytest.raises(PurchaseValidationError):
        await _link(bus, accountant, invoice, (receipt, "10"), (receipt, "11"))
    with pytest.raises(PurchaseValidationError):
        await _link(bus, accountant, invoice, (receipt, "0"))

    await _link(bus, accountant, invoice, (receipt, "10"))
    with pytest.raises(PurchaseDocumentStateError):  # one card invoice per receipt
        await _link(bus, accountant, other_invoice, (good, "5"), (receipt, "10"))
    # All or nothing: the good receipt of the failed batch stayed unlinked.
    assert (await bus.query(GetCardInvoice(card_invoice_id=other_invoice.id))).receipts == ()


async def test_a_card_invoice_with_receipts_cannot_leave_the_register(
    bus: Bus, accountant: UserDTO
) -> None:
    invoice = await _card_invoice(bus, accountant)
    receipt = await _card_receipt(bus, accountant)
    await _link(bus, accountant, invoice, (receipt, "10"))

    with pytest.raises(PurchaseDocumentStateError):
        await bus.execute(ReturnPurchaseToInbox(document_id=invoice.id, actor_id=accountant.id))
    with pytest.raises(PurchaseDocumentStateError):
        await bus.execute(DiscardPurchaseDocument(document_id=invoice.id, actor_id=accountant.id))

    # A linked receipt that is discarded lets go of the card invoice.
    await bus.execute(DiscardPurchaseDocument(document_id=receipt.id, actor_id=accountant.id))
    assert (await bus.query(GetCardInvoice(card_invoice_id=invoice.id))).receipts == ()
    await bus.execute(ReturnPurchaseToInbox(document_id=invoice.id, actor_id=accountant.id))


async def test_editing_a_linked_receipt_keeps_its_card_amount_and_card_payment(
    bus: Bus, accountant: UserDTO
) -> None:
    from dataclasses import replace

    from time_reporting.modules.purchases.contracts import UpdatePurchaseDocument

    invoice = await _card_invoice(bus, accountant)
    receipt = await _card_receipt(bus, accountant)
    await _link(bus, accountant, invoice, (receipt, "100"))
    details = PurchaseDetails(
        kind=PurchaseKind.RECEIPT,
        vendor="Shop",
        document_date=date(2026, 9, 24),
        amount=Decimal("10.00"),
        currency=CCY,
        payment_method=PaymentMethod.CARD,
    )

    edited = await bus.execute(
        UpdatePurchaseDocument(document_id=receipt.id, actor_id=accountant.id, details=details)
    )
    assert edited.amount_base == Decimal("100.00") and edited.vendor == "Shop"
    with pytest.raises(PurchaseDocumentStateError):
        await bus.execute(
            UpdatePurchaseDocument(
                document_id=receipt.id,
                actor_id=accountant.id,
                details=replace(details, payment_method=PaymentMethod.CASH),
            )
        )


async def test_card_invoice_routes(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers(await make_user(roles=ACCOUNTANT))

    async def register(body: dict[str, object]) -> str:
        uploaded = await client.post(
            "/api/v1/purchases/documents",
            headers=headers,
            files=[("files", ("a.pdf", b"%PDF-1", "application/pdf"))],
        )
        document_id = str(uploaded.json()[0]["id"])
        response = await client.post(
            f"/api/v1/purchases/documents/{document_id}/register", headers=headers, json=body
        )
        assert response.status_code == 200
        return document_id

    invoice_id = await register(
        {
            "kind": "card_invoice",
            "document_date": "2026-10-01",
            "due_date": "2026-10-25",
            "payment_status": "unpaid",
            "amount": "300.00",
            "currency": "SEK",
        }
    )
    receipt_id = await register(
        {
            "kind": "receipt",
            "document_date": "2026-09-24",
            "amount": "10.00",
            "currency": CCY,
            "payment_method": "card",
        }
    )

    picker = await client.get(
        "/api/v1/purchases/card-receipts/unlinked",
        headers=headers,
        params={"date_from": "2026-09-01", "date_to": "2026-09-30"},
    )
    linked = await client.post(
        f"/api/v1/purchases/documents/{invoice_id}/card-receipts",
        headers=headers,
        json={"links": [{"receipt_id": receipt_id, "amount_base": "120.00"}]},
    )
    amount = await client.put(
        f"/api/v1/purchases/documents/{receipt_id}/card-amount",
        headers=headers,
        json={"amount_base": "125.00"},
    )
    shown = await client.get(
        f"/api/v1/purchases/documents/{invoice_id}/card-invoice", headers=headers
    )
    unlinked = await client.post(
        f"/api/v1/purchases/documents/{receipt_id}/unlink-card", headers=headers
    )
    not_a_card_invoice = await client.get(
        f"/api/v1/purchases/documents/{receipt_id}/card-invoice", headers=headers
    )

    assert receipt_id in {item["id"] for item in picker.json()}
    assert linked.status_code == 200
    assert Decimal(linked.json()["difference_base"]) == Decimal("180.00")
    assert Decimal(amount.json()["amount_base"]) == Decimal("125.00")
    assert Decimal(shown.json()["receipts_total_base"]) == Decimal("125.00")
    assert unlinked.json()["card_invoice_id"] is None
    assert not_a_card_invoice.status_code == 409
