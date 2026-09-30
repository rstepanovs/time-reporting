"""Command and query handlers of the purchases module (registered in ``purchases.module``).

Handlers translate between bus messages and the service/repository and never return ORM entities.
"""

from time_reporting.core.cqrs import Bus
from time_reporting.modules.purchases.contracts import (
    AddPurchaseDocument,
    DiscardPurchaseDocument,
    GetPurchaseDocument,
    GetPurchaseFilePath,
    ListPurchaseDocuments,
    ListPurchaseStorageKeys,
    PurchaseDocumentDTO,
    PurchaseFileDTO,
)
from time_reporting.modules.purchases.models import PurchaseDocument
from time_reporting.modules.purchases.repository import PurchaseDocumentRepository
from time_reporting.modules.purchases.service import PurchaseService


def to_dto(document: PurchaseDocument) -> PurchaseDocumentDTO:
    return PurchaseDocumentDTO(
        id=document.id,
        stage=document.stage,
        kind=document.kind,
        vendor=document.vendor,
        document_no=document.document_no,
        description=document.description,
        document_date=document.document_date,
        due_date=document.due_date,
        payment_status=document.payment_status,
        paid_on=document.paid_on,
        payment_method=document.payment_method,
        card_invoice_id=document.card_invoice_id,
        amount=document.amount,
        currency=document.currency,
        vat_amount=document.vat_amount,
        amount_base=document.amount_base,
        exchange_rate=document.exchange_rate,
        rate_date=document.rate_date,
        rate_source=document.rate_source,
        amount_base_final=document.amount_base_final,
        file_name=document.file_name,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        source=document.source,
        email_from=document.email_from,
        email_subject=document.email_subject,
        received_at=document.received_at,
        rebilled_expense_line_id=document.rebilled_expense_line_id,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


class _Handler:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._documents = PurchaseDocumentRepository(bus.session)
        self._service = PurchaseService(self._documents)


# --- Queries ---


class ListPurchaseDocumentsHandler(_Handler):
    async def handle(self, query: ListPurchaseDocuments) -> tuple[PurchaseDocumentDTO, ...]:
        documents = await self._documents.list(
            stage=query.stage, kind=query.kind, limit=query.limit
        )
        return tuple(to_dto(document) for document in documents)


class GetPurchaseDocumentHandler(_Handler):
    async def handle(self, query: GetPurchaseDocument) -> PurchaseDocumentDTO:
        return to_dto(await self._service.get(query.document_id))


class GetPurchaseFilePathHandler(_Handler):
    async def handle(self, query: GetPurchaseFilePath) -> PurchaseFileDTO:
        return await self._service.file_of(query.document_id)


class ListPurchaseStorageKeysHandler(_Handler):
    async def handle(self, query: ListPurchaseStorageKeys) -> frozenset[str]:
        return await self._documents.list_storage_keys()


# --- Commands ---


class AddPurchaseDocumentHandler(_Handler):
    async def handle(self, command: AddPurchaseDocument) -> PurchaseDocumentDTO:
        return to_dto(await self._service.add(command))


class DiscardPurchaseDocumentHandler(_Handler):
    async def handle(self, command: DiscardPurchaseDocument) -> PurchaseDocumentDTO:
        return to_dto(await self._service.discard(command))
