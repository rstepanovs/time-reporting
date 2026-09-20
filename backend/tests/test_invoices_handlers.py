import re
import zlib
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from support import ADMIN, MANAGER, CustomerFactory, ProjectFactory, UserFactory
from time_reporting.core.cqrs import Bus
from time_reporting.modules.admin.contracts import GetCustomerRemovalImpact, RemovalBlockerKind
from time_reporting.modules.audit.contracts import AuditAction, ListAuditEvents
from time_reporting.modules.company.contracts import CompanyAddressDTO, UpdateCompanySettings
from time_reporting.modules.customers.contracts import UpdateCustomer
from time_reporting.modules.expenses.contracts import (
    ApproveExpenseReport,
    CreateExpenseReport,
    ExpenseLineChange,
    SaveExpenseReportLines,
    SubmitExpenseReport,
)
from time_reporting.modules.invoices.contracts import (
    BillingItemRateMissingError,
    CompanyProfileIncompleteError,
    CountInvoices,
    CreateInvoiceDraft,
    DeleteInvoiceDraft,
    GetInvoice,
    GetInvoicePdf,
    InvoiceCustomerNotFoundError,
    InvoiceEmptyError,
    InvoiceLineChange,
    InvoiceLineKind,
    InvoiceLineNotFoundError,
    InvoiceNoPeriodsError,
    InvoiceNotDraftError,
    InvoiceNotFoundError,
    InvoiceNotIssuedError,
    InvoiceNotVoidableError,
    InvoicePeriodNotEligibleError,
    InvoiceStatus,
    IssueInvoice,
    ListInvoiceablePeriods,
    ListInvoices,
    MarkInvoicePaid,
    UpdateInvoiceDraft,
    VoidInvoice,
)
from time_reporting.modules.invoices.models import Invoice as InvoiceRow
from time_reporting.modules.projects.contracts import (
    AddProjectMember,
    BillingItemPreset,
    ListProjectBillingItems,
    UpdateProjectBillingItem,
)
from time_reporting.modules.timesheets.contracts import (
    ApproveTimesheetWeek,
    BillingPeriodRef,
    SaveTimesheetWeek,
    SendProjectMonthToBilling,
    SubmitTimesheetWeek,
    TimeEntryChange,
)
from time_reporting.modules.users.contracts import UserDTO

YEAR = 2026
MONTH = 9
PERIOD_START = date(2026, 9, 1)
WEEK_1 = date(2026, 9, 7)
WEEK_2 = date(2026, 9, 14)


async def _hours_item_id(bus: Bus, project_id: UUID) -> UUID:
    items = await bus.query(ListProjectBillingItems(project_id=project_id))
    return next(item.id for item in items if item.preset == BillingItemPreset.NORMAL_HOURS)


async def _purchasing_item_id(bus: Bus, project_id: UUID) -> UUID:
    items = await bus.query(ListProjectBillingItems(project_id=project_id))
    return next(item.id for item in items if item.preset == BillingItemPreset.PURCHASING_EXPENSES)


async def _book_and_approve(
    bus: Bus,
    *,
    worker_id: UUID,
    admin_id: UUID,
    item_id: UUID,
    entry_date: date,
    week_start: date,
    quantity: Decimal = Decimal("4"),
) -> None:
    await bus.execute(
        SaveTimesheetWeek(
            user_id=worker_id,
            week_start=week_start,
            changes=(TimeEntryChange(billing_item_id=item_id, date=entry_date, quantity=quantity),),
        )
    )
    await bus.execute(SubmitTimesheetWeek(user_id=worker_id, week_start=week_start))
    await bus.execute(
        ApproveTimesheetWeek(user_id=worker_id, week_start=week_start, reviewer_id=admin_id)
    )


async def _add_and_approve_expense(
    bus: Bus,
    *,
    worker_id: UUID,
    admin_id: UUID,
    project_id: UUID,
    item_id: UUID,
    expense_date: date,
    amount: Decimal,
    description: str = "Taxi",
    vendor: str | None = "City Cabs",
) -> None:
    report = await bus.execute(
        CreateExpenseReport(user_id=worker_id, project_id=project_id, year=YEAR, month=MONTH)
    )
    await bus.execute(
        SaveExpenseReportLines(
            report_id=report.id,
            actor_id=worker_id,
            lines=(
                ExpenseLineChange(
                    line_id=None,
                    billing_item_id=item_id,
                    expense_date=expense_date,
                    amount=amount,
                    description=description,
                    vendor=vendor,
                ),
            ),
        )
    )
    await bus.execute(SubmitExpenseReport(report_id=report.id, actor_id=worker_id))
    await bus.execute(ApproveExpenseReport(report_id=report.id, reviewer_id=admin_id))


async def _sent_period(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    *,
    customer_id: UUID | None = None,
    hour_rate: Decimal | None = Decimal("100.00"),
    hours: Decimal = Decimal("4"),
) -> tuple[UUID, UserDTO, UserDTO, UserDTO]:
    """Books and approves one week of hours, sends the month to billing, and returns
    ``(project_id, _manager, admin, worker)``. ``hour_rate=None`` leaves the item's rate unset."""
    manager = await make_user(roles=MANAGER)
    admin = await make_user(roles=ADMIN)
    worker = await make_user()
    project = await make_project(manager_id=manager.id, customer_id=customer_id)
    await bus.execute(AddProjectMember(project_id=project.id, user_id=worker.id))
    item_id = await _hours_item_id(bus, project.id)
    if hour_rate is not None:
        await bus.execute(
            UpdateProjectBillingItem(project_id=project.id, item_id=item_id, unit_rate=hour_rate)
        )
    await _book_and_approve(
        bus,
        worker_id=worker.id,
        admin_id=admin.id,
        item_id=item_id,
        entry_date=WEEK_1,
        week_start=WEEK_1,
        quantity=hours,
    )
    await bus.execute(
        SendProjectMonthToBilling(
            project_id=project.id, year=YEAR, month=MONTH, sent_by_id=manager.id
        )
    )
    return project.id, manager, admin, worker


async def _complete_company_profile(bus: Bus, admin_id: UUID) -> None:
    """The minimum a company profile needs for ``IssueInvoice`` to accept it (see
    ``CompanyProfileIncompleteError``)."""
    await bus.execute(
        UpdateCompanySettings(
            actor_id=admin_id,
            legal_name="Belt & Braces Software AB",
            org_number="556677-8899",
            vat_number="SE556677889901",
            address=CompanyAddressDTO(
                street="1 Main Street",
                street2=None,
                postal_code="123 45",
                city="Lund",
                country="se",
            ),
            email="info@example.se",
            phone="070-000 00 00",
            registered_office="Lund",
            bankgiro="123-4567",
            iban="",
            bic="",
            f_tax_approved=True,
            default_invoice_locale="en",
            late_interest="8.00 %",
            invoice_number_prefix="INV-",
            next_invoice_number=1,
            allow_self_review=False,
        )
    )


def _pdf_contains(pdf: bytes, needle: bytes) -> bool:
    """WeasyPrint compresses every PDF stream (including the metadata/xref ones — PDF 1.7 default),
    so a plain ``needle in pdf`` never matches; decompress each ``stream``/``endstream`` block and
    search those instead, falling back to the raw bytes for anything left uncompressed."""
    if needle in pdf:
        return True
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", pdf, re.DOTALL):
        try:
            if needle in zlib.decompress(match.group(1)):
                return True
        except zlib.error:
            continue
    return False


def _stub_renderer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Most issue/pdf tests care about the workflow, not the rendered bytes — only
    ``test_issue_invoice_renders_a_real_pdf`` exercises the actual ``faktura-printer`` call."""
    monkeypatch.setattr(
        "time_reporting.modules.invoices.service.render_invoice_pdf",
        AsyncMock(return_value=b"%PDF-stub"),
    )


async def _issued_invoice(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    make_customer: CustomerFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[UUID, UserDTO]:
    """A freshly issued invoice (stubbed renderer) plus the admin who issued it."""
    _stub_renderer(monkeypatch)
    customer = await make_customer()
    project_id, _manager, admin, _worker = await _sent_period(
        bus, make_project, make_user, customer_id=customer.id
    )
    await _complete_company_profile(bus, admin.id)
    draft = await bus.execute(
        CreateInvoiceDraft(
            customer_id=customer.id,
            periods=(BillingPeriodRef(project_id=project_id, period_start=PERIOD_START),),
            invoice_date=date(2026, 10, 1),
            actor_id=admin.id,
        )
    )
    issued = await bus.execute(IssueInvoice(invoice_id=draft.id, actor_id=admin.id))
    return issued.id, admin


# --- CreateInvoiceDraft: line generation ---


async def test_create_draft_aggregates_hours_per_item_across_dates(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory, make_customer: CustomerFactory
) -> None:
    customer = await make_customer()
    manager = await make_user(roles=MANAGER)
    admin = await make_user(roles=ADMIN)
    worker = await make_user()
    project = await make_project(manager_id=manager.id, customer_id=customer.id)
    await bus.execute(AddProjectMember(project_id=project.id, user_id=worker.id))
    item_id = await _hours_item_id(bus, project.id)
    await bus.execute(
        UpdateProjectBillingItem(
            project_id=project.id, item_id=item_id, unit_rate=Decimal("100.00")
        )
    )
    await _book_and_approve(
        bus,
        worker_id=worker.id,
        admin_id=admin.id,
        item_id=item_id,
        entry_date=WEEK_1,
        week_start=WEEK_1,
        quantity=Decimal("4"),
    )
    await _book_and_approve(
        bus,
        worker_id=worker.id,
        admin_id=admin.id,
        item_id=item_id,
        entry_date=WEEK_2,
        week_start=WEEK_2,
        quantity=Decimal("4"),
    )
    await bus.execute(
        SendProjectMonthToBilling(
            project_id=project.id, year=YEAR, month=MONTH, sent_by_id=manager.id
        )
    )

    invoice = await bus.execute(
        CreateInvoiceDraft(
            customer_id=customer.id,
            periods=(BillingPeriodRef(project_id=project.id, period_start=PERIOD_START),),
            invoice_date=date(2026, 10, 1),
            actor_id=admin.id,
        )
    )

    assert len(invoice.lines) == 1
    line = invoice.lines[0]
    assert line.kind is InvoiceLineKind.TIME
    assert line.quantity == Decimal("8.00")
    assert line.unit_price == Decimal("100.00")
    assert line.amount == Decimal("800.00")
    assert invoice.subtotal == Decimal("800.00")
    assert invoice.vat_amount == Decimal("0")
    assert invoice.total == Decimal("800.00")
    assert invoice.status is InvoiceStatus.DRAFT
    assert invoice.number is None
    assert invoice.due_date == date(2026, 10, 1) + timedelta(days=customer.payment_terms_days)


async def test_create_draft_rounds_amounts_half_up(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory, make_customer: CustomerFactory
) -> None:
    customer = await make_customer()
    project_id, _manager, admin, _worker = await _sent_period(
        bus,
        make_project,
        make_user,
        customer_id=customer.id,
        hour_rate=Decimal("33.33"),
        hours=Decimal("2.5"),
    )

    invoice = await bus.execute(
        CreateInvoiceDraft(
            customer_id=customer.id,
            periods=(BillingPeriodRef(project_id=project_id, period_start=PERIOD_START),),
            invoice_date=date(2026, 10, 1),
            actor_id=admin.id,
        )
    )

    # 2.5 * 33.33 = 83.325, quantized 0.01 ROUND_HALF_UP -> 83.33.
    assert invoice.lines[0].amount == Decimal("83.33")


async def test_create_draft_applies_markup_to_expense_lines(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory, make_customer: CustomerFactory
) -> None:
    customer = await make_customer()
    manager = await make_user(roles=MANAGER)
    admin = await make_user(roles=ADMIN)
    worker = await make_user()
    project = await make_project(manager_id=manager.id, customer_id=customer.id)
    await bus.execute(AddProjectMember(project_id=project.id, user_id=worker.id))
    purchasing_id = await _purchasing_item_id(bus, project.id)
    await bus.execute(
        UpdateProjectBillingItem(
            project_id=project.id, item_id=purchasing_id, markup_percent=Decimal("10.00")
        )
    )
    await _add_and_approve_expense(
        bus,
        worker_id=worker.id,
        admin_id=admin.id,
        project_id=project.id,
        item_id=purchasing_id,
        expense_date=date(2026, 9, 5),
        amount=Decimal("42.50"),
        description="Taxi",
        vendor="City Cabs",
    )
    await bus.execute(
        SendProjectMonthToBilling(
            project_id=project.id, year=YEAR, month=MONTH, sent_by_id=manager.id
        )
    )

    invoice = await bus.execute(
        CreateInvoiceDraft(
            customer_id=customer.id,
            periods=(BillingPeriodRef(project_id=project.id, period_start=PERIOD_START),),
            invoice_date=date(2026, 10, 1),
            actor_id=admin.id,
        )
    )

    assert len(invoice.lines) == 1
    line = invoice.lines[0]
    assert line.kind is InvoiceLineKind.EXPENSE
    assert line.quantity == Decimal("1")
    # 42.50 * 1.10 = 46.75
    assert line.amount == Decimal("46.75")
    assert "City Cabs" in line.description
    assert "Taxi" in line.description


async def test_create_draft_applies_customer_vat(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory, make_customer: CustomerFactory
) -> None:
    customer = await make_customer()
    await bus.execute(UpdateCustomer(customer_id=customer.id, vat_rate=Decimal("25.00")))
    project_id, _manager, admin, _worker = await _sent_period(
        bus, make_project, make_user, customer_id=customer.id
    )

    invoice = await bus.execute(
        CreateInvoiceDraft(
            customer_id=customer.id,
            periods=(BillingPeriodRef(project_id=project_id, period_start=PERIOD_START),),
            invoice_date=date(2026, 10, 1),
            actor_id=admin.id,
        )
    )

    assert invoice.subtotal == Decimal("400.00")
    assert invoice.vat_amount == Decimal("100.00")
    assert invoice.total == Decimal("500.00")


async def test_create_draft_without_customer_vat_has_no_vat_line(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory, make_customer: CustomerFactory
) -> None:
    customer = await make_customer()
    project_id, _manager, admin, _worker = await _sent_period(
        bus, make_project, make_user, customer_id=customer.id
    )

    invoice = await bus.execute(
        CreateInvoiceDraft(
            customer_id=customer.id,
            periods=(BillingPeriodRef(project_id=project_id, period_start=PERIOD_START),),
            invoice_date=date(2026, 10, 1),
            actor_id=admin.id,
        )
    )

    assert invoice.vat_rate is None
    assert invoice.vat_amount == Decimal("0")
    assert invoice.total == invoice.subtotal


# --- CreateInvoiceDraft: rejections ---


async def test_create_draft_rejects_missing_unit_rate(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory, make_customer: CustomerFactory
) -> None:
    customer = await make_customer()
    project_id, _manager, admin, _worker = await _sent_period(
        bus, make_project, make_user, customer_id=customer.id, hour_rate=None
    )

    with pytest.raises(BillingItemRateMissingError):
        await bus.execute(
            CreateInvoiceDraft(
                customer_id=customer.id,
                periods=(BillingPeriodRef(project_id=project_id, period_start=PERIOD_START),),
                invoice_date=date(2026, 10, 1),
                actor_id=admin.id,
            )
        )


async def test_create_draft_rejects_empty_periods(
    bus: Bus, make_customer: CustomerFactory, make_user: UserFactory
) -> None:
    customer = await make_customer()
    admin = await make_user(roles=ADMIN)

    with pytest.raises(InvoiceNoPeriodsError):
        await bus.execute(
            CreateInvoiceDraft(
                customer_id=customer.id,
                periods=(),
                invoice_date=date(2026, 10, 1),
                actor_id=admin.id,
            )
        )


async def test_create_draft_rejects_unknown_customer(bus: Bus, make_user: UserFactory) -> None:
    admin = await make_user(roles=ADMIN)

    with pytest.raises(InvoiceCustomerNotFoundError):
        await bus.execute(
            CreateInvoiceDraft(
                customer_id=uuid4(),
                periods=(BillingPeriodRef(project_id=uuid4(), period_start=PERIOD_START),),
                invoice_date=date(2026, 10, 1),
                actor_id=admin.id,
            )
        )


async def test_create_draft_rejects_period_of_another_customer(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory, make_customer: CustomerFactory
) -> None:
    project_id, _manager, admin, _worker = await _sent_period(bus, make_project, make_user)
    other_customer = await make_customer()

    with pytest.raises(InvoicePeriodNotEligibleError):
        await bus.execute(
            CreateInvoiceDraft(
                customer_id=other_customer.id,
                periods=(BillingPeriodRef(project_id=project_id, period_start=PERIOD_START),),
                invoice_date=date(2026, 10, 1),
                actor_id=admin.id,
            )
        )


async def test_create_draft_rejects_unsent_period(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory, make_customer: CustomerFactory
) -> None:
    customer = await make_customer()
    admin = await make_user(roles=ADMIN)
    project = await make_project(customer_id=customer.id)

    with pytest.raises(InvoicePeriodNotEligibleError):
        await bus.execute(
            CreateInvoiceDraft(
                customer_id=customer.id,
                periods=(BillingPeriodRef(project_id=project.id, period_start=PERIOD_START),),
                invoice_date=date(2026, 10, 1),
                actor_id=admin.id,
            )
        )


async def test_create_draft_rejects_already_invoiced_period(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory, make_customer: CustomerFactory
) -> None:
    customer = await make_customer()
    project_id, _manager, admin, _worker = await _sent_period(
        bus, make_project, make_user, customer_id=customer.id
    )
    period = (BillingPeriodRef(project_id=project_id, period_start=PERIOD_START),)
    await bus.execute(
        CreateInvoiceDraft(
            customer_id=customer.id,
            periods=period,
            invoice_date=date(2026, 10, 1),
            actor_id=admin.id,
        )
    )

    with pytest.raises(InvoicePeriodNotEligibleError):
        await bus.execute(
            CreateInvoiceDraft(
                customer_id=customer.id,
                periods=period,
                invoice_date=date(2026, 10, 1),
                actor_id=admin.id,
            )
        )


# --- GetInvoice / ListInvoices / ListInvoiceablePeriods ---


async def test_get_invoice_raises_when_not_found(bus: Bus) -> None:
    with pytest.raises(InvoiceNotFoundError):
        await bus.query(GetInvoice(invoice_id=uuid4()))


async def test_list_invoices_filters_by_customer_and_status(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory, make_customer: CustomerFactory
) -> None:
    customer_a = await make_customer()
    customer_b = await make_customer()
    project_a_id, _manager_a, admin_a, _worker_a = await _sent_period(
        bus, make_project, make_user, customer_id=customer_a.id
    )
    project_b_id, _manager_b, admin_b, _worker_b = await _sent_period(
        bus, make_project, make_user, customer_id=customer_b.id
    )
    await bus.execute(
        CreateInvoiceDraft(
            customer_id=customer_a.id,
            periods=(BillingPeriodRef(project_id=project_a_id, period_start=PERIOD_START),),
            invoice_date=date(2026, 10, 1),
            actor_id=admin_a.id,
        )
    )
    await bus.execute(
        CreateInvoiceDraft(
            customer_id=customer_b.id,
            periods=(BillingPeriodRef(project_id=project_b_id, period_start=PERIOD_START),),
            invoice_date=date(2026, 10, 1),
            actor_id=admin_b.id,
        )
    )

    page = await bus.query(ListInvoices(customer_id=customer_a.id, limit=50, offset=0))
    assert page.total == 1
    assert page.items[0].customer_id == customer_a.id

    draft_page = await bus.query(ListInvoices(status=InvoiceStatus.DRAFT, limit=50, offset=0))
    assert draft_page.total == 2


async def test_list_invoiceable_periods_groups_by_customer(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory, make_customer: CustomerFactory
) -> None:
    customer = await make_customer()
    project_id, _manager, admin, _worker = await _sent_period(
        bus, make_project, make_user, customer_id=customer.id
    )

    customers = await bus.query(ListInvoiceablePeriods())

    matching = next(c for c in customers if c.customer_id == customer.id)
    assert len(matching.periods) == 1
    assert matching.periods[0].project_id == project_id
    assert matching.periods[0].period_start == PERIOD_START

    # Once invoiced, the period drops out.
    await bus.execute(
        CreateInvoiceDraft(
            customer_id=customer.id,
            periods=(BillingPeriodRef(project_id=project_id, period_start=PERIOD_START),),
            invoice_date=date(2026, 10, 1),
            actor_id=admin.id,
        )
    )
    customers_after = await bus.query(ListInvoiceablePeriods())
    assert all(c.customer_id != customer.id for c in customers_after)


# --- UpdateInvoiceDraft ---


async def test_update_draft_adds_edits_and_deletes_lines(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory, make_customer: CustomerFactory
) -> None:
    customer = await make_customer()
    project_id, _manager, admin, _worker = await _sent_period(
        bus, make_project, make_user, customer_id=customer.id
    )
    invoice = await bus.execute(
        CreateInvoiceDraft(
            customer_id=customer.id,
            periods=(BillingPeriodRef(project_id=project_id, period_start=PERIOD_START),),
            invoice_date=date(2026, 10, 1),
            actor_id=admin.id,
        )
    )
    generated_line = invoice.lines[0]

    updated = await bus.execute(
        UpdateInvoiceDraft(
            invoice_id=invoice.id,
            actor_id=admin.id,
            lines=(
                InvoiceLineChange(
                    line_id=None,
                    description="Travel expenses (manual)",
                    quantity=Decimal("1"),
                    unit="pcs",
                    unit_price=Decimal("50.00"),
                ),
            ),
        )
    )
    assert len(updated.lines) == 2
    manual_line = next(line for line in updated.lines if line.kind is InvoiceLineKind.MANUAL)
    assert manual_line.amount == Decimal("50.00")
    assert manual_line.project_id is None
    assert updated.subtotal == Decimal("450.00")

    edited = await bus.execute(
        UpdateInvoiceDraft(
            invoice_id=invoice.id,
            actor_id=admin.id,
            lines=(
                InvoiceLineChange(
                    line_id=generated_line.id,
                    description=generated_line.description,
                    quantity=generated_line.quantity,
                    unit=generated_line.unit,
                    unit_price=Decimal("50.00"),
                ),
            ),
        )
    )
    edited_line = next(line for line in edited.lines if line.id == generated_line.id)
    assert edited_line.kind is InvoiceLineKind.TIME
    assert edited_line.unit_price == Decimal("50.00")
    assert edited_line.amount == Decimal("200.00")

    final = await bus.execute(
        UpdateInvoiceDraft(
            invoice_id=invoice.id, actor_id=admin.id, delete_line_ids=frozenset({manual_line.id})
        )
    )
    assert len(final.lines) == 1
    assert final.subtotal == Decimal("200.00")
    assert final.total == Decimal("200.00")


async def test_update_draft_clears_optional_fields(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory, make_customer: CustomerFactory
) -> None:
    customer = await make_customer()
    await bus.execute(
        UpdateCustomer(customer_id=customer.id, vat_rate=Decimal("25.00"), your_reference="PO-123")
    )
    project_id, _manager, admin, _worker = await _sent_period(
        bus, make_project, make_user, customer_id=customer.id
    )
    invoice = await bus.execute(
        CreateInvoiceDraft(
            customer_id=customer.id,
            periods=(BillingPeriodRef(project_id=project_id, period_start=PERIOD_START),),
            invoice_date=date(2026, 10, 1),
            actor_id=admin.id,
        )
    )
    assert invoice.vat_rate == Decimal("25.00")
    assert invoice.your_reference == "PO-123"

    cleared = await bus.execute(
        UpdateInvoiceDraft(
            invoice_id=invoice.id,
            actor_id=admin.id,
            clear_fields=frozenset({"vat_rate", "your_reference"}),
        )
    )
    assert cleared.vat_rate is None
    assert cleared.vat_amount == Decimal("0")
    assert cleared.your_reference is None


async def test_update_draft_rejects_unknown_line_id(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory, make_customer: CustomerFactory
) -> None:
    customer = await make_customer()
    project_id, _manager, admin, _worker = await _sent_period(
        bus, make_project, make_user, customer_id=customer.id
    )
    invoice = await bus.execute(
        CreateInvoiceDraft(
            customer_id=customer.id,
            periods=(BillingPeriodRef(project_id=project_id, period_start=PERIOD_START),),
            invoice_date=date(2026, 10, 1),
            actor_id=admin.id,
        )
    )

    with pytest.raises(InvoiceLineNotFoundError):
        await bus.execute(
            UpdateInvoiceDraft(
                invoice_id=invoice.id,
                actor_id=admin.id,
                lines=(
                    InvoiceLineChange(
                        line_id=uuid4(),
                        description="Ghost",
                        quantity=Decimal("1"),
                        unit="pcs",
                        unit_price=Decimal("1"),
                    ),
                ),
            )
        )

    unchanged = await bus.query(GetInvoice(invoice_id=invoice.id))
    assert len(unchanged.lines) == 1


# --- DeleteInvoiceDraft ---


async def test_delete_draft_frees_its_periods(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory, make_customer: CustomerFactory
) -> None:
    customer = await make_customer()
    project_id, _manager, admin, _worker = await _sent_period(
        bus, make_project, make_user, customer_id=customer.id
    )
    period = (BillingPeriodRef(project_id=project_id, period_start=PERIOD_START),)
    invoice = await bus.execute(
        CreateInvoiceDraft(
            customer_id=customer.id,
            periods=period,
            invoice_date=date(2026, 10, 1),
            actor_id=admin.id,
        )
    )
    invoiceable_before = await bus.query(ListInvoiceablePeriods())
    assert all(c.customer_id != customer.id for c in invoiceable_before)

    await bus.execute(DeleteInvoiceDraft(invoice_id=invoice.id, actor_id=admin.id))

    with pytest.raises(InvoiceNotFoundError):
        await bus.query(GetInvoice(invoice_id=invoice.id))

    invoiceable_after = await bus.query(ListInvoiceablePeriods())
    matching = next(c for c in invoiceable_after if c.customer_id == customer.id)
    assert matching.periods[0].period_start == PERIOD_START

    # The period is invoiceable again — a new draft over the same period succeeds.
    await bus.execute(
        CreateInvoiceDraft(
            customer_id=customer.id,
            periods=period,
            invoice_date=date(2026, 10, 1),
            actor_id=admin.id,
        )
    )


async def test_delete_draft_raises_when_not_found(bus: Bus, make_user: UserFactory) -> None:
    admin = await make_user(roles=ADMIN)

    with pytest.raises(InvoiceNotFoundError):
        await bus.execute(DeleteInvoiceDraft(invoice_id=uuid4(), actor_id=admin.id))


# --- CountInvoices / admin removal impact ---


async def test_count_invoices_and_customer_removal_impact(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory, make_customer: CustomerFactory
) -> None:
    customer = await make_customer()
    project_id, _manager, admin, _worker = await _sent_period(
        bus, make_project, make_user, customer_id=customer.id
    )

    assert await bus.query(CountInvoices(customer_id=customer.id)) == 0

    await bus.execute(
        CreateInvoiceDraft(
            customer_id=customer.id,
            periods=(BillingPeriodRef(project_id=project_id, period_start=PERIOD_START),),
            invoice_date=date(2026, 10, 1),
            actor_id=admin.id,
        )
    )

    assert await bus.query(CountInvoices(customer_id=customer.id)) == 1

    impact = await bus.query(GetCustomerRemovalImpact(customer_id=customer.id))
    assert impact is not None
    assert impact.can_delete_permanently is False
    kinds = {blocker.kind for blocker in impact.blockers}
    assert RemovalBlockerKind.INVOICES in kinds


# --- IssueInvoice ---


async def test_issue_invoice_renders_a_real_pdf(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory, make_customer: CustomerFactory
) -> None:
    """The one test in this module that exercises the actual faktura-printer render — every
    other issue/pdf test stubs it out."""
    customer = await make_customer()
    project_id, _manager, admin, _worker = await _sent_period(
        bus, make_project, make_user, customer_id=customer.id
    )
    await _complete_company_profile(bus, admin.id)
    draft = await bus.execute(
        CreateInvoiceDraft(
            customer_id=customer.id,
            periods=(BillingPeriodRef(project_id=project_id, period_start=PERIOD_START),),
            invoice_date=date(2026, 10, 1),
            actor_id=admin.id,
        )
    )

    issued = await bus.execute(IssueInvoice(invoice_id=draft.id, actor_id=admin.id))

    assert issued.status is InvoiceStatus.ISSUED
    assert issued.number == "INV-1"
    assert issued.issued_at is not None

    row = await bus.session.get(InvoiceRow, issued.id)
    assert row is not None
    assert row.pdf is not None
    assert row.pdf.startswith(b"%PDF")
    assert row.pdf_sha256 is not None
    assert _pdf_contains(row.pdf, b"INV-1")


async def test_issue_invoice_allocates_consecutive_numbers(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory, make_customer: CustomerFactory
) -> None:
    customer = await make_customer()
    admin_id: UUID | None = None
    issued_numbers: list[str | None] = []
    for _ in range(2):
        project_id, _manager, admin, _worker = await _sent_period(
            bus, make_project, make_user, customer_id=customer.id
        )
        admin_id = admin.id
        if issued_numbers == []:
            await _complete_company_profile(bus, admin.id)
        draft = await bus.execute(
            CreateInvoiceDraft(
                customer_id=customer.id,
                periods=(BillingPeriodRef(project_id=project_id, period_start=PERIOD_START),),
                invoice_date=date(2026, 10, 1),
                actor_id=admin.id,
            )
        )
        issued = await bus.execute(IssueInvoice(invoice_id=draft.id, actor_id=admin.id))
        issued_numbers.append(issued.number)
    assert admin_id is not None
    assert issued_numbers == ["INV-1", "INV-2"]


async def test_issue_invoice_rejects_already_issued(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    make_customer: CustomerFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoice_id, admin = await _issued_invoice(
        bus, make_project, make_user, make_customer, monkeypatch
    )

    with pytest.raises(InvoiceNotDraftError):
        await bus.execute(IssueInvoice(invoice_id=invoice_id, actor_id=admin.id))


async def test_issue_invoice_rejects_empty_draft(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    make_customer: CustomerFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_renderer(monkeypatch)
    customer = await make_customer()
    project_id, _manager, admin, _worker = await _sent_period(
        bus, make_project, make_user, customer_id=customer.id
    )
    await _complete_company_profile(bus, admin.id)
    draft = await bus.execute(
        CreateInvoiceDraft(
            customer_id=customer.id,
            periods=(BillingPeriodRef(project_id=project_id, period_start=PERIOD_START),),
            invoice_date=date(2026, 10, 1),
            actor_id=admin.id,
        )
    )
    await bus.execute(
        UpdateInvoiceDraft(
            invoice_id=draft.id,
            actor_id=admin.id,
            delete_line_ids=frozenset({draft.lines[0].id}),
        )
    )

    with pytest.raises(InvoiceEmptyError):
        await bus.execute(IssueInvoice(invoice_id=draft.id, actor_id=admin.id))


async def test_issue_invoice_rejects_incomplete_company_profile(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    make_customer: CustomerFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_renderer(monkeypatch)
    customer = await make_customer()
    project_id, _manager, admin, _worker = await _sent_period(
        bus, make_project, make_user, customer_id=customer.id
    )
    draft = await bus.execute(
        CreateInvoiceDraft(
            customer_id=customer.id,
            periods=(BillingPeriodRef(project_id=project_id, period_start=PERIOD_START),),
            invoice_date=date(2026, 10, 1),
            actor_id=admin.id,
        )
    )

    with pytest.raises(CompanyProfileIncompleteError):
        await bus.execute(IssueInvoice(invoice_id=draft.id, actor_id=admin.id))


async def test_issue_invoice_raises_when_not_found(bus: Bus, make_user: UserFactory) -> None:
    admin = await make_user(roles=ADMIN)

    with pytest.raises(InvoiceNotFoundError):
        await bus.execute(IssueInvoice(invoice_id=uuid4(), actor_id=admin.id))


async def test_issued_invoice_cannot_be_edited_or_deleted(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    make_customer: CustomerFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoice_id, admin = await _issued_invoice(
        bus, make_project, make_user, make_customer, monkeypatch
    )

    with pytest.raises(InvoiceNotDraftError):
        await bus.execute(
            UpdateInvoiceDraft(invoice_id=invoice_id, actor_id=admin.id, notes="edited")
        )
    with pytest.raises(InvoiceNotDraftError):
        await bus.execute(DeleteInvoiceDraft(invoice_id=invoice_id, actor_id=admin.id))


async def test_issue_invoice_records_audit_event(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    make_customer: CustomerFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoice_id, admin = await _issued_invoice(
        bus, make_project, make_user, make_customer, monkeypatch
    )

    events = await bus.query(
        ListAuditEvents(
            limit=10, offset=0, action=AuditAction.INVOICE_ISSUED, entity_type="invoice"
        )
    )
    assert len(events.items) == 1
    assert events.items[0].entity_id == str(invoice_id)
    assert events.items[0].actor_id == admin.id


# --- GetInvoicePdf ---


async def test_get_invoice_pdf_previews_a_draft_without_storing_it(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    make_customer: CustomerFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_renderer(monkeypatch)
    customer = await make_customer()
    project_id, _manager, admin, _worker = await _sent_period(
        bus, make_project, make_user, customer_id=customer.id
    )
    draft = await bus.execute(
        CreateInvoiceDraft(
            customer_id=customer.id,
            periods=(BillingPeriodRef(project_id=project_id, period_start=PERIOD_START),),
            invoice_date=date(2026, 10, 1),
            actor_id=admin.id,
        )
    )

    pdf = await bus.query(GetInvoicePdf(invoice_id=draft.id))
    assert pdf.content == b"%PDF-stub"
    assert "draft" in pdf.filename

    row = await bus.session.get(InvoiceRow, draft.id)
    assert row is not None
    assert row.pdf is None
    assert row.number is None


async def test_get_invoice_pdf_serves_the_stored_bytes_once_issued(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    make_customer: CustomerFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoice_id, _admin = await _issued_invoice(
        bus, make_project, make_user, make_customer, monkeypatch
    )

    pdf = await bus.query(GetInvoicePdf(invoice_id=invoice_id))

    row = await bus.session.get(InvoiceRow, invoice_id)
    assert row is not None
    assert pdf.content == row.pdf
    assert pdf.filename == f"invoice-{row.number}.pdf"


async def test_get_invoice_pdf_raises_when_not_found(bus: Bus) -> None:
    with pytest.raises(InvoiceNotFoundError):
        await bus.query(GetInvoicePdf(invoice_id=uuid4()))


# --- MarkInvoicePaid ---


async def test_mark_invoice_paid(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    make_customer: CustomerFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoice_id, admin = await _issued_invoice(
        bus, make_project, make_user, make_customer, monkeypatch
    )

    paid = await bus.execute(
        MarkInvoicePaid(invoice_id=invoice_id, actor_id=admin.id, paid_on=date(2026, 10, 15))
    )

    assert paid.status is InvoiceStatus.PAID
    assert paid.paid_on == date(2026, 10, 15)

    events = await bus.query(
        ListAuditEvents(limit=10, offset=0, action=AuditAction.INVOICE_PAID, entity_type="invoice")
    )
    assert len(events.items) == 1


async def test_mark_invoice_paid_rejects_draft(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory, make_customer: CustomerFactory
) -> None:
    customer = await make_customer()
    project_id, _manager, admin, _worker = await _sent_period(
        bus, make_project, make_user, customer_id=customer.id
    )
    draft = await bus.execute(
        CreateInvoiceDraft(
            customer_id=customer.id,
            periods=(BillingPeriodRef(project_id=project_id, period_start=PERIOD_START),),
            invoice_date=date(2026, 10, 1),
            actor_id=admin.id,
        )
    )

    with pytest.raises(InvoiceNotIssuedError):
        await bus.execute(
            MarkInvoicePaid(invoice_id=draft.id, actor_id=admin.id, paid_on=date(2026, 10, 15))
        )


async def test_mark_invoice_paid_raises_when_not_found(bus: Bus, make_user: UserFactory) -> None:
    admin = await make_user(roles=ADMIN)

    with pytest.raises(InvoiceNotFoundError):
        await bus.execute(
            MarkInvoicePaid(invoice_id=uuid4(), actor_id=admin.id, paid_on=date(2026, 10, 15))
        )


# --- VoidInvoice ---


async def test_void_invoice_frees_its_periods_and_keeps_the_pdf(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    make_customer: CustomerFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoice_id, admin = await _issued_invoice(
        bus, make_project, make_user, make_customer, monkeypatch
    )
    before = await bus.query(GetInvoice(invoice_id=invoice_id))
    customer_id = before.customer.id

    voided = await bus.execute(
        VoidInvoice(invoice_id=invoice_id, actor_id=admin.id, reason="Wrong customer")
    )

    assert voided.status is InvoiceStatus.VOID
    assert voided.voided_at is not None
    assert voided.void_reason == "Wrong customer"
    assert voided.number == before.number

    row = await bus.session.get(InvoiceRow, invoice_id)
    assert row is not None
    assert row.pdf is not None

    invoiceable = await bus.query(ListInvoiceablePeriods())
    assert any(c.customer_id == customer_id for c in invoiceable)

    events = await bus.query(
        ListAuditEvents(
            limit=10, offset=0, action=AuditAction.INVOICE_VOIDED, entity_type="invoice"
        )
    )
    assert len(events.items) == 1


async def test_void_invoice_allowed_from_paid(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    make_customer: CustomerFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoice_id, admin = await _issued_invoice(
        bus, make_project, make_user, make_customer, monkeypatch
    )
    await bus.execute(
        MarkInvoicePaid(invoice_id=invoice_id, actor_id=admin.id, paid_on=date(2026, 10, 15))
    )

    voided = await bus.execute(
        VoidInvoice(invoice_id=invoice_id, actor_id=admin.id, reason="Refunded")
    )

    assert voided.status is InvoiceStatus.VOID


async def test_void_invoice_rejects_draft(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory, make_customer: CustomerFactory
) -> None:
    customer = await make_customer()
    project_id, _manager, admin, _worker = await _sent_period(
        bus, make_project, make_user, customer_id=customer.id
    )
    draft = await bus.execute(
        CreateInvoiceDraft(
            customer_id=customer.id,
            periods=(BillingPeriodRef(project_id=project_id, period_start=PERIOD_START),),
            invoice_date=date(2026, 10, 1),
            actor_id=admin.id,
        )
    )

    with pytest.raises(InvoiceNotVoidableError):
        await bus.execute(VoidInvoice(invoice_id=draft.id, actor_id=admin.id, reason="Mistake"))


async def test_void_invoice_rejects_already_void(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    make_customer: CustomerFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoice_id, admin = await _issued_invoice(
        bus, make_project, make_user, make_customer, monkeypatch
    )
    await bus.execute(VoidInvoice(invoice_id=invoice_id, actor_id=admin.id, reason="First"))

    with pytest.raises(InvoiceNotVoidableError):
        await bus.execute(VoidInvoice(invoice_id=invoice_id, actor_id=admin.id, reason="Second"))


async def test_void_invoice_raises_when_not_found(bus: Bus, make_user: UserFactory) -> None:
    admin = await make_user(roles=ADMIN)

    with pytest.raises(InvoiceNotFoundError):
        await bus.execute(VoidInvoice(invoice_id=uuid4(), actor_id=admin.id, reason="x"))
