"""Bus-level tests for the accounting module: ``GetAccountantPackageStatus`` (counts, per-currency
totals and the three "something's not ready" warnings) and ``BuildAccountantPackage`` (the ZIP's
actual contents — summary.pdf/summary.xlsx, stored invoice PDFs and numbered/unlinked receipts).

Invoice PDF rendering is stubbed (as ``test_invoices_handlers.py`` does) since only the bytes
matter here, not their content; ``accounting``'s own ``summary.pdf``/``summary.xlsx`` render for
real in every test, since that's the code this module actually adds.
"""

import zipfile
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from openpyxl import load_workbook

from support import ADMIN, MANAGER, CustomerFactory, ProjectFactory, UserFactory
from time_reporting.core.config import get_settings
from time_reporting.core.cqrs import Bus
from time_reporting.modules.accounting.contracts import (
    AccountantPackageStatusDTO,
    AccountantPackageTotalDTO,
    BuildAccountantPackage,
    GetAccountantPackageStatus,
)
from time_reporting.modules.company.contracts import CompanyAddressDTO, UpdateCompanySettings
from time_reporting.modules.expenses.contracts import (
    AddExpenseAttachment,
    ApproveExpenseReport,
    CreateExpenseReport,
    ExpenseLineChange,
    SaveExpenseReportLines,
    SubmitExpenseReport,
)
from time_reporting.modules.invoices.contracts import (
    CreateInvoiceDraft,
    IssueInvoice,
    ListInvoices,
    VoidInvoice,
)
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
_PDF_BYTES = b"%PDF-1.4 not a real pdf, just needs content"


@pytest.fixture
def _isolated_attachments(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    patched = get_settings().model_copy(update={"attachment_dir": str(tmp_path)})
    monkeypatch.setattr("time_reporting.modules.expenses.service.get_settings", lambda: patched)
    return tmp_path


def _stub_invoice_renderer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "time_reporting.modules.invoices.service.render_invoice_pdf",
        AsyncMock(return_value=b"%PDF-stub"),
    )


async def _hours_item_id(bus: Bus, project_id: UUID) -> UUID:
    items = await bus.query(ListProjectBillingItems(project_id=project_id))
    return next(item.id for item in items if item.preset == BillingItemPreset.NORMAL_HOURS)


async def _purchasing_item_id(bus: Bus, project_id: UUID) -> UUID:
    items = await bus.query(ListProjectBillingItems(project_id=project_id))
    return next(item.id for item in items if item.preset == BillingItemPreset.PURCHASING_EXPENSES)


async def _complete_company_profile(bus: Bus, admin_id: UUID) -> None:
    """The minimum a company profile needs for ``IssueInvoice`` to accept it."""
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
            customer_number_prefix="",
            next_customer_number=1,
            allow_self_review=False,
        )
    )


async def _sent_period(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    *,
    customer_id: UUID | None = None,
) -> tuple[UUID, UserDTO, UserDTO, UserDTO]:
    """Books and approves one week of hours (100/hour) and sends the month to billing, returning
    ``(project_id, manager, admin, worker)``."""
    manager = await make_user(roles=MANAGER)
    admin = await make_user(roles=ADMIN)
    worker = await make_user()
    project = await make_project(manager_id=manager.id, customer_id=customer_id)
    await bus.execute(AddProjectMember(project_id=project.id, user_id=worker.id))
    item_id = await _hours_item_id(bus, project.id)
    await bus.execute(
        UpdateProjectBillingItem(project_id=project.id, item_id=item_id, unit_rate=Decimal("100"))
    )
    await bus.execute(
        SaveTimesheetWeek(
            user_id=worker.id,
            week_start=WEEK_1,
            changes=(TimeEntryChange(billing_item_id=item_id, date=WEEK_1, quantity=Decimal("4")),),
        )
    )
    await bus.execute(SubmitTimesheetWeek(user_id=worker.id, week_start=WEEK_1))
    await bus.execute(
        ApproveTimesheetWeek(user_id=worker.id, week_start=WEEK_1, reviewer_id=admin.id)
    )
    await bus.execute(
        SendProjectMonthToBilling(
            project_id=project.id, year=YEAR, month=MONTH, sent_by_id=manager.id
        )
    )
    return project.id, manager, admin, worker


async def _issued_invoice(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    make_customer: CustomerFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[UserDTO, str]:
    """A freshly issued invoice (stubbed renderer, 4h @ 100/hour = 400.00 EUR) plus the admin who
    issued it and the invoice's allocated number."""
    _stub_invoice_renderer(monkeypatch)
    customer = await make_customer()
    project_id, _manager, admin, _worker = await _sent_period(
        bus, make_project, make_user, customer_id=customer.id
    )
    await _complete_company_profile(bus, admin.id)
    draft = await bus.execute(
        CreateInvoiceDraft(
            customer_id=customer.id,
            periods=(BillingPeriodRef(project_id=project_id, period_start=PERIOD_START),),
            invoice_date=date(2026, 9, 20),
            actor_id=admin.id,
        )
    )
    issued = await bus.execute(IssueInvoice(invoice_id=draft.id, actor_id=admin.id))
    assert issued.number is not None
    return admin, issued.number


async def _approved_expense_report(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    *,
    customer_id: UUID | None = None,
    is_internal: bool = False,
    attach_line_receipt: bool = False,
    attach_unlinked_receipt: bool = False,
) -> UUID:
    """Creates, submits and approves a one-line (42.50, "Taxi") expense report for ``YEAR``/
    ``MONTH``, returning the report id. The reviewer is the project's manager, never the owner."""
    manager = await make_user(roles=MANAGER)
    worker = await make_user()
    project = await make_project(
        manager_id=manager.id, customer_id=customer_id, is_internal=is_internal
    )
    await bus.execute(AddProjectMember(project_id=project.id, user_id=worker.id))
    item_id = await _purchasing_item_id(bus, project.id)

    report = await bus.execute(
        CreateExpenseReport(user_id=worker.id, project_id=project.id, year=YEAR, month=MONTH)
    )
    updated = await bus.execute(
        SaveExpenseReportLines(
            report_id=report.id,
            actor_id=worker.id,
            lines=(
                ExpenseLineChange(
                    line_id=None,
                    billing_item_id=item_id,
                    expense_date=date(2026, 9, 10),
                    amount=Decimal("42.50"),
                    description="Taxi",
                    vendor="City Cabs",
                ),
            ),
        )
    )
    line_id = updated.lines[0].id

    if attach_line_receipt:
        await bus.execute(
            AddExpenseAttachment(
                report_id=report.id,
                actor_id=worker.id,
                file_name="receipt.pdf",
                content_type="application/pdf",
                content=_PDF_BYTES,
                line_id=line_id,
            )
        )
    if attach_unlinked_receipt:
        await bus.execute(
            AddExpenseAttachment(
                report_id=report.id,
                actor_id=worker.id,
                file_name="report-level.pdf",
                content_type="application/pdf",
                content=_PDF_BYTES,
            )
        )

    await bus.execute(SubmitExpenseReport(report_id=report.id, actor_id=worker.id))
    await bus.execute(ApproveExpenseReport(report_id=report.id, reviewer_id=manager.id))
    return report.id


# --- GetAccountantPackageStatus ---


async def test_status_is_empty_for_a_month_with_nothing(bus: Bus) -> None:
    status = await bus.query(GetAccountantPackageStatus(year=2030, month=1))

    assert status == AccountantPackageStatusDTO(
        year=2030,
        month=1,
        invoice_count=0,
        expense_line_count=0,
        totals=(),
        draft_invoice_count=0,
        unapproved_expense_report_count=0,
        uninvoiced_sent_period_count=0,
    )


async def test_status_counts_invoices_and_expenses_and_totals(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    make_customer: CustomerFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _issued_invoice(bus, make_project, make_user, make_customer, monkeypatch)
    await _approved_expense_report(bus, make_project, make_user)

    status = await bus.query(GetAccountantPackageStatus(year=YEAR, month=MONTH))

    assert status.invoice_count == 1
    assert status.expense_line_count == 1
    assert status.draft_invoice_count == 0
    assert status.unapproved_expense_report_count == 0
    assert status.uninvoiced_sent_period_count == 0
    # Invoiced and claimed-expense totals share a currency here but are kept in separate fields of
    # the same row, never summed together.
    assert status.totals == (
        AccountantPackageTotalDTO(
            currency="EUR", invoiced_total=Decimal("400.00"), expense_total=Decimal("42.50")
        ),
    )


async def test_status_flags_draft_invoice_unapproved_report_and_uninvoiced_period(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    make_customer: CustomerFactory,
) -> None:
    # A sent period nobody has invoiced yet.
    await _sent_period(bus, make_project, make_user)

    # A second sent period, drafted (but not issued) into an invoice dated in the month.
    customer = await make_customer()
    project_id, _manager, admin, _worker = await _sent_period(
        bus, make_project, make_user, customer_id=customer.id
    )
    await bus.execute(
        CreateInvoiceDraft(
            customer_id=customer.id,
            periods=(BillingPeriodRef(project_id=project_id, period_start=PERIOD_START),),
            invoice_date=date(2026, 9, 15),
            actor_id=admin.id,
        )
    )

    # A report submitted but not yet approved.
    manager = await make_user(roles=MANAGER)
    worker = await make_user()
    project = await make_project(manager_id=manager.id)
    await bus.execute(AddProjectMember(project_id=project.id, user_id=worker.id))
    item_id = await _purchasing_item_id(bus, project.id)
    report = await bus.execute(
        CreateExpenseReport(user_id=worker.id, project_id=project.id, year=YEAR, month=MONTH)
    )
    await bus.execute(
        SaveExpenseReportLines(
            report_id=report.id,
            actor_id=worker.id,
            lines=(
                ExpenseLineChange(
                    line_id=None,
                    billing_item_id=item_id,
                    expense_date=date(2026, 9, 5),
                    amount=Decimal("10"),
                    description="Snacks",
                ),
            ),
        )
    )
    await bus.execute(SubmitExpenseReport(report_id=report.id, actor_id=worker.id))

    status = await bus.query(GetAccountantPackageStatus(year=YEAR, month=MONTH))

    assert status.invoice_count == 0
    assert status.expense_line_count == 0
    assert status.draft_invoice_count == 1
    assert status.unapproved_expense_report_count == 1
    assert status.uninvoiced_sent_period_count == 1


async def test_status_excludes_a_voided_invoice_from_the_total(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    make_customer: CustomerFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin, number = await _issued_invoice(bus, make_project, make_user, make_customer, monkeypatch)
    invoices = await bus.query(
        ListInvoices(customer_id=None, status=None, date_from=None, date_to=None, limit=1, offset=0)
    )
    assert invoices.items[0].number == number
    await bus.execute(
        VoidInvoice(invoice_id=invoices.items[0].id, actor_id=admin.id, reason="Customer cancelled")
    )

    status = await bus.query(GetAccountantPackageStatus(year=YEAR, month=MONTH))

    # Still listed (in the package's Invoices table, as a record it was issued then cancelled),
    # but contributes nothing to the total — with no other invoice or expense that month, EUR
    # drops out of the totals entirely rather than showing an all-zero row.
    assert status.invoice_count == 1
    assert status.totals == ()


# --- BuildAccountantPackage ---


async def test_build_package_writes_summary_invoice_and_receipts(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    make_customer: CustomerFactory,
    monkeypatch: pytest.MonkeyPatch,
    _isolated_attachments: Path,
) -> None:
    admin, number = await _issued_invoice(bus, make_project, make_user, make_customer, monkeypatch)
    await _approved_expense_report(
        bus, make_project, make_user, attach_line_receipt=True, attach_unlinked_receipt=True
    )

    package = await bus.query(BuildAccountantPackage(year=YEAR, month=MONTH, actor_id=admin.id))
    try:
        assert package.filename == f"accountant-package-{YEAR:04d}-{MONTH:02d}.zip"
        with zipfile.ZipFile(package.path) as archive:
            names = archive.namelist()

            assert "summary.pdf" in names
            assert archive.read("summary.pdf").startswith(b"%PDF")

            assert "summary.xlsx" in names
            workbook = load_workbook(BytesIO(archive.read("summary.xlsx")))
            invoice_rows = list(workbook["Invoices"].iter_rows(min_row=2, values_only=True))
            assert len(invoice_rows) == 1
            invoice_row = invoice_rows[0]
            assert invoice_row[0] == number
            assert invoice_row[1] == "2026-09-20"
            assert isinstance(invoice_row[2], str) and invoice_row[2]  # customer name
            assert invoice_row[3:8] == (400.0, 0.0, 400.0, "EUR", "issued")
            expense_rows = list(workbook["Expenses"].iter_rows(min_row=2, values_only=True))
            assert len(expense_rows) == 1
            assert expense_rows[0][5] == "Taxi"
            assert expense_rows[0][8] == "001"  # the Receipt column, matching receipts/001_...
            assert expense_rows[0][9] == "No"  # not an internal project

            assert f"invoices/{number}.pdf" in names
            assert archive.read(f"invoices/{number}.pdf") == b"%PDF-stub"

            numbered_receipts = [name for name in names if name.startswith("receipts/001_")]
            assert numbered_receipts == ["receipts/001_2026-09-10_City-Cabs_42.50.pdf"]
            assert any(name.endswith("/report-level.pdf") for name in names)
    finally:
        package.path.unlink(missing_ok=True)


async def test_build_package_marks_internal_project_expenses(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    make_customer: CustomerFactory,
) -> None:
    manager = await make_user(roles=MANAGER)
    await _approved_expense_report(bus, make_project, make_user, is_internal=True)

    package = await bus.query(BuildAccountantPackage(year=YEAR, month=MONTH, actor_id=manager.id))
    try:
        with zipfile.ZipFile(package.path) as archive:
            workbook = load_workbook(BytesIO(archive.read("summary.xlsx")))
            expense_rows = list(workbook["Expenses"].iter_rows(min_row=2, values_only=True))
            assert expense_rows[0][9] == "Yes"
    finally:
        package.path.unlink(missing_ok=True)
