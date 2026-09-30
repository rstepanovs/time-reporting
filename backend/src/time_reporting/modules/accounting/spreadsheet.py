"""Builds the accountant package's ``summary.xlsx`` (``openpyxl``) — the same data as
``summary.pdf``, as two flat sheets (``Invoices``, ``Expenses``) rather than the PDF's grouped
tables, since a spreadsheet is for filtering/sorting, not reading top to bottom.
"""

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.worksheet.worksheet import Worksheet

from time_reporting.modules.accounting.content import PackageContent

_INVOICE_HEADERS = ("Number", "Date", "Customer", "Net", "VAT", "Total", "Currency", "Status")
_EXPENSE_HEADERS = (
    "Date",
    "Employee",
    "Project",
    "Vendor",
    "Document no.",
    "Description",
    "Amount",
    "Currency",
    "Receipt",
    "Internal",
)


_PURCHASE_HEADERS = (
    "File",
    "Date",
    "Kind",
    "Vendor",
    "Document no.",
    "Description",
    "Amount",
    "Currency",
    "Base amount",
    "Provisional",
    "Status",
    "Payment method",
    "Card invoice",
)


def _write_header_row(sheet: Worksheet, headers: tuple[str, ...]) -> None:
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)


def build_summary_workbook(content: PackageContent) -> Workbook:
    workbook = Workbook()
    invoices_sheet = workbook.active
    assert invoices_sheet is not None
    invoices_sheet.title = "Invoices"
    _write_header_row(invoices_sheet, _INVOICE_HEADERS)
    for invoice_row in content.invoices:
        invoices_sheet.append(
            (
                invoice_row.number,
                invoice_row.invoice_date,
                invoice_row.customer_name,
                invoice_row.net,
                invoice_row.vat,
                invoice_row.total,
                invoice_row.currency,
                invoice_row.status,
            )
        )

    expenses_sheet = workbook.create_sheet("Expenses")
    _write_header_row(expenses_sheet, _EXPENSE_HEADERS)
    for expense_row in content.expense_rows:
        receipt = ", ".join(f"{number:03d}" for number in expense_row.receipt_numbers)
        expenses_sheet.append(
            (
                expense_row.expense_date,
                expense_row.employee_name,
                expense_row.project_name,
                expense_row.vendor,
                expense_row.document_no,
                expense_row.description,
                expense_row.amount,
                expense_row.currency,
                receipt,
                "Yes" if expense_row.is_internal else "No",
            )
        )

    purchases_sheet = workbook.create_sheet("Purchases")
    _write_header_row(purchases_sheet, _PURCHASE_HEADERS)
    for purchase_row in content.purchase_rows:
        purchases_sheet.append(
            (
                f"{purchase_row.file_number:03d}" if purchase_row.file_number else "",
                purchase_row.document_date,
                purchase_row.kind,
                purchase_row.vendor,
                purchase_row.document_no,
                purchase_row.description,
                purchase_row.amount,
                purchase_row.currency,
                purchase_row.amount_base,
                "Yes" if purchase_row.provisional else "",
                purchase_row.status,
                purchase_row.payment_method,
                purchase_row.card_invoice,
            )
        )

    return workbook


def render_summary_xlsx(content: PackageContent) -> bytes:
    buffer = BytesIO()
    build_summary_workbook(content).save(buffer)
    return buffer.getvalue()
