"""Purchase-document use cases: storing a file in the inbox, discarding."""

import hashlib
from uuid import UUID

from time_reporting.core.config import get_settings
from time_reporting.core.cqrs import Bus
from time_reporting.modules.audit.contracts import AuditAction, RecordAuditEvent
from time_reporting.modules.purchases.contracts import (
    AddPurchaseDocument,
    DiscardPurchaseDocument,
    MarkPurchasePaid,
    MarkPurchaseUnpaid,
    PaymentMethod,
    PaymentStatus,
    PurchaseDetails,
    PurchaseDocumentNotFoundError,
    PurchaseDocumentStateError,
    PurchaseFileDTO,
    PurchaseKind,
    PurchaseStage,
    RegisterPurchaseDocument,
    ReturnPurchaseToInbox,
    UpdatePurchaseDocument,
)
from time_reporting.modules.purchases.conversion import Converter, is_converted_by_hand
from time_reporting.modules.purchases.models import PurchaseDocument
from time_reporting.modules.purchases.repository import (
    ExternalRefTakenError,
    PurchaseDocumentRepository,
)
from time_reporting.modules.purchases.rules import normalize
from time_reporting.modules.purchases.storage import PurchaseFileStorage

_ENTITY_TYPE = "purchase_document"

# Kinds that have a payment state a user can flip with Paid/Unpaid.
_PAYABLE_KINDS = frozenset({PurchaseKind.INVOICE, PurchaseKind.CARD_INVOICE})


class PurchaseService:
    def __init__(self, bus: Bus, documents: PurchaseDocumentRepository) -> None:
        self._bus = bus
        self._documents = documents
        self._converter = Converter(bus)
        self._storage = PurchaseFileStorage(get_settings())

    async def get(self, document_id: UUID) -> PurchaseDocument:
        document = await self._documents.get_by_id(document_id)
        if document is None:
            raise PurchaseDocumentNotFoundError(document_id)
        return document

    async def file_of(self, document_id: UUID) -> PurchaseFileDTO:
        document = await self.get(document_id)
        path = self._storage.path_for(document.storage_key)
        if path is None:
            # The row outlived its file (e.g. a restore without the attachment archive).
            raise PurchaseDocumentNotFoundError(document_id)
        return PurchaseFileDTO(
            path=path, file_name=document.file_name, content_type=document.content_type
        )

    async def add(self, command: AddPurchaseDocument) -> PurchaseDocument:
        if command.external_ref is not None:
            existing = await self._documents.get_by_external_ref(command.external_ref)
            if existing is not None:
                return existing

        # Checked before hashing or touching the filesystem, so a rejected file costs nothing.
        self._storage.ensure_allowed(
            content_type=command.content_type, size_bytes=len(command.content)
        )
        storage_key = self._storage.save(content=command.content, content_type=command.content_type)
        document = PurchaseDocument(
            stage=PurchaseStage.INBOX,
            file_name=command.file_name,
            content_type=command.content_type,
            size_bytes=len(command.content),
            sha256=hashlib.sha256(command.content).hexdigest(),
            storage_key=storage_key,
            source=command.source,
            email_from=command.email_from,
            email_subject=command.email_subject,
            received_at=command.received_at,
            external_ref=command.external_ref,
            created_by_id=command.actor_id,
        )
        try:
            await self._documents.save(document)
        except ExternalRefTakenError:
            # A concurrent import stored it between the check above and the insert.
            self._storage.delete(storage_key)
            assert command.external_ref is not None
            winner = await self._documents.get_by_external_ref(command.external_ref)
            assert winner is not None
            return winner
        return document

    async def discard(self, command: DiscardPurchaseDocument) -> PurchaseDocument:
        document = await self.get(command.document_id)
        if document.stage is PurchaseStage.DISCARDED:
            raise PurchaseDocumentStateError("The document is already discarded")
        if document.rebilled_expense_line_id is not None:
            raise PurchaseDocumentStateError("The document has been rebilled to a project")
        document.stage = PurchaseStage.DISCARDED
        await self._documents.save(document)
        await self._audit(command.actor_id, AuditAction.PURCHASE_DISCARDED, document, "Discarded")
        return document

    async def register(self, command: RegisterPurchaseDocument) -> PurchaseDocument:
        document = await self.get(command.document_id)
        if document.stage is not PurchaseStage.INBOX:
            raise PurchaseDocumentStateError("Only an inbox document can be registered")
        details = normalize(command.details)
        self._assign(document, details)
        document.stage = PurchaseStage.REGISTERED
        document.registered_by_id = command.actor_id
        await self._converter.apply(
            document, manual_amount_base=details.amount_base, manual_rate=details.exchange_rate
        )
        await self._documents.save(document)
        await self._audit(command.actor_id, AuditAction.PURCHASE_REGISTERED, document, "Registered")
        return document

    async def update(self, command: UpdatePurchaseDocument) -> PurchaseDocument:
        document = await self._get_registered(command.document_id)
        self._ensure_not_rebilled(document)
        details = normalize(command.details)
        if document.card_invoice_id is not None and (
            details.payment_method is not PaymentMethod.CARD or details.kind is not document.kind
        ):
            raise PurchaseDocumentStateError(
                "A receipt linked to a card invoice stays a card receipt; unlink it first"
            )
        if (
            document.kind is PurchaseKind.CARD_INVOICE
            and details.kind is not document.kind
            and await self._documents.count_linked_receipts(document.id)
        ):
            raise PurchaseDocumentStateError("Unlink the card invoice's receipts first")

        amount_changed = (details.amount, details.currency) != (document.amount, document.currency)
        self._assign(document, details)
        await self._converter.apply(
            document,
            manual_amount_base=details.amount_base,
            manual_rate=details.exchange_rate,
            recompute=command.recompute_conversion or amount_changed,
        )
        await self._documents.save(document)
        return document

    async def return_to_inbox(self, command: ReturnPurchaseToInbox) -> PurchaseDocument:
        document = await self._get_registered(command.document_id)
        self._ensure_not_rebilled(document)
        if document.kind is PurchaseKind.CARD_INVOICE and (
            await self._documents.count_linked_receipts(document.id)
        ):
            raise PurchaseDocumentStateError("Unlink the card invoice's receipts first")
        self._assign(document, None)
        document.stage = PurchaseStage.INBOX
        document.registered_by_id = None
        document.card_invoice_id = None
        await self._converter.apply(document)
        await self._documents.save(document)
        return document

    async def mark_paid(self, command: MarkPurchasePaid) -> PurchaseDocument:
        document = await self._get_payable(command.document_id)
        if document.payment_status is not PaymentStatus.UNPAID:
            raise PurchaseDocumentStateError("The document is already paid")
        if (
            document.kind is PurchaseKind.CARD_INVOICE
            and command.payment_method is PaymentMethod.CARD
        ):
            raise PurchaseDocumentStateError("A card invoice can't be paid by card")
        document.payment_status = PaymentStatus.PAID
        document.paid_on = command.paid_on
        document.payment_method = command.payment_method
        await self._converter.apply(
            document,
            manual_amount_base=command.amount_base,
            recompute=not is_converted_by_hand(document),
        )
        await self._documents.save(document)
        await self._audit(
            command.actor_id,
            AuditAction.PURCHASE_PAID,
            document,
            f"Paid on {command.paid_on} ({command.payment_method.value})",
        )
        return document

    async def mark_unpaid(self, command: MarkPurchaseUnpaid) -> PurchaseDocument:
        document = await self._get_payable(command.document_id)
        if document.payment_status is not PaymentStatus.PAID:
            raise PurchaseDocumentStateError("The document is not paid")
        document.payment_status = PaymentStatus.UNPAID
        document.paid_on = None
        document.payment_method = None
        await self._converter.apply(document, recompute=not is_converted_by_hand(document))
        await self._documents.save(document)
        await self._audit(command.actor_id, AuditAction.PURCHASE_UNPAID, document, "Marked unpaid")
        return document

    # --- helpers ---

    async def _get_registered(self, document_id: UUID) -> PurchaseDocument:
        document = await self.get(document_id)
        if document.stage is not PurchaseStage.REGISTERED:
            raise PurchaseDocumentStateError("The document isn't registered")
        return document

    async def _get_payable(self, document_id: UUID) -> PurchaseDocument:
        document = await self._get_registered(document_id)
        if document.kind not in _PAYABLE_KINDS:
            raise PurchaseDocumentStateError("Only an invoice or a card invoice can be paid")
        return document

    @staticmethod
    def _ensure_not_rebilled(document: PurchaseDocument) -> None:
        if document.rebilled_expense_line_id is not None:
            raise PurchaseDocumentStateError("The document has been rebilled to a project")

    @staticmethod
    def _assign(document: PurchaseDocument, details: PurchaseDetails | None) -> None:
        """Copy the user-entered fields onto ``document``; ``None`` clears them all."""
        document.kind = None if details is None else details.kind
        for name in (
            "vendor",
            "document_no",
            "description",
            "document_date",
            "due_date",
            "payment_status",
            "paid_on",
            "payment_method",
            "amount",
            "currency",
            "vat_amount",
        ):
            setattr(document, name, None if details is None else getattr(details, name))

    async def _audit(
        self, actor_id: UUID, action: AuditAction, document: PurchaseDocument, verb: str
    ) -> None:
        label = document.vendor or document.file_name
        kind = document.kind.value.replace("_", " ") if document.kind else "document"
        await self._bus.execute(
            RecordAuditEvent(
                actor_id=actor_id,
                action=action,
                entity_type=_ENTITY_TYPE,
                entity_id=str(document.id),
                summary=f"{verb} {kind} {document.document_no or ''} ({label})".replace("  ", " "),
                details={"kind": document.kind.value if document.kind else None},
            )
        )
