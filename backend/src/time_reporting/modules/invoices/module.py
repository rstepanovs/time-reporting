"""Registers the invoices module's handlers on the bus."""

from time_reporting.core.cqrs import HandlerRegistry
from time_reporting.modules.invoices.contracts import (
    CountInvoices,
    CreateInvoiceDraft,
    DeleteInvoiceDraft,
    GetInvoice,
    GetInvoicePdf,
    GetInvoicingSummary,
    IssueInvoice,
    ListInvoiceablePeriods,
    ListInvoices,
    ListInvoicesForMonth,
    MarkInvoicePaid,
    UpdateInvoiceDraft,
    VoidInvoice,
)
from time_reporting.modules.invoices.handlers import (
    CountInvoicesHandler,
    CreateInvoiceDraftHandler,
    DeleteInvoiceDraftHandler,
    GetInvoiceHandler,
    GetInvoicePdfHandler,
    GetInvoicingSummaryHandler,
    IssueInvoiceHandler,
    ListInvoiceablePeriodsHandler,
    ListInvoicesForMonthHandler,
    ListInvoicesHandler,
    MarkInvoicePaidHandler,
    UpdateInvoiceDraftHandler,
    VoidInvoiceHandler,
)


def register(registry: HandlerRegistry) -> None:
    registry.query(GetInvoice, GetInvoiceHandler)
    registry.query(ListInvoices, ListInvoicesHandler)
    registry.query(ListInvoicesForMonth, ListInvoicesForMonthHandler)
    registry.query(ListInvoiceablePeriods, ListInvoiceablePeriodsHandler)
    registry.query(GetInvoicingSummary, GetInvoicingSummaryHandler)
    registry.query(CountInvoices, CountInvoicesHandler)
    registry.query(GetInvoicePdf, GetInvoicePdfHandler)

    registry.command(CreateInvoiceDraft, CreateInvoiceDraftHandler)
    registry.command(UpdateInvoiceDraft, UpdateInvoiceDraftHandler)
    registry.command(DeleteInvoiceDraft, DeleteInvoiceDraftHandler)
    registry.command(IssueInvoice, IssueInvoiceHandler)
    registry.command(MarkInvoicePaid, MarkInvoicePaidHandler)
    registry.command(VoidInvoice, VoidInvoiceHandler)
