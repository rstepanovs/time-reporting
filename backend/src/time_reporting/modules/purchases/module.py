"""Registers the purchases module's handlers on the bus."""

from time_reporting.core.cqrs import HandlerRegistry
from time_reporting.modules.purchases.contracts import (
    AddPurchaseDocument,
    DiscardPurchaseDocument,
    GetPurchaseDocument,
    GetPurchaseFilePath,
    ListPurchaseDocuments,
    ListPurchaseStorageKeys,
)
from time_reporting.modules.purchases.handlers import (
    AddPurchaseDocumentHandler,
    DiscardPurchaseDocumentHandler,
    GetPurchaseDocumentHandler,
    GetPurchaseFilePathHandler,
    ListPurchaseDocumentsHandler,
    ListPurchaseStorageKeysHandler,
)


def register(registry: HandlerRegistry) -> None:
    registry.query(ListPurchaseDocuments, ListPurchaseDocumentsHandler)
    registry.query(GetPurchaseDocument, GetPurchaseDocumentHandler)
    registry.query(GetPurchaseFilePath, GetPurchaseFilePathHandler)
    registry.query(ListPurchaseStorageKeys, ListPurchaseStorageKeysHandler)

    registry.command(AddPurchaseDocument, AddPurchaseDocumentHandler)
    registry.command(DiscardPurchaseDocument, DiscardPurchaseDocumentHandler)
