"""Purchase-document use cases: storing a file in the inbox, discarding."""

import hashlib
from decimal import Decimal
from uuid import UUID

from time_reporting.core.config import get_settings
from time_reporting.core.cqrs import Bus
from time_reporting.modules.audit.contracts import AuditAction, RecordAuditEvent
from time_reporting.modules.company.contracts import GetCompanySettings
from time_reporting.modules.currency.contracts import (
    ExchangeRateUnavailableError,
    GetExchangeRate,
)
from time_reporting.modules.expenses.contracts import (
    AddExpenseLineWithAttachment,
    ExpenseBillingItemNotFoundError,
    ExpenseDateOutsidePeriodError,
    ExpenseLineChange,
    ExpenseProjectClosedError,
    ExpenseReportLockedError,
    ExpenseReportNotEditableError,
)
from time_reporting.modules.projects.contracts import GetProjectById
from time_reporting.modules.purchases.contracts import (
    AddPurchaseDocument,
    DiscardPurchaseDocument,
    LinkCardReceipts,
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
    PurchaseValidationError,
    RateSource,
    RebillPurchase,
    RebillSuggestionDTO,
    RegisterPurchaseDocument,
    ReturnPurchaseToInbox,
    SuggestRebillAmount,
    UnlinkCardReceipt,
    UpdateCardReceiptAmount,
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
        if document.kind is PurchaseKind.CARD_INVOICE and (
            await self._documents.count_linked_receipts(document.id)
        ):
            raise PurchaseDocumentStateError("Unlink the card invoice's receipts first")
        if document.card_invoice_id is not None:
            self._detach(document)
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

    # --- rebilling ---

    async def suggest_rebill(self, command: SuggestRebillAmount) -> RebillSuggestionDTO:
        document = await self._get_rebillable(command.document_id)
        project = await self._bus.query(GetProjectById(project_id=command.project_id))
        if project is None:
            raise PurchaseValidationError("Unknown project")
        currency = project.customer.currency
        return RebillSuggestionDTO(
            amount=await self._amount_in(document, currency),
            currency=currency,
            expense_date=document.document_date,
            description=" — ".join(filter(None, (document.vendor, document.description))),
        )

    async def rebill(self, command: RebillPurchase) -> PurchaseDocument:
        document = await self._get_rebillable(command.document_id)
        project = await self._bus.query(GetProjectById(project_id=command.project_id))
        if project is None:
            raise PurchaseValidationError("Unknown project")
        amount = command.amount
        if amount is None:
            amount = await self._amount_in(document, project.customer.currency)
        if amount is None or amount <= Decimal(0):
            raise PurchaseValidationError(
                f"Give the amount in {project.customer.currency}: it can't be derived"
            )
        path = self._storage.path_for(document.storage_key)
        if path is None:
            raise PurchaseDocumentNotFoundError(document.id)
        assert document.document_date is not None

        try:
            rebilled = await self._bus.execute(
                AddExpenseLineWithAttachment(
                    project_id=command.project_id,
                    year=command.year,
                    month=command.month,
                    actor_id=command.actor_id,
                    line=ExpenseLineChange(
                        line_id=None,
                        billing_item_id=command.billing_item_id,
                        expense_date=command.expense_date or document.document_date,
                        amount=amount,
                        description=command.description,
                        vendor=document.vendor,
                        document_no=document.document_no,
                    ),
                    file_name=document.file_name,
                    content_type=document.content_type,
                    content=path.read_bytes(),
                )
            )
        except (
            ExpenseProjectClosedError,
            ExpenseBillingItemNotFoundError,
            ExpenseDateOutsidePeriodError,
        ) as exc:
            raise PurchaseValidationError(str(exc)) from exc
        except (ExpenseReportNotEditableError, ExpenseReportLockedError) as exc:
            raise PurchaseDocumentStateError(str(exc)) from exc

        document.rebilled_expense_line_id = rebilled.line_id
        document.rebilled_expense_attachment_id = rebilled.attachment_id
        await self._documents.save(document)
        await self._bus.execute(
            RecordAuditEvent(
                actor_id=command.actor_id,
                action=AuditAction.PURCHASE_REBILLED,
                entity_type=_ENTITY_TYPE,
                entity_id=str(document.id),
                summary=f"Rebilled {document.vendor or document.file_name} to {project.name}",
                details={
                    "project_id": str(project.id),
                    "expense_report_id": str(rebilled.report_id),
                    "amount": str(amount),
                    "currency": project.customer.currency,
                },
            )
        )
        return document

    async def _get_rebillable(self, document_id: UUID) -> PurchaseDocument:
        document = await self._get_registered(document_id)
        if document.kind not in (PurchaseKind.RECEIPT, PurchaseKind.INVOICE):
            raise PurchaseDocumentStateError("Only a receipt or an invoice can be rebilled")
        self._ensure_not_rebilled(document)
        return document

    async def _amount_in(self, document: PurchaseDocument, currency: str) -> Decimal | None:
        """``document``'s amount in ``currency``, or ``None`` when it can't be derived."""
        if document.amount is None:
            return None
        if document.currency == currency:
            return document.amount
        if document.amount_base is None:
            return None
        base_currency = (await self._bus.query(GetCompanySettings())).base_currency
        if currency == base_currency:
            return document.amount_base
        rate_on = document.paid_on or document.document_date
        if rate_on is None:
            return None
        try:
            rate = await self._bus.execute(GetExchangeRate(currency=currency, on_date=rate_on))
        except ExchangeRateUnavailableError:
            return None
        return (document.amount_base / rate.rate).quantize(Decimal("0.01"))

    # --- card invoices ---

    async def get_card_invoice(
        self, card_invoice_id: UUID
    ) -> tuple[PurchaseDocument, list[PurchaseDocument]]:
        invoice = await self._get_card_invoice(card_invoice_id)
        return invoice, list(await self._documents.list_linked_receipts(card_invoice_id))

    async def link_card_receipts(
        self, command: LinkCardReceipts
    ) -> tuple[PurchaseDocument, list[PurchaseDocument]]:
        invoice = await self._get_card_invoice(command.card_invoice_id)
        ids = [link.receipt_id for link in command.links]
        if len(set(ids)) != len(ids):
            raise PurchaseValidationError("A receipt can be linked only once")
        if any(link.amount_base <= Decimal(0) for link in command.links):
            raise PurchaseValidationError("Every amount must be positive")
        receipts = [await self.get(receipt_id) for receipt_id in ids]
        for receipt in receipts:
            if not _is_card_receipt(receipt):
                raise PurchaseDocumentStateError(
                    f"{receipt.file_name} isn't a registered card-paid receipt"
                )
            if receipt.card_invoice_id is not None:
                raise PurchaseDocumentStateError(
                    f"{receipt.file_name} is already linked to a card invoice"
                )
        for receipt, link in zip(receipts, command.links, strict=True):
            receipt.card_invoice_id = invoice.id
            self._set_card_amount(receipt, link.amount_base)
            await self._documents.save(receipt)
        return await self.get_card_invoice(invoice.id)

    async def unlink_card_receipt(self, command: UnlinkCardReceipt) -> PurchaseDocument:
        receipt = await self.get(command.receipt_id)
        if receipt.card_invoice_id is None:
            raise PurchaseDocumentStateError("The receipt isn't linked to a card invoice")
        self._detach(receipt)
        await self._documents.save(receipt)
        return receipt

    async def update_card_receipt_amount(
        self, command: UpdateCardReceiptAmount
    ) -> PurchaseDocument:
        receipt = await self.get(command.receipt_id)
        if receipt.card_invoice_id is None:
            raise PurchaseDocumentStateError("The receipt isn't linked to a card invoice")
        if command.amount_base <= Decimal(0):
            raise PurchaseValidationError("The amount must be positive")
        self._set_card_amount(receipt, command.amount_base)
        await self._documents.save(receipt)
        return receipt

    async def _get_card_invoice(self, card_invoice_id: UUID) -> PurchaseDocument:
        invoice = await self.get(card_invoice_id)
        if invoice.stage is not PurchaseStage.REGISTERED or invoice.kind is not (
            PurchaseKind.CARD_INVOICE
        ):
            raise PurchaseDocumentStateError("The document isn't a registered card invoice")
        return invoice

    @staticmethod
    def _set_card_amount(receipt: PurchaseDocument, amount_base: Decimal) -> None:
        """The amount typed from the card invoice's line: final, and never recomputed."""
        assert receipt.amount is not None
        receipt.amount_base = amount_base.quantize(Decimal("0.01"))
        receipt.exchange_rate = (amount_base / receipt.amount).quantize(Decimal("0.00000001"))
        receipt.rate_date = None
        receipt.rate_source = RateSource.CARD_INVOICE
        receipt.amount_base_final = True

    @staticmethod
    def _detach(receipt: PurchaseDocument) -> None:
        """Unlink from the card invoice and forget the amount it supplied."""
        receipt.card_invoice_id = None
        receipt.amount_base = None
        receipt.exchange_rate = None
        receipt.rate_date = None
        receipt.rate_source = None
        receipt.amount_base_final = False

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


def _is_card_receipt(document: PurchaseDocument) -> bool:
    return (
        document.stage is PurchaseStage.REGISTERED
        and document.kind in (PurchaseKind.RECEIPT, PurchaseKind.INVOICE)
        and document.payment_method is PaymentMethod.CARD
        and document.amount is not None
    )
