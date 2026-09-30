"""Plain data ``AccountingService`` assembles from other modules' DTOs, shaped exactly as
``rendering.py``/``spreadsheet.py`` need it to build ``summary.pdf``/``summary.xlsx`` — kept out of
``contracts.py`` since nothing outside this module ever needs it.
"""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from time_reporting.modules.accounting.contracts import AccountantPackageTotalDTO


@dataclass(frozen=True, slots=True, kw_only=True)
class InvoiceRow:
    """One row of the summary's Invoices table."""

    number: str
    invoice_date: str
    customer_name: str
    net: Decimal
    vat: Decimal
    total: Decimal
    currency: str
    status: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ExpenseRow:
    """One row of the summary's Expenses table. ``receipt_numbers`` are the ``NNN``s
    (``ReceiptFile.arcname``'s prefix) of this line's own attachments, empty if it has none."""

    expense_date: str
    employee_name: str
    project_name: str
    vendor: str
    document_no: str
    description: str
    amount: Decimal
    currency: str
    receipt_numbers: tuple[int, ...]
    is_internal: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class PurchaseRow:
    """One row of the summary's Purchases table. A card invoice is followed by the receipts it
    settled (``is_card_receipt``, ``card_invoice`` naming the parent); their amounts are
    documentation only — the card invoice's own amount is what was paid, so only top-level rows
    count towards the total. ``provisional`` marks a base-currency amount that is still an
    estimate (unpaid, or not yet final)."""

    file_number: int | None
    document_date: str
    kind: str
    vendor: str
    document_no: str
    description: str
    amount: Decimal | None
    currency: str
    amount_base: Decimal | None
    provisional: bool
    status: str
    payment_method: str
    card_invoice: str
    is_card_receipt: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class ReceiptFile:
    """One attachment to embed in the ZIP under ``receipts/...`` — ``arcname`` is the path inside
    the archive, ``path`` the file's location on disk (from ``expenses.GetAttachmentPath``)."""

    arcname: str
    path: Path


@dataclass(frozen=True, slots=True, kw_only=True)
class PackageContent:
    """Everything ``rendering.render_summary_pdf``/``spreadsheet.write_summary_xlsx`` print, plus
    (``receipt_files``) everything the ZIP embeds alongside them. ``totals`` reuses
    ``contracts.AccountantPackageTotalDTO`` rather than a second, identically-shaped type — both
    ``GetAccountantPackageStatus`` and this module-internal content need the exact same per-
    currency total."""

    year: int
    month: int
    invoices: tuple[InvoiceRow, ...]
    expense_rows: tuple[ExpenseRow, ...]
    totals: tuple[AccountantPackageTotalDTO, ...]
    receipt_files: tuple[ReceiptFile, ...]
    base_currency: str
    purchase_rows: tuple[PurchaseRow, ...]
    purchase_total_base: Decimal
    purchase_total_provisional: bool
    purchase_files: tuple[ReceiptFile, ...]
