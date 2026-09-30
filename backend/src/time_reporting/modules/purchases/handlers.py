"""Command and query handlers of the purchases module (registered in ``purchases.module``).

Handlers translate between bus messages and the service/repository and never return ORM entities.
"""

import calendar
from datetime import date
from decimal import Decimal
from uuid import UUID

from time_reporting.core.cqrs import Bus
from time_reporting.modules.company.contracts import GetCompanySettings
from time_reporting.modules.purchases.contracts import (
    AddPurchaseDocument,
    CardInvoiceDTO,
    DiscardPurchaseDocument,
    GetCardInvoice,
    GetPurchaseDocument,
    GetPurchaseFilePath,
    GetPurchasesSummary,
    LinkCardReceipts,
    ListMonthPurchases,
    ListPurchaseDocuments,
    ListPurchaseStorageKeys,
    ListUnlinkedCardReceipts,
    MarkPurchasePaid,
    MarkPurchaseUnpaid,
    MonthPurchaseDTO,
    PurchaseDocumentDTO,
    PurchaseFileDTO,
    PurchaseKind,
    PurchasesSummaryDTO,
    RebillPurchase,
    RebillSuggestionDTO,
    RegisterPurchaseDocument,
    ReturnPurchaseToInbox,
    SuggestRebillAmount,
    UnlinkCardReceipt,
    UpdateCardReceiptAmount,
    UpdatePurchaseDocument,
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


def card_invoice_dto(invoice: PurchaseDocument, receipts: list[PurchaseDocument]) -> CardInvoiceDTO:
    total = sum((r.amount_base or Decimal(0) for r in receipts), Decimal(0))
    return CardInvoiceDTO(
        invoice=to_dto(invoice),
        receipts=tuple(to_dto(receipt) for receipt in receipts),
        receipts_total_base=total,
        difference_base=None if invoice.amount_base is None else invoice.amount_base - total,
    )


class _Handler:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._documents = PurchaseDocumentRepository(bus.session)
        self._service = PurchaseService(bus, self._documents)


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


class RegisterPurchaseDocumentHandler(_Handler):
    async def handle(self, command: RegisterPurchaseDocument) -> PurchaseDocumentDTO:
        return to_dto(await self._service.register(command))


class UpdatePurchaseDocumentHandler(_Handler):
    async def handle(self, command: UpdatePurchaseDocument) -> PurchaseDocumentDTO:
        return to_dto(await self._service.update(command))


class ReturnPurchaseToInboxHandler(_Handler):
    async def handle(self, command: ReturnPurchaseToInbox) -> PurchaseDocumentDTO:
        return to_dto(await self._service.return_to_inbox(command))


class MarkPurchasePaidHandler(_Handler):
    async def handle(self, command: MarkPurchasePaid) -> PurchaseDocumentDTO:
        return to_dto(await self._service.mark_paid(command))


class MarkPurchaseUnpaidHandler(_Handler):
    async def handle(self, command: MarkPurchaseUnpaid) -> PurchaseDocumentDTO:
        return to_dto(await self._service.mark_unpaid(command))


class GetCardInvoiceHandler(_Handler):
    async def handle(self, query: GetCardInvoice) -> CardInvoiceDTO:
        return card_invoice_dto(*await self._service.get_card_invoice(query.card_invoice_id))


class ListUnlinkedCardReceiptsHandler(_Handler):
    async def handle(self, query: ListUnlinkedCardReceipts) -> tuple[PurchaseDocumentDTO, ...]:
        receipts = await self._documents.list_unlinked_card_receipts(query.date_from, query.date_to)
        return tuple(to_dto(receipt) for receipt in receipts)


class LinkCardReceiptsHandler(_Handler):
    async def handle(self, command: LinkCardReceipts) -> CardInvoiceDTO:
        return card_invoice_dto(*await self._service.link_card_receipts(command))


class UnlinkCardReceiptHandler(_Handler):
    async def handle(self, command: UnlinkCardReceipt) -> PurchaseDocumentDTO:
        return to_dto(await self._service.unlink_card_receipt(command))


class UpdateCardReceiptAmountHandler(_Handler):
    async def handle(self, command: UpdateCardReceiptAmount) -> PurchaseDocumentDTO:
        return to_dto(await self._service.update_card_receipt_amount(command))


class GetPurchasesSummaryHandler(_Handler):
    async def handle(self, query: GetPurchasesSummary) -> PurchasesSummaryDTO:
        figures = await self._documents.unpaid_figures(query.today)
        company = await self._bus.query(GetCompanySettings())
        return PurchasesSummaryDTO(
            base_currency=company.base_currency,
            inbox_count=await self._documents.count_inbox(),
            unpaid_count=figures.unpaid_count,
            unpaid_total_base=figures.total_base,
            unpaid_provisional=figures.provisional_count > 0,
            unpaid_unconverted_count=figures.unconverted_count,
            overdue_count=figures.overdue_count,
            due_soon_count=figures.due_soon_count,
        )


class ListMonthPurchasesHandler(_Handler):
    async def handle(self, query: ListMonthPurchases) -> tuple[MonthPurchaseDTO, ...]:
        last_day = calendar.monthrange(query.year, query.month)[1]
        documents = await self._documents.list_registered_in_range(
            date(query.year, query.month, 1), date(query.year, query.month, last_day)
        )
        receipts = await self._documents.list_receipts_of(
            [d.id for d in documents if d.kind is PurchaseKind.CARD_INVOICE]
        )
        by_invoice: dict[UUID, list[PurchaseDocumentDTO]] = {}
        for receipt in receipts:
            assert receipt.card_invoice_id is not None
            by_invoice.setdefault(receipt.card_invoice_id, []).append(to_dto(receipt))
        return tuple(
            MonthPurchaseDTO(
                document=to_dto(document),
                card_receipts=tuple(by_invoice.get(document.id, ())),
            )
            for document in documents
        )


class SuggestRebillAmountHandler(_Handler):
    async def handle(self, command: SuggestRebillAmount) -> RebillSuggestionDTO:
        return await self._service.suggest_rebill(command)


class RebillPurchaseHandler(_Handler):
    async def handle(self, command: RebillPurchase) -> PurchaseDocumentDTO:
        return to_dto(await self._service.rebill(command))
