"""Registers the purchases module's handlers on the bus."""

from time_reporting.core.cqrs import HandlerRegistry
from time_reporting.modules.purchases.contracts import (
    AddPurchaseDocument,
    DiscardPurchaseDocument,
    GetCardInvoice,
    GetPurchaseDocument,
    GetPurchaseFilePath,
    LinkCardReceipts,
    ListPurchaseDocuments,
    ListPurchaseStorageKeys,
    ListUnlinkedCardReceipts,
    MarkPurchasePaid,
    MarkPurchaseUnpaid,
    RegisterPurchaseDocument,
    ReturnPurchaseToInbox,
    UnlinkCardReceipt,
    UpdateCardReceiptAmount,
    UpdatePurchaseDocument,
)
from time_reporting.modules.purchases.handlers import (
    AddPurchaseDocumentHandler,
    DiscardPurchaseDocumentHandler,
    GetCardInvoiceHandler,
    GetPurchaseDocumentHandler,
    GetPurchaseFilePathHandler,
    LinkCardReceiptsHandler,
    ListPurchaseDocumentsHandler,
    ListPurchaseStorageKeysHandler,
    ListUnlinkedCardReceiptsHandler,
    MarkPurchasePaidHandler,
    MarkPurchaseUnpaidHandler,
    RegisterPurchaseDocumentHandler,
    ReturnPurchaseToInboxHandler,
    UnlinkCardReceiptHandler,
    UpdateCardReceiptAmountHandler,
    UpdatePurchaseDocumentHandler,
)


def register(registry: HandlerRegistry) -> None:
    registry.query(ListPurchaseDocuments, ListPurchaseDocumentsHandler)
    registry.query(GetPurchaseDocument, GetPurchaseDocumentHandler)
    registry.query(GetPurchaseFilePath, GetPurchaseFilePathHandler)
    registry.query(ListPurchaseStorageKeys, ListPurchaseStorageKeysHandler)
    registry.query(GetCardInvoice, GetCardInvoiceHandler)
    registry.query(ListUnlinkedCardReceipts, ListUnlinkedCardReceiptsHandler)

    registry.command(AddPurchaseDocument, AddPurchaseDocumentHandler)
    registry.command(DiscardPurchaseDocument, DiscardPurchaseDocumentHandler)
    registry.command(RegisterPurchaseDocument, RegisterPurchaseDocumentHandler)
    registry.command(UpdatePurchaseDocument, UpdatePurchaseDocumentHandler)
    registry.command(ReturnPurchaseToInbox, ReturnPurchaseToInboxHandler)
    registry.command(MarkPurchasePaid, MarkPurchasePaidHandler)
    registry.command(MarkPurchaseUnpaid, MarkPurchaseUnpaidHandler)
    registry.command(LinkCardReceipts, LinkCardReceiptsHandler)
    registry.command(UnlinkCardReceipt, UnlinkCardReceiptHandler)
    registry.command(UpdateCardReceiptAmount, UpdateCardReceiptAmountHandler)
