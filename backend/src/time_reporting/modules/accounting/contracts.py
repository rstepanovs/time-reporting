"""Public contract of the accounting module.

No tables of its own: assembles the monthly accountant handoff package (a status summary and a
downloadable ZIP) purely from other modules' data. Depends on ``invoices.contracts``,
``expenses.contracts`` and ``company.contracts`` (the header printed on ``summary.pdf``/
``summary.xlsx``); nothing depends on ``accounting``, so it registers last in
``modules/registry.py``.
"""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from time_reporting.core.cqrs import Query


@dataclass(frozen=True, slots=True, kw_only=True)
class AccountantPackageTotalDTO:
    """One currency's totals for the month. Invoiced and claimed-expense totals are never summed
    together (a customer invoice and a purchase receipt aren't the same kind of money), and
    ``invoiced_total`` only counts ``issued``/``paid`` invoices — a voided one is still listed in
    ``summary.pdf`` (as a record that the number was used and cancelled) but contributes nothing
    to the total."""

    currency: str
    invoiced_total: Decimal
    expense_total: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class AccountantPackageStatusDTO:
    """What ``BuildAccountantPackage`` would produce for ``year``/``month`` right now, plus every
    reason it might be incomplete — for the accounting page to show before anything downloads.
    ``invoice_count``/``expense_line_count`` are exactly what the ZIP would contain."""

    year: int
    month: int
    invoice_count: int
    expense_line_count: int
    totals: tuple[AccountantPackageTotalDTO, ...]
    # A draft invoice dated in this month — no PDF yet, so it isn't in the package; the accountant
    # should know it exists so nothing is missed once it's issued.
    draft_invoice_count: int
    # A report whose period is this month but isn't (yet) approved — its lines aren't in the
    # package until it is.
    unapproved_expense_report_count: int
    # A billing period sent within this month that no invoice covers yet.
    uninvoiced_sent_period_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class GetAccountantPackageStatus(Query[AccountantPackageStatusDTO]):
    year: int
    month: int


@dataclass(frozen=True, slots=True, kw_only=True)
class AccountantPackageDTO:
    """A freshly built ZIP file on disk. ``path`` points at a temporary file the caller (the
    router) streams back and deletes once sent — it is never a location any other request could
    read, and nothing about it is persisted."""

    path: Path
    filename: str


@dataclass(frozen=True, slots=True, kw_only=True)
class BuildAccountantPackage(Query[AccountantPackageDTO]):
    """Builds the ZIP fresh on every call — a query, not a command: nothing is written to the
    database, matching ``invoices.GetInvoicePdf``'s draft-preview precedent. ``actor_id`` is
    passed through to every ``expenses.GetAttachmentPath`` read for a receipt file — the router's
    ``AccountantDep`` already grants read access to every attachment, but the query still needs a
    viewer to check."""

    year: int
    month: int
    actor_id: UUID
