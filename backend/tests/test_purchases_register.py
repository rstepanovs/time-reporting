"""Registering purchase documents: per-kind rules, SEK conversion, Paid/Unpaid, audit."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import AsyncClient

from support import ACCOUNTANT, AuthHeaders, UserFactory
from test_currency import CCY, FakeRiksbank, install
from time_reporting.core.config import get_settings
from time_reporting.core.cqrs import Bus
from time_reporting.modules.audit.contracts import AuditAction, ListAuditEvents
from time_reporting.modules.purchases.contracts import (
    AddPurchaseDocument,
    MarkPurchasePaid,
    MarkPurchaseUnpaid,
    PaymentMethod,
    PaymentStatus,
    PurchaseDetails,
    PurchaseDocumentDTO,
    PurchaseDocumentStateError,
    PurchaseKind,
    PurchaseStage,
    PurchaseValidationError,
    RateSource,
    RegisterPurchaseDocument,
    ReturnPurchaseToInbox,
    UpdatePurchaseDocument,
)
from time_reporting.modules.users.contracts import UserDTO

# FakeRiksbank publishes ZZZ at 11.2645 on 2026-09-24 and 11.29 on 2026-09-25.
MON = date(2026, 9, 24)
TUE = date(2026, 9, 25)


@pytest.fixture(autouse=True)
def _isolated_storage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    patched = get_settings().model_copy(update={"attachment_dir": str(tmp_path)})
    monkeypatch.setattr("time_reporting.modules.purchases.service.get_settings", lambda: patched)


@pytest.fixture(autouse=True)
def _riksbank(monkeypatch: pytest.MonkeyPatch) -> FakeRiksbank:
    return install(monkeypatch, FakeRiksbank())


@pytest.fixture
async def accountant(make_user: UserFactory) -> UserDTO:
    return await make_user(roles=ACCOUNTANT)


async def _inbox(bus: Bus) -> PurchaseDocumentDTO:
    return await bus.execute(
        AddPurchaseDocument(
            actor_id=None, file_name="scan.pdf", content_type="application/pdf", content=b"%PDF-1"
        )
    )


def _invoice(**overrides: object) -> PurchaseDetails:
    fields: dict[str, object] = {
        "kind": PurchaseKind.INVOICE,
        "vendor": "Acme",
        "document_no": "F-1",
        "document_date": MON,
        "due_date": date(2026, 10, 24),
        "payment_status": PaymentStatus.UNPAID,
        "amount": Decimal("100.00"),
        "currency": CCY,
    }
    return PurchaseDetails(**{**fields, **overrides})  # type: ignore[arg-type]


def _receipt(**overrides: object) -> PurchaseDetails:
    fields: dict[str, object] = {
        "kind": PurchaseKind.RECEIPT,
        "vendor": "Shop",
        "document_date": TUE,
        "amount": Decimal("100.00"),
        "currency": CCY,
        "payment_method": PaymentMethod.BANK_TRANSFER,
    }
    return PurchaseDetails(**{**fields, **overrides})  # type: ignore[arg-type]


async def _register(bus: Bus, accountant: UserDTO, details: PurchaseDetails) -> PurchaseDocumentDTO:
    document = await _inbox(bus)
    return await bus.execute(
        RegisterPurchaseDocument(document_id=document.id, actor_id=accountant.id, details=details)
    )


# --- Per-kind rules ---


async def test_receipt_is_paid_on_the_purchase_date_at_that_days_rate(
    bus: Bus, accountant: UserDTO
) -> None:
    document = await _register(bus, accountant, _receipt())

    assert document.stage is PurchaseStage.REGISTERED
    assert document.payment_status is PaymentStatus.PAID
    assert document.paid_on == TUE
    assert document.exchange_rate == Decimal("11.29")
    assert document.amount_base == Decimal("1129.00")
    assert document.rate_source is RateSource.RIKSBANK
    assert document.amount_base_final is True


@pytest.mark.parametrize(
    "details",
    [
        _receipt(payment_method=None),
        _receipt(amount=None),
        _receipt(due_date=date(2026, 10, 1)),
        _receipt(payment_status=PaymentStatus.UNPAID),
        _invoice(due_date=None),
        _invoice(paid_on=TUE),
        _invoice(payment_status=PaymentStatus.PAID, paid_on=TUE),  # paid needs a method
        _invoice(
            kind=PurchaseKind.CARD_INVOICE,
            payment_status=PaymentStatus.PAID,
            paid_on=TUE,
            payment_method=PaymentMethod.CARD,
        ),
        _invoice(amount=Decimal(0)),
        _invoice(currency="SEKK"),
        _invoice(amount_base=Decimal(5), exchange_rate=Decimal(2)),
        PurchaseDetails(kind=PurchaseKind.OTHER, amount=Decimal(1), currency="SEK"),
    ],
)
async def test_invalid_fields_are_rejected(
    bus: Bus, accountant: UserDTO, details: PurchaseDetails
) -> None:
    document = await _inbox(bus)

    with pytest.raises(PurchaseValidationError):
        await bus.execute(
            RegisterPurchaseDocument(
                document_id=document.id, actor_id=accountant.id, details=details
            )
        )


async def test_other_documents_carry_no_amounts(bus: Bus, accountant: UserDTO) -> None:
    document = await _register(
        bus, accountant, PurchaseDetails(kind=PurchaseKind.OTHER, description="Contract")
    )

    assert document.amount_base is None and document.rate_source is None


async def test_only_an_inbox_document_can_be_registered(bus: Bus, accountant: UserDTO) -> None:
    document = await _register(bus, accountant, _invoice())

    with pytest.raises(PurchaseDocumentStateError):
        await bus.execute(
            RegisterPurchaseDocument(
                document_id=document.id, actor_id=accountant.id, details=_invoice()
            )
        )


# --- Conversion ---


async def test_unpaid_invoice_is_provisional_at_the_document_date(
    bus: Bus, accountant: UserDTO
) -> None:
    document = await _register(bus, accountant, _invoice())

    assert document.exchange_rate == Decimal("11.2645")
    assert document.amount_base == Decimal("1126.45")
    assert document.amount_base_final is False


async def test_paid_becomes_final_at_the_payment_date_rate_and_unpaid_reverts(
    bus: Bus, accountant: UserDTO
) -> None:
    document = await _register(bus, accountant, _invoice())

    paid = await bus.execute(
        MarkPurchasePaid(
            document_id=document.id,
            actor_id=accountant.id,
            paid_on=TUE,
            payment_method=PaymentMethod.BANK_TRANSFER,
        )
    )
    assert paid.payment_status is PaymentStatus.PAID
    assert paid.amount_base == Decimal("1129.00")
    assert paid.rate_date == TUE
    assert paid.amount_base_final is True

    unpaid = await bus.execute(MarkPurchaseUnpaid(document_id=document.id, actor_id=accountant.id))
    assert unpaid.payment_status is PaymentStatus.UNPAID
    assert unpaid.paid_on is None and unpaid.payment_method is None
    assert unpaid.amount_base == Decimal("1126.45")
    assert unpaid.amount_base_final is False


async def test_paid_with_the_actual_debited_amount_is_manual_and_survives_unpaid(
    bus: Bus, accountant: UserDTO
) -> None:
    document = await _register(bus, accountant, _invoice())

    paid = await bus.execute(
        MarkPurchasePaid(
            document_id=document.id,
            actor_id=accountant.id,
            paid_on=TUE,
            payment_method=PaymentMethod.BANK_TRANSFER,
            amount_base=Decimal("1140.00"),
        )
    )
    assert paid.rate_source is RateSource.MANUAL
    assert paid.amount_base == Decimal("1140.00")
    assert paid.exchange_rate == Decimal("11.40000000")
    assert paid.amount_base_final is True

    unpaid = await bus.execute(MarkPurchaseUnpaid(document_id=document.id, actor_id=accountant.id))
    assert unpaid.amount_base == Decimal("1140.00")
    assert unpaid.amount_base_final is False


async def test_a_manual_rate_survives_edits_until_the_amount_changes(
    bus: Bus, accountant: UserDTO
) -> None:
    document = await _register(bus, accountant, _invoice(exchange_rate=Decimal("12")))
    assert document.amount_base == Decimal("1200.00")

    edited = await bus.execute(
        UpdatePurchaseDocument(
            document_id=document.id,
            actor_id=accountant.id,
            details=_invoice(vendor="Acme AB"),
        )
    )
    assert edited.vendor == "Acme AB"
    assert edited.rate_source is RateSource.MANUAL and edited.amount_base == Decimal("1200.00")

    changed = await bus.execute(
        UpdatePurchaseDocument(
            document_id=document.id,
            actor_id=accountant.id,
            details=_invoice(amount=Decimal("200.00")),
        )
    )
    assert changed.rate_source is RateSource.RIKSBANK
    assert changed.amount_base == Decimal("2252.90")


async def test_base_currency_amounts_need_no_rate(bus: Bus, accountant: UserDTO) -> None:
    document = await _register(bus, accountant, _invoice(currency="SEK"))

    assert document.amount_base == Decimal("100.00")
    assert document.rate_source is RateSource.NONE


async def test_card_receipts_stay_unconverted(bus: Bus, accountant: UserDTO) -> None:
    document = await _register(bus, accountant, _receipt(payment_method=PaymentMethod.CARD))

    assert document.amount_base is None and document.rate_source is None


async def test_an_unavailable_rate_leaves_the_amount_open(
    bus: Bus, accountant: UserDTO, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(monkeypatch, FakeRiksbank(status=204))

    document = await _register(bus, accountant, _invoice())

    assert document.stage is PurchaseStage.REGISTERED
    assert document.amount_base is None and document.rate_source is None


# --- Paid / Unpaid rules, return to inbox, audit ---


async def test_paid_and_unpaid_are_only_for_invoices_in_the_right_state(
    bus: Bus, accountant: UserDTO
) -> None:
    receipt = await _register(bus, accountant, _receipt())
    invoice = await _register(bus, accountant, _invoice())
    pay = {"actor_id": accountant.id, "paid_on": TUE, "payment_method": PaymentMethod.CASH}

    with pytest.raises(PurchaseDocumentStateError):
        await bus.execute(MarkPurchasePaid(document_id=receipt.id, **pay))  # type: ignore[arg-type]
    with pytest.raises(PurchaseDocumentStateError):
        await bus.execute(MarkPurchaseUnpaid(document_id=invoice.id, actor_id=accountant.id))
    await bus.execute(MarkPurchasePaid(document_id=invoice.id, **pay))  # type: ignore[arg-type]
    with pytest.raises(PurchaseDocumentStateError):
        await bus.execute(MarkPurchasePaid(document_id=invoice.id, **pay))  # type: ignore[arg-type]


async def test_return_to_inbox_clears_the_classification(bus: Bus, accountant: UserDTO) -> None:
    document = await _register(bus, accountant, _invoice())

    back = await bus.execute(ReturnPurchaseToInbox(document_id=document.id, actor_id=accountant.id))

    assert back.stage is PurchaseStage.INBOX
    assert back.kind is None and back.vendor is None and back.amount is None
    assert back.amount_base is None and back.rate_source is None
    assert back.file_name == "scan.pdf"
    again = await bus.execute(
        RegisterPurchaseDocument(
            document_id=document.id, actor_id=accountant.id, details=replace(_invoice(), vendor="B")
        )
    )
    assert again.vendor == "B"


async def test_registration_payment_and_discard_are_audited(bus: Bus, accountant: UserDTO) -> None:
    from time_reporting.modules.purchases.contracts import DiscardPurchaseDocument

    document = await _register(bus, accountant, _invoice())
    await bus.execute(
        MarkPurchasePaid(
            document_id=document.id,
            actor_id=accountant.id,
            paid_on=TUE,
            payment_method=PaymentMethod.BANK_TRANSFER,
        )
    )
    await bus.execute(MarkPurchaseUnpaid(document_id=document.id, actor_id=accountant.id))
    await bus.execute(DiscardPurchaseDocument(document_id=document.id, actor_id=accountant.id))

    page = await bus.query(
        ListAuditEvents(
            limit=50, offset=0, entity_type="purchase_document", entity_id=str(document.id)
        )
    )

    assert {event.action for event in page.items} == {
        AuditAction.PURCHASE_REGISTERED,
        AuditAction.PURCHASE_PAID,
        AuditAction.PURCHASE_UNPAID,
        AuditAction.PURCHASE_DISCARDED,
    }


# --- HTTP ---


async def test_register_pay_and_validation_over_http(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers(await make_user(roles=ACCOUNTANT))
    uploaded = await client.post(
        "/api/v1/purchases/documents",
        headers=headers,
        files=[("files", ("a.pdf", b"%PDF-1", "application/pdf"))],
    )
    document_id = uploaded.json()[0]["id"]
    base = f"/api/v1/purchases/documents/{document_id}"

    invalid = await client.post(
        f"{base}/register", headers=headers, json={"kind": "invoice", "amount": "10.00"}
    )
    registered = await client.post(
        f"{base}/register",
        headers=headers,
        json={
            "kind": "invoice",
            "document_date": "2026-09-24",
            "due_date": "2026-10-24",
            "payment_status": "unpaid",
            "amount": "100.00",
            "currency": CCY.lower(),
            "vendor": "Acme",
        },
    )
    paid = await client.post(
        f"{base}/paid",
        headers=headers,
        json={"paid_on": "2026-09-25", "payment_method": "bank_transfer"},
    )
    paid_again = await client.post(
        f"{base}/paid",
        headers=headers,
        json={"paid_on": "2026-09-25", "payment_method": "bank_transfer"},
    )
    unpaid = await client.post(f"{base}/unpaid", headers=headers)
    back = await client.post(f"{base}/return-to-inbox", headers=headers)

    assert invalid.status_code == 400
    assert registered.status_code == 200
    assert registered.json()["currency"] == CCY
    assert Decimal(registered.json()["amount_base"]) == Decimal("1126.45")
    assert paid.json()["payment_status"] == "paid"
    assert paid_again.status_code == 409
    assert unpaid.json()["payment_status"] == "unpaid"
    assert back.json()["stage"] == "inbox"
