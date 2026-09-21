"""Accounting domain logic: assembles the monthly accountant package purely from other modules'
data, reached through the bus — this module owns no tables and no repository of its own.
"""

import os
import re
import zipfile
from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import mkstemp
from uuid import UUID

from time_reporting.core.cqrs import Bus
from time_reporting.modules.accounting.content import (
    ExpenseRow,
    InvoiceRow,
    PackageContent,
    ReceiptFile,
)
from time_reporting.modules.accounting.contracts import (
    AccountantPackageDTO,
    AccountantPackageStatusDTO,
    AccountantPackageTotalDTO,
    BuildAccountantPackage,
    GetAccountantPackageStatus,
)
from time_reporting.modules.accounting.rendering import render_summary_pdf
from time_reporting.modules.accounting.spreadsheet import render_summary_xlsx
from time_reporting.modules.company.contracts import GetCompanySettings
from time_reporting.modules.expenses.contracts import (
    CountMonthReportsNotApproved,
    ExpenseMonthReportDTO,
    GetAttachmentPath,
    ListMonthExpenseLines,
)
from time_reporting.modules.invoices.contracts import (
    InvoiceStatus,
    InvoiceWithPdfDTO,
    ListInvoiceablePeriods,
    ListInvoices,
    ListInvoicesForMonth,
)

# Keeps a filename readable while safe on every filesystem the ZIP might be extracted on.
_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    first = date(year, month, 1)
    last_day = monthrange(year, month)[1]
    return first, date(year, month, last_day)


def _slug(text: str, *, max_length: int = 40) -> str:
    slug = _UNSAFE_FILENAME_CHARS.sub("-", text).strip("-")
    return (slug or "unnamed")[:max_length]


def _totals_by_currency(
    invoices: tuple[InvoiceWithPdfDTO, ...], reports: tuple[ExpenseMonthReportDTO, ...]
) -> tuple[AccountantPackageTotalDTO, ...]:
    """Invoiced and claimed-expense totals, grouped by currency and never mixed together. A
    ``VOID`` invoice is excluded — it printed a number that was then cancelled, not real revenue."""
    invoiced: dict[str, Decimal] = defaultdict(Decimal)
    for item in invoices:
        if item.invoice.status is InvoiceStatus.VOID:
            continue
        invoiced[item.invoice.currency] += item.invoice.total

    expenses: dict[str, Decimal] = defaultdict(Decimal)
    for report in reports:
        currency = report.project.customer.currency
        for line in report.lines:
            expenses[currency] += line.amount

    currencies = sorted(set(invoiced) | set(expenses))
    return tuple(
        AccountantPackageTotalDTO(
            currency=currency,
            invoiced_total=invoiced.get(currency, Decimal("0")),
            expense_total=expenses.get(currency, Decimal("0")),
        )
        for currency in currencies
    )


class AccountingService:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus

    async def get_status(self, query: GetAccountantPackageStatus) -> AccountantPackageStatusDTO:
        invoices, reports = await self._load(query.year, query.month)
        date_from, date_to = _month_bounds(query.year, query.month)

        # Only `.total` is used — `limit=1` still gets an accurate count (the repository counts
        # separately from the page it fetches), without paging through every draft.
        draft_page = await self._bus.query(
            ListInvoices(
                customer_id=None,
                status=InvoiceStatus.DRAFT,
                date_from=date_from,
                date_to=date_to,
                limit=1,
                offset=0,
            )
        )
        unapproved_count = await self._bus.query(
            CountMonthReportsNotApproved(year=query.year, month=query.month)
        )
        invoiceable = await self._bus.query(ListInvoiceablePeriods())
        uninvoiced_count = sum(
            1
            for customer in invoiceable
            for period in customer.periods
            if date_from <= period.period_start <= date_to
        )

        return AccountantPackageStatusDTO(
            year=query.year,
            month=query.month,
            invoice_count=len(invoices),
            expense_line_count=sum(len(report.lines) for report in reports),
            totals=_totals_by_currency(invoices, reports),
            draft_invoice_count=draft_page.total,
            unapproved_expense_report_count=unapproved_count,
            uninvoiced_sent_period_count=uninvoiced_count,
        )

    async def build_package(self, query: BuildAccountantPackage) -> AccountantPackageDTO:
        invoices, reports = await self._load(query.year, query.month)
        content = await self._build_content(
            query.year, query.month, invoices, reports, query.actor_id
        )
        company = await self._bus.query(GetCompanySettings())

        pdf = await render_summary_pdf(content, company=company)
        xlsx = render_summary_xlsx(content)

        fd, tmp_name = mkstemp(prefix="accountant-package-", suffix=".zip")
        os.close(fd)
        path = Path(tmp_name)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("summary.pdf", pdf)
            archive.writestr("summary.xlsx", xlsx)
            for item in invoices:
                archive.writestr(f"invoices/{item.invoice.number}.pdf", item.pdf)
            for receipt in content.receipt_files:
                archive.write(receipt.path, arcname=receipt.arcname)

        return AccountantPackageDTO(
            path=path, filename=f"accountant-package-{query.year:04d}-{query.month:02d}.zip"
        )

    async def _load(
        self, year: int, month: int
    ) -> tuple[tuple[InvoiceWithPdfDTO, ...], tuple[ExpenseMonthReportDTO, ...]]:
        invoices = await self._bus.query(ListInvoicesForMonth(year=year, month=month))
        reports = await self._bus.query(ListMonthExpenseLines(year=year, month=month))
        return invoices, reports

    async def _build_content(
        self,
        year: int,
        month: int,
        invoices: tuple[InvoiceWithPdfDTO, ...],
        reports: tuple[ExpenseMonthReportDTO, ...],
        actor_id: UUID,
    ) -> PackageContent:
        invoice_rows = tuple(
            InvoiceRow(
                number=item.invoice.number or "",
                invoice_date=item.invoice.invoice_date.isoformat(),
                customer_name=item.invoice.customer.name,
                net=item.invoice.subtotal,
                vat=item.invoice.vat_amount,
                total=item.invoice.total,
                currency=item.invoice.currency,
                status=item.invoice.status.value,
            )
            for item in invoices
        )

        expense_rows: list[ExpenseRow] = []
        receipt_files: list[ReceiptFile] = []
        next_number = 1
        for report in reports:
            currency = report.project.customer.currency
            report_name = _slug(f"{report.project.name}-{report.user.name}")
            report_slug = f"{report_name}-{str(report.id)[:8]}"
            for line in report.lines:
                numbers: list[int] = []
                for attachment_id in line.attachment_ids:
                    file = await self._bus.query(
                        GetAttachmentPath(attachment_id=attachment_id, viewer_id=actor_id)
                    )
                    numbers.append(next_number)
                    extension = Path(file.file_name).suffix
                    receipt_files.append(
                        ReceiptFile(
                            arcname=(
                                f"receipts/{next_number:03d}_{line.expense_date.isoformat()}_"
                                f"{_slug(line.vendor or 'unknown')}_{line.amount}{extension}"
                            ),
                            path=file.path,
                        )
                    )
                    next_number += 1
                expense_rows.append(
                    ExpenseRow(
                        expense_date=line.expense_date.isoformat(),
                        employee_name=report.user.name,
                        project_name=report.project.name,
                        vendor=line.vendor or "",
                        document_no=line.document_no or "",
                        description=line.description,
                        amount=line.amount,
                        currency=currency,
                        receipt_numbers=tuple(numbers),
                        is_internal=report.project.is_internal,
                    )
                )
            for attachment_id in report.unlinked_attachment_ids:
                file = await self._bus.query(
                    GetAttachmentPath(attachment_id=attachment_id, viewer_id=actor_id)
                )
                receipt_files.append(
                    ReceiptFile(arcname=f"receipts/{report_slug}/{file.file_name}", path=file.path)
                )

        expense_rows.sort(key=lambda row: (row.expense_date, row.employee_name))

        return PackageContent(
            year=year,
            month=month,
            invoices=invoice_rows,
            expense_rows=tuple(expense_rows),
            totals=_totals_by_currency(invoices, reports),
            receipt_files=tuple(receipt_files),
        )
