"""Rebilling a purchase to a project through the accountant's own expense report."""

from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import AsyncClient

from support import ACCOUNTANT, AuthHeaders, ProjectFactory, UserFactory
from test_currency import FakeRiksbank, install
from time_reporting.core.config import get_settings
from time_reporting.core.cqrs import Bus
from time_reporting.modules.audit.contracts import AuditAction, ListAuditEvents
from time_reporting.modules.expenses.contracts import (
    ExpenseLineChange,
    ExpenseReportDTO,
    GetAttachmentPath,
    GetExpenseReport,
    SaveExpenseReportLines,
    SubmitExpenseReport,
)
from time_reporting.modules.projects.contracts import (
    BillingItemPreset,
    ListProjectBillingItems,
    ProjectDTO,
)
from time_reporting.modules.purchases.contracts import (
    AddPurchaseDocument,
    PaymentMethod,
    PurchaseDetails,
    PurchaseDocumentDTO,
    PurchaseDocumentStateError,
    PurchaseKind,
    PurchaseValidationError,
    RebillPurchase,
    RegisterPurchaseDocument,
    ReturnPurchaseToInbox,
    SuggestRebillAmount,
    UpdatePurchaseDocument,
)
from time_reporting.modules.users.contracts import UserDTO

# The project's customer is billed in EUR; FakeRiksbank publishes every currency at 11.29 SEK on
# 2026-09-25, so EUR 100 is SEK 1129.00 and back.
DAY = date(2026, 9, 25)
PDF = b"%PDF-1.4 receipt"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    patched = get_settings().model_copy(update={"attachment_dir": str(tmp_path)})
    monkeypatch.setattr("time_reporting.modules.purchases.service.get_settings", lambda: patched)
    monkeypatch.setattr("time_reporting.modules.expenses.service.get_settings", lambda: patched)
    install(monkeypatch, FakeRiksbank())


@pytest.fixture
async def accountant(make_user: UserFactory) -> UserDTO:
    return await make_user(roles=ACCOUNTANT)


async def _expense_item_id(bus: Bus, project: ProjectDTO) -> object:
    items = await bus.query(ListProjectBillingItems(project_id=project.id))
    return next(i.id for i in items if i.preset is BillingItemPreset.PURCHASING_EXPENSES)


async def _receipt(
    bus: Bus, actor: UserDTO, *, currency: str = "EUR", amount: str = "100.00", day: date = DAY
) -> PurchaseDocumentDTO:
    inbox = await bus.execute(
        AddPurchaseDocument(
            actor_id=None, file_name="r.pdf", content_type="application/pdf", content=PDF
        )
    )
    return await bus.execute(
        RegisterPurchaseDocument(
            document_id=inbox.id,
            actor_id=actor.id,
            details=PurchaseDetails(
                kind=PurchaseKind.RECEIPT,
                vendor="Hotel AB",
                document_no="R-7",
                document_date=day,
                amount=Decimal(amount),
                currency=currency,
                payment_method=PaymentMethod.BANK_TRANSFER,
            ),
        )
    )


def _rebill(
    document: PurchaseDocumentDTO,
    actor: UserDTO,
    project: ProjectDTO,
    item_id: object,
    **overrides: object,
) -> RebillPurchase:
    fields: dict[str, object] = {
        "document_id": document.id,
        "actor_id": actor.id,
        "project_id": project.id,
        "year": 2026,
        "month": 9,
        "billing_item_id": item_id,
        "description": "Hotel for the workshop",
    }
    return RebillPurchase(**{**fields, **overrides})  # type: ignore[arg-type]


async def test_rebilling_copies_the_file_onto_the_actors_report(
    bus: Bus, make_project: ProjectFactory, accountant: UserDTO
) -> None:
    project = await make_project()
    item_id = await _expense_item_id(bus, project)
    document = await _receipt(bus, accountant)

    rebilled = await bus.execute(_rebill(document, accountant, project, item_id))

    assert rebilled.rebilled_expense_line_id is not None
    events = await bus.query(
        ListAuditEvents(
            limit=10,
            offset=0,
            action=AuditAction.PURCHASE_REBILLED,
            entity_id=str(document.id),
        )
    )
    assert len(events.items) == 1
    report_id = uuid_of(events.items[0].details, "expense_report_id")
    report = await bus.query(GetExpenseReport(report_id=report_id, viewer_id=accountant.id))
    assert report.user.id == accountant.id
    (line,) = report.lines
    assert (line.amount, line.vendor, line.document_no) == (Decimal("100.00"), "Hotel AB", "R-7")
    assert line.expense_date == DAY
    (attachment,) = report.attachments
    assert attachment.line_id == line.id
    file = await bus.query(GetAttachmentPath(attachment_id=attachment.id, viewer_id=accountant.id))
    assert file.path.read_bytes() == PDF
    assert rebilled.rebilled_expense_line_id == line.id
    assert rebilled.rebilled_expense_report_id == report_id


def uuid_of(details: dict[str, object] | None, key: str):  # type: ignore[no-untyped-def]
    from uuid import UUID

    assert details is not None
    return UUID(str(details[key]))


async def test_a_second_rebill_in_the_same_month_adds_to_the_same_report(
    bus: Bus, make_project: ProjectFactory, accountant: UserDTO
) -> None:
    project = await make_project()
    item_id = await _expense_item_id(bus, project)
    first = await _receipt(bus, accountant)
    second = await _receipt(bus, accountant, amount="50.00")
    await bus.execute(_rebill(first, accountant, project, item_id))
    await bus.execute(_rebill(second, accountant, project, item_id))

    events = await bus.query(
        ListAuditEvents(limit=10, offset=0, action=AuditAction.PURCHASE_REBILLED)
    )
    report_ids = {
        e.details["expense_report_id"]
        for e in events.items
        if e.details and e.entity_id in {str(first.id), str(second.id)}
    }
    assert len(report_ids) == 1
    report: ExpenseReportDTO = await bus.query(
        GetExpenseReport(report_id=uuid_of({"x": report_ids.pop()}, "x"), viewer_id=accountant.id)
    )
    assert [line.amount for line in report.lines] == [Decimal("100.00"), Decimal("50.00")]
    assert len(report.attachments) == 2


async def test_rebilled_documents_are_frozen(
    bus: Bus, make_project: ProjectFactory, accountant: UserDTO
) -> None:
    project = await make_project()
    item_id = await _expense_item_id(bus, project)
    document = await _receipt(bus, accountant)
    await bus.execute(_rebill(document, accountant, project, item_id))

    with pytest.raises(PurchaseDocumentStateError):
        await bus.execute(_rebill(document, accountant, project, item_id))
    with pytest.raises(PurchaseDocumentStateError):
        await bus.execute(ReturnPurchaseToInbox(document_id=document.id, actor_id=accountant.id))
    with pytest.raises(PurchaseDocumentStateError):
        await bus.execute(
            UpdatePurchaseDocument(
                document_id=document.id,
                actor_id=accountant.id,
                details=PurchaseDetails(
                    kind=PurchaseKind.RECEIPT,
                    document_date=DAY,
                    amount=Decimal(1),
                    currency="EUR",
                    payment_method=PaymentMethod.CASH,
                ),
            )
        )


async def test_the_amount_is_suggested_in_the_customers_currency(
    bus: Bus, make_project: ProjectFactory, accountant: UserDTO
) -> None:
    project = await make_project()
    same_currency = await _receipt(bus, accountant, currency="EUR", amount="100.00")
    in_sek = await _receipt(bus, accountant, currency="SEK", amount="1129.00")

    same = await bus.execute(
        SuggestRebillAmount(document_id=same_currency.id, project_id=project.id)
    )
    converted = await bus.execute(SuggestRebillAmount(document_id=in_sek.id, project_id=project.id))

    assert (same.amount, same.currency) == (Decimal("100.00"), "EUR")
    assert same.description == "Hotel AB"
    assert converted.amount == Decimal("100.00")  # 1129.00 SEK at 11.29 SEK/EUR


async def test_an_unavailable_rate_needs_a_typed_amount(
    bus: Bus, make_project: ProjectFactory, accountant: UserDTO, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = await make_project()
    item_id = await _expense_item_id(bus, project)
    document = await _receipt(bus, accountant, currency="SEK", amount="1129.00")
    install(monkeypatch, FakeRiksbank(status=204))

    suggestion = await bus.execute(
        SuggestRebillAmount(document_id=document.id, project_id=project.id)
    )
    with pytest.raises(PurchaseValidationError):
        await bus.execute(_rebill(document, accountant, project, item_id))
    typed = await bus.execute(_rebill(document, accountant, project, item_id, amount=Decimal(95)))

    assert suggestion.amount is None
    assert typed.rebilled_expense_line_id is not None


async def test_rule_violations_leave_the_document_unrebilled(
    bus: Bus, make_project: ProjectFactory, accountant: UserDTO
) -> None:
    project = await make_project()
    item_id = await _expense_item_id(bus, project)
    document = await _receipt(bus, accountant)

    with pytest.raises(PurchaseValidationError):  # date outside the chosen month
        await bus.execute(_rebill(document, accountant, project, item_id, month=10))
    with pytest.raises(PurchaseValidationError):  # not an item of the project
        await bus.execute(_rebill(document, accountant, project, uuid4()))

    assert (await _refetch(bus, document)).rebilled_expense_line_id is None


async def _refetch(bus: Bus, document: PurchaseDocumentDTO) -> PurchaseDocumentDTO:
    from time_reporting.modules.purchases.contracts import GetPurchaseDocument

    return await bus.query(GetPurchaseDocument(document_id=document.id))


async def test_a_submitted_report_refuses_more_lines(
    bus: Bus, make_project: ProjectFactory, accountant: UserDTO
) -> None:
    project = await make_project()
    item_id = await _expense_item_id(bus, project)
    first = await _receipt(bus, accountant)
    second = await _receipt(bus, accountant)
    await bus.execute(_rebill(first, accountant, project, item_id))
    events = await bus.query(
        ListAuditEvents(limit=5, offset=0, action=AuditAction.PURCHASE_REBILLED)
    )
    report_id = uuid_of(events.items[0].details, "expense_report_id")
    await bus.execute(SubmitExpenseReport(report_id=report_id, actor_id=accountant.id))

    with pytest.raises(PurchaseDocumentStateError):
        await bus.execute(_rebill(second, accountant, project, item_id))


async def test_rebill_routes(
    client: AsyncClient,
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    auth_headers: AuthHeaders,
) -> None:
    user = await make_user(roles=ACCOUNTANT)
    headers = auth_headers(user)
    project = await make_project()
    item_id = await _expense_item_id(bus, project)
    document = await _receipt(bus, user)
    base = f"/api/v1/purchases/documents/{document.id}"

    suggestion = await client.get(
        f"{base}/rebill-suggestion", headers=headers, params={"project_id": str(project.id)}
    )
    invalid = await client.post(
        f"{base}/rebill",
        headers=headers,
        json={
            "project_id": str(project.id),
            "year": 2026,
            "month": 10,
            "billing_item_id": str(item_id),
            "description": "x",
        },
    )
    done = await client.post(
        f"{base}/rebill",
        headers=headers,
        json={
            "project_id": str(project.id),
            "year": 2026,
            "month": 9,
            "billing_item_id": str(item_id),
            "description": "Hotel",
        },
    )
    again = await client.post(
        f"{base}/rebill",
        headers=headers,
        json={
            "project_id": str(project.id),
            "year": 2026,
            "month": 9,
            "billing_item_id": str(item_id),
            "description": "Hotel",
        },
    )

    assert suggestion.json()["amount"] == "100.00"
    assert invalid.status_code == 400
    assert done.status_code == 200
    assert done.json()["rebilled_expense_line_id"] is not None
    assert again.status_code == 409


async def test_the_non_member_owner_can_still_edit_the_rebilled_report(
    bus: Bus, make_project: ProjectFactory, accountant: UserDTO
) -> None:
    project = await make_project()
    item_id = await _expense_item_id(bus, project)
    document = await _receipt(bus, accountant)
    await bus.execute(_rebill(document, accountant, project, item_id))
    events = await bus.query(
        ListAuditEvents(limit=5, offset=0, action=AuditAction.PURCHASE_REBILLED)
    )
    report_id = uuid_of(events.items[0].details, "expense_report_id")
    report = await bus.query(GetExpenseReport(report_id=report_id, viewer_id=accountant.id))

    saved = await bus.execute(
        SaveExpenseReportLines(
            report_id=report_id,
            actor_id=accountant.id,
            lines=(
                ExpenseLineChange(
                    line_id=report.lines[0].id,
                    billing_item_id=report.lines[0].billing_item.id,
                    expense_date=DAY,
                    amount=Decimal("90.00"),
                    description="Corrected",
                ),
            ),
        )
    )

    assert saved.lines[0].amount == Decimal("90.00")
