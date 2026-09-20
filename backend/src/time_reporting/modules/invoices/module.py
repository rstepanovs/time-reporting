"""Registers the invoices module's handlers on the bus."""

from time_reporting.core.cqrs import HandlerRegistry
from time_reporting.modules.invoices.contracts import (
    CountInvoices,
    CreateInvoiceDraft,
    DeleteInvoiceDraft,
    GetInvoice,
    ListInvoiceablePeriods,
    ListInvoices,
    UpdateInvoiceDraft,
)
from time_reporting.modules.invoices.handlers import (
    CountInvoicesHandler,
    CreateInvoiceDraftHandler,
    DeleteInvoiceDraftHandler,
    GetInvoiceHandler,
    ListInvoiceablePeriodsHandler,
    ListInvoicesHandler,
    UpdateInvoiceDraftHandler,
)


def register(registry: HandlerRegistry) -> None:
    registry.query(GetInvoice, GetInvoiceHandler)
    registry.query(ListInvoices, ListInvoicesHandler)
    registry.query(ListInvoiceablePeriods, ListInvoiceablePeriodsHandler)
    registry.query(CountInvoices, CountInvoicesHandler)

    registry.command(CreateInvoiceDraft, CreateInvoiceDraftHandler)
    registry.command(UpdateInvoiceDraft, UpdateInvoiceDraftHandler)
    registry.command(DeleteInvoiceDraft, DeleteInvoiceDraftHandler)
