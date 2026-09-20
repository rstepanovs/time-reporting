"""Command and query handlers of the invoices module (registered in ``invoices.module``).

Handlers translate between bus messages and the service and never return ORM entities.
"""

from time_reporting.core.cqrs import Bus
from time_reporting.modules.invoices.contracts import (
    CountInvoices,
    CreateInvoiceDraft,
    DeleteInvoiceDraft,
    GetInvoice,
    GetInvoicePdf,
    InvoiceableCustomerDTO,
    InvoiceDTO,
    InvoicePageDTO,
    InvoicePdfDTO,
    IssueInvoice,
    ListInvoiceablePeriods,
    ListInvoices,
    MarkInvoicePaid,
    UpdateInvoiceDraft,
    VoidInvoice,
)
from time_reporting.modules.invoices.service import InvoiceService


class CreateInvoiceDraftHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = InvoiceService(bus)

    async def handle(self, command: CreateInvoiceDraft) -> InvoiceDTO:
        return await self._service.create_draft(command)


class GetInvoiceHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = InvoiceService(bus)

    async def handle(self, query: GetInvoice) -> InvoiceDTO:
        return await self._service.handle_get(query)


class ListInvoicesHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = InvoiceService(bus)

    async def handle(self, query: ListInvoices) -> InvoicePageDTO:
        return await self._service.list_invoices(query)


class ListInvoiceablePeriodsHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = InvoiceService(bus)

    async def handle(self, query: ListInvoiceablePeriods) -> tuple[InvoiceableCustomerDTO, ...]:
        return await self._service.list_invoiceable_periods(query)


class CountInvoicesHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = InvoiceService(bus)

    async def handle(self, query: CountInvoices) -> int:
        return await self._service.count_invoices(query)


class UpdateInvoiceDraftHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = InvoiceService(bus)

    async def handle(self, command: UpdateInvoiceDraft) -> InvoiceDTO:
        return await self._service.update_draft(command)


class DeleteInvoiceDraftHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = InvoiceService(bus)

    async def handle(self, command: DeleteInvoiceDraft) -> None:
        await self._service.delete_draft(command)


class IssueInvoiceHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = InvoiceService(bus)

    async def handle(self, command: IssueInvoice) -> InvoiceDTO:
        return await self._service.issue_invoice(command)


class MarkInvoicePaidHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = InvoiceService(bus)

    async def handle(self, command: MarkInvoicePaid) -> InvoiceDTO:
        return await self._service.mark_paid(command)


class VoidInvoiceHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = InvoiceService(bus)

    async def handle(self, command: VoidInvoice) -> InvoiceDTO:
        return await self._service.void_invoice(command)


class GetInvoicePdfHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = InvoiceService(bus)

    async def handle(self, query: GetInvoicePdf) -> InvoicePdfDTO:
        return await self._service.get_pdf(query)
