"""Renders an ``InvoiceDTO`` to PDF via ``faktura-printer``.

The only file in the whole app importing ``faktura_printer`` — everything it needs travels in as
plain dicts (``seller``/``buyer``, built by ``service._build_seller_snapshot``/
``_build_buyer_snapshot`` and, for an issued invoice, the very same dicts read back from
``Invoice.seller_snapshot``/``buyer_snapshot``), so this module depends on nothing from the rest of
the app beyond ``invoices.contracts``.
"""

import asyncio
from decimal import Decimal
from pathlib import Path
from tempfile import gettempdir
from typing import Any

from faktura_printer import Buyer, Invoice, Item, Seller, Totals
from faktura_printer import render_pdf as _render_pdf

# `InvoiceInfo` isn't re-exported from the package root (see faktura-printer's README "Public
# API" table) — imported from its actual module instead, still fully typed (py.typed).
from faktura_printer.models import InvoiceInfo

from time_reporting.modules.invoices.contracts import InvoiceDTO

# render_pdf(untrusted=True) requires a base_dir even though nothing rendered here ever resolves
# to a file on disk (the logo is a `data:` URI, everything else is plain text) — any existing
# directory works, and the system temp dir is always present.
_SCRATCH_BASE_DIR = Path(gettempdir())


def _build_invoice(
    dto: InvoiceDTO, *, seller: dict[str, Any], buyer: dict[str, Any], draft: bool
) -> Invoice:
    # late_interest/customer_number travel inside the seller/buyer snapshot dicts (see
    # service.py) since Invoice/InvoiceBillingPeriod has no columns of its own for them, but
    # faktura-printer prints them on `invoice`, not `seller`/`buyer` — pulled back out here.
    seller_fields = dict(seller)
    late_interest = seller_fields.pop("late_interest", "")
    buyer_fields = dict(buyer)
    customer_number = buyer_fields.pop("customer_number", "")

    notes = dto.notes or ""
    if dto.vat_rate is None and dto.vat_note:
        notes = f"{dto.vat_note}\n\n{notes}" if notes else dto.vat_note

    return Invoice(
        locale=dto.locale,
        labels={"title": "UTKAST/DRAFT"} if draft else {},
        seller=Seller(**seller_fields),
        buyer=Buyer(**buyer_fields),
        invoice=InvoiceInfo(
            number=dto.number or "DRAFT",
            customer_number=customer_number,
            currency=dto.currency,
            date=dto.invoice_date,
            due_date=dto.due_date,
            late_interest=late_interest,
            your_reference=dto.your_reference or "",
        ),
        items=[
            Item(
                description=line.description,
                quantity=line.quantity,
                unit=line.unit,
                unit_price=line.unit_price,
                amount=line.amount,
            )
            for line in dto.lines
        ],
        totals=Totals(
            net=dto.subtotal,
            excl_vat=dto.subtotal,
            vat_rate=dto.vat_rate if dto.vat_rate is not None else Decimal("0"),
            vat_amount=dto.vat_amount,
            total=dto.total,
        ),
        notes=notes,
    )


async def render_invoice_pdf(
    dto: InvoiceDTO, *, seller: dict[str, Any], buyer: dict[str, Any], draft: bool
) -> bytes:
    """Render ``dto`` to PDF bytes.

    ``draft=True`` labels the PDF "UTKAST/DRAFT" and prints a placeholder invoice number — the
    caller decides whether the result is stored (only ``IssueInvoice``, with ``draft=False``,
    does). WeasyPrint is CPU-bound, so the actual render runs in a thread.
    """
    invoice = _build_invoice(dto, seller=seller, buyer=buyer, draft=draft)
    return await asyncio.to_thread(_render_pdf, invoice, base_dir=_SCRATCH_BASE_DIR, untrusted=True)
