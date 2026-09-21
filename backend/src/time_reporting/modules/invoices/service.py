"""Invoice domain logic.

Changes are flushed through the repository; the bus commits. Reads other modules only through
their ``contracts.py`` messages, dispatched on the shared ``Bus``.
"""

import base64
import hashlib
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from time_reporting.core.cqrs import Bus
from time_reporting.db.mixins import utc_now
from time_reporting.modules.audit.contracts import AuditAction, RecordAuditEvent
from time_reporting.modules.company.contracts import (
    AllocateInvoiceNumber,
    CompanyLogoDTO,
    CompanySettingsDTO,
    GetCompanyLogo,
    GetCompanySettings,
)
from time_reporting.modules.customers.contracts import (
    CustomerDTO,
    GetCustomerById,
    GetCustomersByIds,
)
from time_reporting.modules.invoices.contracts import (
    BillingItemRateMissingError,
    CompanyProfileIncompleteError,
    CountInvoices,
    CreateInvoiceDraft,
    CurrencyTotalDTO,
    DeleteInvoiceDraft,
    GetInvoice,
    GetInvoicePdf,
    GetInvoicingSummary,
    InvoiceableCustomerDTO,
    InvoiceablePeriodDTO,
    InvoiceCustomerDTO,
    InvoiceCustomerNotFoundError,
    InvoiceDTO,
    InvoiceEmptyError,
    InvoiceLineChange,
    InvoiceLineDTO,
    InvoiceLineKind,
    InvoiceLineNotFoundError,
    InvoiceNoPeriodsError,
    InvoiceNotDraftError,
    InvoiceNotFoundError,
    InvoiceNotIssuedError,
    InvoiceNotVoidableError,
    InvoicePageDTO,
    InvoicePdfDTO,
    InvoicePeriodDTO,
    InvoicePeriodNotEligibleError,
    InvoiceStatus,
    InvoiceSummaryDTO,
    InvoicingSummaryDTO,
    IssueInvoice,
    ListInvoiceablePeriods,
    ListInvoices,
    MarkInvoicePaid,
    UpdateInvoiceDraft,
    VoidInvoice,
)
from time_reporting.modules.invoices.models import Invoice, InvoiceBillingPeriod, InvoiceLine
from time_reporting.modules.invoices.rendering import render_invoice_pdf
from time_reporting.modules.invoices.repository import (
    InvoiceBillingPeriodRepository,
    InvoiceLineRepository,
    InvoiceRepository,
)
from time_reporting.modules.projects.contracts import (
    BillingUnit,
    GetProjectBillingItemsByIds,
    GetProjectsByIds,
    ProjectBillingItemDTO,
    ProjectDTO,
)
from time_reporting.modules.timesheets.contracts import (
    BillingPeriodAlreadyInvoicedError,
    BillingPeriodExportRowDTO,
    BillingPeriodListItemDTO,
    BillingPeriodNotFoundError,
    BillingPeriodRef,
    ClearBillingPeriodsInvoiced,
    GetBillingPeriodExportRows,
    ListBillingPeriods,
    MarkBillingPeriodsInvoiced,
)

# Company essentials an invoice can't be printed without — see CompanyProfileIncompleteError.
_REQUIRED_COMPANY_FIELDS = ("legal_name", "org_number")


def _build_seller_snapshot(
    company: CompanySettingsDTO, logo: CompanyLogoDTO | None
) -> dict[str, Any]:
    """A plain dict matching ``faktura_printer.Seller`` kwargs, plus ``late_interest`` (popped
    back out in ``rendering.py`` — ``Seller`` itself has no such field)."""
    street = company.address.street
    if company.address.street2:
        street = f"{street}, {company.address.street2}"
    return {
        "name": company.legal_name,
        "address": {
            "street": street,
            "postal_code": company.address.postal_code,
            "city": company.address.city,
            "country": company.address.country,
        },
        "logo": f"data:{logo.content_type};base64,{base64.b64encode(logo.content).decode()}"
        if logo is not None
        else None,
        "phone": company.phone,
        "email": company.email,
        "registered_office": company.registered_office,
        "bankgiro": company.bankgiro,
        "iban": company.iban,
        "bic": company.bic,
        "org_number": company.org_number,
        "vat_number": company.vat_number,
        "f_tax_approved": company.f_tax_approved,
        "late_interest": company.late_interest,
    }


def _build_buyer_snapshot(customer: CustomerDTO) -> dict[str, Any]:
    """A plain dict matching ``faktura_printer.Buyer`` kwargs, plus ``customer_number`` (popped
    back out in ``rendering.py`` — ``Buyer`` itself has no such field)."""
    street = customer.billing_address.line1
    if customer.billing_address.line2:
        street = f"{street}, {customer.billing_address.line2}"
    return {
        "name": customer.legal_name or customer.name,
        "address": {
            "street": street,
            "postal_code": customer.billing_address.postal_code or "",
            "city": customer.billing_address.city,
            "country": customer.billing_address.country,
        },
        "org_number": customer.tax_id or "",
        "customer_number": customer.customer_number or "",
    }


@dataclass(frozen=True, slots=True, kw_only=True)
class _GeneratedLine:
    """A line built by ``_generate_lines``, before it has an id or position."""

    kind: InvoiceLineKind
    description: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    amount: Decimal
    project_id: UUID | None
    billing_item_id: UUID | None


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _generate_lines(
    rows_by_ref: dict[BillingPeriodRef, tuple[BillingPeriodExportRowDTO, ...]],
    projects_by_id: dict[UUID, ProjectDTO],
    items_by_id: dict[UUID, ProjectBillingItemDTO],
) -> tuple[list[_GeneratedLine], tuple[str, ...]]:
    """One ``TIME`` line per (project, billing item) summed within each period, plus one
    ``EXPENSE`` line per approved expense line (marked up, never aggregated — each keeps its own
    vendor/date/description). Returns the lines and the names of any ``hour``/``day`` item with no
    ``unit_rate`` — a non-empty second element means the whole draft must be refused.
    """
    lines: list[_GeneratedLine] = []
    missing_rate: set[str] = set()

    for ref, rows in rows_by_ref.items():
        project = projects_by_id[ref.project_id]

        time_totals: dict[UUID, Decimal] = defaultdict(Decimal)
        for row in rows:
            if row.unit is not BillingUnit.AMOUNT:
                time_totals[row.billing_item_id] += row.quantity
        for item_id, quantity in time_totals.items():
            item = items_by_id[item_id]
            if item.unit_rate is None:
                missing_rate.add(f"{project.name} — {item.name}")
                continue
            lines.append(
                _GeneratedLine(
                    kind=InvoiceLineKind.TIME,
                    description=f"{project.name} — {item.name} ({ref.period_start:%Y-%m})",
                    quantity=quantity,
                    unit=item.unit.value,
                    unit_price=item.unit_rate,
                    amount=_quantize(quantity * item.unit_rate),
                    project_id=ref.project_id,
                    billing_item_id=item_id,
                )
            )

        for row in rows:
            if row.unit is not BillingUnit.AMOUNT:
                continue
            item = items_by_id[row.billing_item_id]
            markup = item.markup_percent or Decimal("0")
            unit_price = _quantize(row.quantity * (Decimal("1") + markup / Decimal("100")))
            description_parts = [row.entry_date.isoformat()]
            if row.vendor:
                description_parts.append(row.vendor)
            if row.description:
                description_parts.append(row.description)
            lines.append(
                _GeneratedLine(
                    kind=InvoiceLineKind.EXPENSE,
                    description=" — ".join(description_parts),
                    quantity=Decimal("1"),
                    unit="pcs",
                    unit_price=unit_price,
                    amount=unit_price,
                    project_id=ref.project_id,
                    billing_item_id=row.billing_item_id,
                )
            )

    return lines, tuple(sorted(missing_rate))


class InvoiceService:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._invoices = InvoiceRepository(bus.session)
        self._lines = InvoiceLineRepository(bus.session)
        self._period_links = InvoiceBillingPeriodRepository(bus.session)

    async def create_draft(self, command: CreateInvoiceDraft) -> InvoiceDTO:
        if not command.periods:
            raise InvoiceNoPeriodsError()
        customer = await self._bus.query(GetCustomerById(customer_id=command.customer_id))
        if customer is None:
            raise InvoiceCustomerNotFoundError(command.customer_id)

        project_ids = frozenset(ref.project_id for ref in command.periods)
        projects_by_id = {
            project.id: project
            for project in await self._bus.query(GetProjectsByIds(project_ids=project_ids))
        }

        rows_by_ref: dict[BillingPeriodRef, tuple[BillingPeriodExportRowDTO, ...]] = {}
        for ref in command.periods:
            project = projects_by_id.get(ref.project_id)
            if project is None or project.customer.id != command.customer_id:
                raise InvoicePeriodNotEligibleError(
                    ref.project_id, ref.period_start, "does not belong to this customer"
                )
            if project.is_internal:
                raise InvoicePeriodNotEligibleError(
                    ref.project_id, ref.period_start, "project is internal"
                )
            # Checked here (not only via the nested MarkBillingPeriodsInvoiced below) so a period
            # that isn't sent, or is already invoiced, is caught before anything is written — a
            # late failure inside MarkBillingPeriodsInvoiced would otherwise race the
            # InvoiceBillingPeriod rows' own unique constraint on (project_id, period_start).
            existing = await self._bus.query(
                ListBillingPeriods(
                    project_id=ref.project_id,
                    month_from=ref.period_start,
                    month_to=ref.period_start,
                    limit=1,
                    offset=0,
                )
            )
            if not existing.items:
                raise InvoicePeriodNotEligibleError(
                    ref.project_id, ref.period_start, "not sent to billing"
                )
            if existing.items[0].invoice_id is not None:
                raise InvoicePeriodNotEligibleError(
                    ref.project_id, ref.period_start, "already invoiced"
                )
            rows_by_ref[ref] = await self._bus.query(
                GetBillingPeriodExportRows(project_id=ref.project_id, period_start=ref.period_start)
            )

        items_by_id = {
            item.id: item
            for item in await self._bus.query(
                GetProjectBillingItemsByIds(
                    billing_item_ids=frozenset(
                        row.billing_item_id for rows in rows_by_ref.values() for row in rows
                    )
                )
            )
        }
        generated, missing_rate_items = _generate_lines(rows_by_ref, projects_by_id, items_by_id)
        if missing_rate_items:
            raise BillingItemRateMissingError(missing_rate_items)

        settings = await self._bus.query(GetCompanySettings())
        locale = customer.invoice_locale or settings.default_invoice_locale
        due_date = command.invoice_date + timedelta(days=customer.payment_terms_days)
        subtotal = sum((line.amount for line in generated), start=Decimal("0"))
        vat_amount = (
            _quantize(subtotal * customer.vat_rate / Decimal("100"))
            if customer.vat_rate is not None
            else Decimal("0")
        )

        invoice = Invoice(
            customer_id=customer.id,
            status=InvoiceStatus.DRAFT,
            invoice_date=command.invoice_date,
            due_date=due_date,
            currency=customer.currency,
            locale=locale,
            vat_rate=customer.vat_rate,
            vat_note=customer.vat_note,
            your_reference=customer.your_reference,
            subtotal=subtotal,
            vat_amount=vat_amount,
            total=subtotal + vat_amount,
        )
        await self._invoices.save(invoice)
        for position, line in enumerate(generated, start=1):
            await self._lines.save(
                InvoiceLine(
                    invoice_id=invoice.id,
                    position=position,
                    kind=line.kind,
                    description=line.description,
                    quantity=line.quantity,
                    unit=line.unit,
                    unit_price=line.unit_price,
                    amount=line.amount,
                    project_id=line.project_id,
                    billing_item_id=line.billing_item_id,
                )
            )
        for ref in command.periods:
            await self._period_links.save(
                InvoiceBillingPeriod(
                    invoice_id=invoice.id, project_id=ref.project_id, period_start=ref.period_start
                )
            )

        try:
            await self._bus.execute(
                MarkBillingPeriodsInvoiced(periods=command.periods, invoice_id=invoice.id)
            )
        except BillingPeriodAlreadyInvoicedError as exc:
            raise InvoicePeriodNotEligibleError(
                exc.project_id, exc.period_start, "already invoiced"
            ) from exc
        except BillingPeriodNotFoundError as exc:
            raise InvoicePeriodNotEligibleError(
                exc.project_id, exc.period_start, "not sent to billing"
            ) from exc

        await self._bus.execute(
            RecordAuditEvent(
                actor_id=command.actor_id,
                action=AuditAction.INVOICE_CREATED,
                entity_type="invoice",
                entity_id=str(invoice.id),
                summary=f"Created draft invoice for {customer.name}",
            )
        )

        return await self.get_invoice(invoice.id)

    async def get_invoice(self, invoice_id: UUID) -> InvoiceDTO:
        invoice = await self._invoices.get(invoice_id)
        if invoice is None:
            raise InvoiceNotFoundError(invoice_id)
        customer = await self._bus.query(GetCustomerById(customer_id=invoice.customer_id))
        # `customers.id` is referenced `ON DELETE RESTRICT`, so the customer always still exists.
        assert customer is not None

        lines = await self._lines.list_for_invoice(invoice.id)
        period_links = await self._period_links.list_for_invoice(invoice.id)
        projects_by_id = {
            project.id: project
            for project in await self._bus.query(
                GetProjectsByIds(project_ids=frozenset(link.project_id for link in period_links))
            )
        }

        return InvoiceDTO(
            id=invoice.id,
            customer=InvoiceCustomerDTO(
                id=customer.id, name=customer.name, currency=customer.currency
            ),
            status=invoice.status,
            number=invoice.number,
            invoice_date=invoice.invoice_date,
            due_date=invoice.due_date,
            currency=invoice.currency,
            locale=invoice.locale,
            vat_rate=invoice.vat_rate,
            vat_note=invoice.vat_note,
            your_reference=invoice.your_reference,
            notes=invoice.notes,
            subtotal=invoice.subtotal,
            vat_amount=invoice.vat_amount,
            total=invoice.total,
            issued_at=invoice.issued_at,
            paid_on=invoice.paid_on,
            voided_at=invoice.voided_at,
            void_reason=invoice.void_reason,
            lines=tuple(
                InvoiceLineDTO(
                    id=line.id,
                    position=line.position,
                    kind=line.kind,
                    description=line.description,
                    quantity=line.quantity,
                    unit=line.unit,
                    unit_price=line.unit_price,
                    amount=line.amount,
                    project_id=line.project_id,
                    billing_item_id=line.billing_item_id,
                )
                for line in lines
            ),
            # `invoice_billing_periods.project_id` is `ON DELETE RESTRICT`, so the project always
            # still exists for every link.
            periods=tuple(
                InvoicePeriodDTO(
                    project_id=link.project_id,
                    project_name=projects_by_id[link.project_id].name,
                    period_start=link.period_start,
                )
                for link in period_links
            ),
            created_at=invoice.created_at,
            updated_at=invoice.updated_at,
        )

    async def handle_get(self, query: GetInvoice) -> InvoiceDTO:
        return await self.get_invoice(query.invoice_id)

    async def list_invoices(self, query: ListInvoices) -> InvoicePageDTO:
        invoices = await self._invoices.get_page(
            customer_id=query.customer_id,
            status=query.status,
            date_from=query.date_from,
            date_to=query.date_to,
            limit=query.limit,
            offset=query.offset,
        )
        total = await self._invoices.count(
            customer_id=query.customer_id,
            status=query.status,
            date_from=query.date_from,
            date_to=query.date_to,
        )
        customers_by_id = {
            customer.id: customer
            for customer in await self._bus.query(
                GetCustomersByIds(
                    customer_ids=frozenset(invoice.customer_id for invoice in invoices)
                )
            )
        }
        items = tuple(
            InvoiceSummaryDTO(
                id=invoice.id,
                customer_id=invoice.customer_id,
                customer_name=customers_by_id[invoice.customer_id].name,
                status=invoice.status,
                number=invoice.number,
                invoice_date=invoice.invoice_date,
                due_date=invoice.due_date,
                currency=invoice.currency,
                total=invoice.total,
            )
            for invoice in invoices
        )
        return InvoicePageDTO(items=items, total=total, limit=query.limit, offset=query.offset)

    async def list_invoiceable_periods(
        self, _query: ListInvoiceablePeriods
    ) -> tuple[InvoiceableCustomerDTO, ...]:
        page = await self._bus.query(ListBillingPeriods(invoiced=False, limit=10_000, offset=0))
        if not page.items:
            return ()
        projects_by_id = {
            project.id: project
            for project in await self._bus.query(
                GetProjectsByIds(project_ids=frozenset(item.project_id for item in page.items))
            )
        }

        by_customer: dict[UUID, list[BillingPeriodListItemDTO]] = defaultdict(list)
        for item in page.items:
            project = projects_by_id.get(item.project_id)
            # An internal project can never be sent to billing in the first place (see
            # `timesheets.ProjectIsInternalError`), so this branch is unreachable today — kept as
            # the same defense-in-depth the module boundary encourages elsewhere.
            if project is None or project.is_internal:
                continue
            by_customer[project.customer.id].append(item)

        customers: list[InvoiceableCustomerDTO] = []
        for customer_id, items in by_customer.items():
            customer_info = projects_by_id[items[0].project_id].customer
            customers.append(
                InvoiceableCustomerDTO(
                    customer_id=customer_id,
                    customer_name=customer_info.name,
                    currency=customer_info.currency,
                    periods=tuple(
                        InvoiceablePeriodDTO(
                            project_id=item.project_id,
                            project_name=item.project_name,
                            period_start=item.period_start,
                            period_end=item.period_end,
                            sent_at=item.sent_at,
                        )
                        for item in sorted(items, key=lambda i: (i.project_name, i.period_start))
                    ),
                )
            )
        return tuple(sorted(customers, key=lambda customer: customer.customer_name))

    async def get_invoicing_summary(self, query: GetInvoicingSummary) -> InvoicingSummaryDTO:
        periods_to_invoice = sum(
            len(customer.periods)
            for customer in await self.list_invoiceable_periods(ListInvoiceablePeriods())
        )
        unpaid_totals = tuple(
            CurrencyTotalDTO(currency=currency, amount=amount)
            for currency, amount in await self._invoices.sum_unpaid_by_currency()
        )
        overdue_count = await self._invoices.count_overdue(query.today)
        return InvoicingSummaryDTO(
            periods_to_invoice=periods_to_invoice,
            unpaid_totals=unpaid_totals,
            overdue_count=overdue_count,
        )

    async def count_invoices(self, query: CountInvoices) -> int:
        return await self._invoices.count_for_customer(query.customer_id)

    async def update_draft(self, command: UpdateInvoiceDraft) -> InvoiceDTO:
        invoice = await self._invoices.get(command.invoice_id)
        if invoice is None:
            raise InvoiceNotFoundError(command.invoice_id)
        if invoice.status is not InvoiceStatus.DRAFT:
            raise InvoiceNotDraftError(invoice.id, invoice.status)

        existing_by_id = {line.id: line for line in await self._lines.list_for_invoice(invoice.id)}
        resolved: list[tuple[InvoiceLine | None, InvoiceLineChange]] = []
        for change in command.lines:
            existing_line: InvoiceLine | None = None
            if change.line_id is not None:
                existing_line = existing_by_id.get(change.line_id)
                if existing_line is None:
                    raise InvoiceLineNotFoundError(change.line_id)
            resolved.append((existing_line, change))

        if command.invoice_date is not None:
            invoice.invoice_date = command.invoice_date
        if command.due_date is not None:
            invoice.due_date = command.due_date
        if command.vat_rate is not None:
            invoice.vat_rate = command.vat_rate
        if command.vat_note is not None:
            invoice.vat_note = command.vat_note
        if command.your_reference is not None:
            invoice.your_reference = command.your_reference
        if command.notes is not None:
            invoice.notes = command.notes
        if "vat_rate" in command.clear_fields:
            invoice.vat_rate = None
        if "vat_note" in command.clear_fields:
            invoice.vat_note = None
        if "your_reference" in command.clear_fields:
            invoice.your_reference = None
        if "notes" in command.clear_fields:
            invoice.notes = None

        for existing_line, change in resolved:
            amount = _quantize(change.quantity * change.unit_price)
            if existing_line is not None:
                existing_line.description = change.description
                existing_line.quantity = change.quantity
                existing_line.unit = change.unit
                existing_line.unit_price = change.unit_price
                existing_line.amount = amount
                await self._lines.save(existing_line)
            else:
                position = await self._lines.next_position(invoice.id)
                await self._lines.save(
                    InvoiceLine(
                        invoice_id=invoice.id,
                        position=position,
                        kind=InvoiceLineKind.MANUAL,
                        description=change.description,
                        quantity=change.quantity,
                        unit=change.unit,
                        unit_price=change.unit_price,
                        amount=amount,
                        project_id=None,
                        billing_item_id=None,
                    )
                )

        for line_id in command.delete_line_ids:
            line = existing_by_id.get(line_id)
            if line is not None:
                await self._lines.delete(line)

        remaining = await self._lines.list_for_invoice(invoice.id)
        subtotal = sum((line.amount for line in remaining), start=Decimal("0"))
        vat_amount = (
            _quantize(subtotal * invoice.vat_rate / Decimal("100"))
            if invoice.vat_rate is not None
            else Decimal("0")
        )
        invoice.subtotal = subtotal
        invoice.vat_amount = vat_amount
        invoice.total = subtotal + vat_amount
        await self._invoices.save(invoice)

        return await self.get_invoice(invoice.id)

    async def delete_draft(self, command: DeleteInvoiceDraft) -> None:
        invoice = await self._invoices.get(command.invoice_id)
        if invoice is None:
            raise InvoiceNotFoundError(command.invoice_id)
        if invoice.status is not InvoiceStatus.DRAFT:
            raise InvoiceNotDraftError(invoice.id, invoice.status)
        customer = await self._bus.query(GetCustomerById(customer_id=invoice.customer_id))
        assert customer is not None

        await self._invoices.delete(invoice)
        await self._bus.execute(ClearBillingPeriodsInvoiced(invoice_id=invoice.id))
        await self._bus.execute(
            RecordAuditEvent(
                actor_id=command.actor_id,
                action=AuditAction.INVOICE_DELETED,
                entity_type="invoice",
                entity_id=str(invoice.id),
                summary=f"Deleted draft invoice for {customer.name}",
            )
        )

    async def issue_invoice(self, command: IssueInvoice) -> InvoiceDTO:
        invoice = await self._invoices.get(command.invoice_id)
        if invoice is None:
            raise InvoiceNotFoundError(command.invoice_id)
        if invoice.status is not InvoiceStatus.DRAFT:
            raise InvoiceNotDraftError(invoice.id, invoice.status)

        lines = await self._lines.list_for_invoice(invoice.id)
        if not lines:
            raise InvoiceEmptyError(invoice.id)

        company = await self._bus.query(GetCompanySettings())
        missing = tuple(field for field in _REQUIRED_COMPANY_FIELDS if not getattr(company, field))
        if missing:
            raise CompanyProfileIncompleteError(missing)

        customer = await self._bus.query(GetCustomerById(customer_id=invoice.customer_id))
        assert customer is not None
        logo = await self._bus.query(GetCompanyLogo())

        number = await self._bus.execute(AllocateInvoiceNumber())
        seller = _build_seller_snapshot(company, logo)
        buyer = _build_buyer_snapshot(customer)
        invoice.number = number
        invoice.seller_snapshot = seller
        invoice.buyer_snapshot = buyer
        await self._invoices.save(invoice)

        # Re-read as a DTO now that `number` is set, so the rendered PDF prints it too.
        dto = await self.get_invoice(invoice.id)
        pdf = await render_invoice_pdf(dto, seller=seller, buyer=buyer, draft=False)

        invoice.pdf = pdf
        invoice.pdf_sha256 = hashlib.sha256(pdf).hexdigest()
        invoice.issued_at = utc_now()
        invoice.issued_by_id = command.actor_id
        invoice.status = InvoiceStatus.ISSUED
        await self._invoices.save(invoice)

        await self._bus.execute(
            RecordAuditEvent(
                actor_id=command.actor_id,
                action=AuditAction.INVOICE_ISSUED,
                entity_type="invoice",
                entity_id=str(invoice.id),
                summary=f"Issued invoice {number} for {customer.name}",
            )
        )
        return await self.get_invoice(invoice.id)

    async def mark_paid(self, command: MarkInvoicePaid) -> InvoiceDTO:
        invoice = await self._invoices.get(command.invoice_id)
        if invoice is None:
            raise InvoiceNotFoundError(command.invoice_id)
        if invoice.status is not InvoiceStatus.ISSUED:
            raise InvoiceNotIssuedError(invoice.id, invoice.status)

        invoice.status = InvoiceStatus.PAID
        invoice.paid_on = command.paid_on
        await self._invoices.save(invoice)

        await self._bus.execute(
            RecordAuditEvent(
                actor_id=command.actor_id,
                action=AuditAction.INVOICE_PAID,
                entity_type="invoice",
                entity_id=str(invoice.id),
                summary=f"Marked invoice {invoice.number} paid",
            )
        )
        return await self.get_invoice(invoice.id)

    async def void_invoice(self, command: VoidInvoice) -> InvoiceDTO:
        invoice = await self._invoices.get(command.invoice_id)
        if invoice is None:
            raise InvoiceNotFoundError(command.invoice_id)
        if invoice.status not in (InvoiceStatus.ISSUED, InvoiceStatus.PAID):
            raise InvoiceNotVoidableError(invoice.id, invoice.status)

        invoice.status = InvoiceStatus.VOID
        invoice.voided_at = utc_now()
        invoice.void_reason = command.reason
        await self._invoices.save(invoice)

        await self._bus.execute(ClearBillingPeriodsInvoiced(invoice_id=invoice.id))
        await self._bus.execute(
            RecordAuditEvent(
                actor_id=command.actor_id,
                action=AuditAction.INVOICE_VOIDED,
                entity_type="invoice",
                entity_id=str(invoice.id),
                summary=f"Voided invoice {invoice.number}",
            )
        )
        return await self.get_invoice(invoice.id)

    async def get_pdf(self, query: GetInvoicePdf) -> InvoicePdfDTO:
        invoice = await self._invoices.get(query.invoice_id)
        if invoice is None:
            raise InvoiceNotFoundError(query.invoice_id)

        if invoice.status is not InvoiceStatus.DRAFT:
            # Rendered and stored once, at IssueInvoice time — never re-rendered afterwards, even
            # once paid or void (VoidInvoice keeps the PDF as a record of what was cancelled).
            assert invoice.pdf is not None
            return InvoicePdfDTO(content=invoice.pdf, filename=f"invoice-{invoice.number}.pdf")

        customer = await self._bus.query(GetCustomerById(customer_id=invoice.customer_id))
        assert customer is not None
        company = await self._bus.query(GetCompanySettings())
        logo = await self._bus.query(GetCompanyLogo())
        dto = await self.get_invoice(invoice.id)
        pdf = await render_invoice_pdf(
            dto,
            seller=_build_seller_snapshot(company, logo),
            buyer=_build_buyer_snapshot(customer),
            draft=True,
        )
        return InvoicePdfDTO(content=pdf, filename=f"invoice-draft-{invoice.id}.pdf")
