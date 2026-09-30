"""Purchases HTTP API: the company's register of incoming receipts and invoices, accountant only."""

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Path, Query, UploadFile, status
from fastapi.responses import FileResponse

from time_reporting.api.deps import BusDep
from time_reporting.core.config import get_settings
from time_reporting.modules.auth.dependencies import AccountantDep
from time_reporting.modules.purchases.contracts import (
    ALLOWED_PURCHASE_CONTENT_TYPES,
    DEFAULT_LIST_LIMIT,
    AddPurchaseDocument,
    CardReceiptLink,
    DiscardPurchaseDocument,
    GetCardInvoice,
    GetPurchaseDocument,
    GetPurchaseFilePath,
    GetPurchasesSummary,
    LinkCardReceipts,
    ListMonthPurchases,
    ListPurchaseDocuments,
    ListUnlinkedCardReceipts,
    MarkPurchasePaid,
    MarkPurchaseUnpaid,
    PaymentStatus,
    PurchaseDocumentNotFoundError,
    PurchaseDocumentStateError,
    PurchaseFileTooLargeError,
    PurchaseFileTypeNotAllowedError,
    PurchaseKind,
    PurchaseSort,
    PurchaseStage,
    PurchaseValidationError,
    RebillPurchase,
    RegisterPurchaseDocument,
    ReturnPurchaseToInbox,
    SuggestRebillAmount,
    UnlinkCardReceipt,
    UpdateCardReceiptAmount,
    UpdatePurchaseDocument,
)
from time_reporting.modules.purchases.schemas import (
    CardInvoiceResponse,
    CardReceiptAmountRequest,
    LinkCardReceiptsRequest,
    MarkPaidRequest,
    MonthPurchaseResponse,
    PurchaseDetailsRequest,
    PurchaseDocumentPageResponse,
    PurchaseDocumentResponse,
    PurchasesSummaryResponse,
    RebillRequest,
    RebillSuggestionResponse,
    UpdatePurchaseRequest,
)

router = APIRouter(prefix="/purchases", tags=["purchases"])

_NOT_FOUND_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"description": "Purchase document not found"}
}


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)


_CONFLICT_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_409_CONFLICT: {"description": "The document's state doesn't allow this"}
}
_INVALID_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_400_BAD_REQUEST: {"description": "The fields break the rules of the kind"}
}


def _bad_request(exc: PurchaseValidationError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _conflict(exc: PurchaseDocumentStateError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


def _too_large(exc: PurchaseFileTooLargeError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(exc))


def _type_not_allowed(exc: PurchaseFileTypeNotAllowedError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc))


@router.post(
    "/documents",
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_413_CONTENT_TOO_LARGE: {"description": "A file is too large"},
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {"description": "A file type isn't allowed"},
    },
    summary="Upload one or more files into the inbox",
)
async def upload_purchase_documents(
    files: Annotated[list[UploadFile], File()], current_user: AccountantDep, bus: BusDep
) -> list[PurchaseDocumentResponse]:
    # Every file is checked before any is stored, so one bad file in a batch rejects the whole
    # upload instead of leaving the good ones behind.
    max_bytes = get_settings().attachment_max_bytes
    uploads: list[tuple[UploadFile, str, bytes]] = []
    for file in files:
        content_type = file.content_type or "application/octet-stream"
        if content_type not in ALLOWED_PURCHASE_CONTENT_TYPES:
            raise _type_not_allowed(PurchaseFileTypeNotAllowedError(content_type))
        # One byte over the limit is enough to reject, without buffering a huge body.
        content = await file.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise _too_large(PurchaseFileTooLargeError(len(content), max_bytes))
        uploads.append((file, content_type, content))

    created: list[PurchaseDocumentResponse] = []
    for file, content_type, content in uploads:
        try:
            document = await bus.execute(
                AddPurchaseDocument(
                    actor_id=current_user.id,
                    file_name=file.filename or "document",
                    content_type=content_type,
                    content=content,
                )
            )
        except PurchaseFileTooLargeError as exc:
            raise _too_large(exc) from exc
        except PurchaseFileTypeNotAllowedError as exc:
            raise _type_not_allowed(exc) from exc
        created.append(PurchaseDocumentResponse.model_validate(document))
    return created


@router.get("/documents")
async def list_purchase_documents(
    _: AccountantDep,
    bus: BusDep,
    stage: PurchaseStage | None = None,
    kind: PurchaseKind | None = None,
    payment_status: PaymentStatus | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    sort: PurchaseSort = PurchaseSort.NEWEST,
    limit: Annotated[int, Query(ge=1, le=500)] = DEFAULT_LIST_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PurchaseDocumentPageResponse:
    page = await bus.query(
        ListPurchaseDocuments(
            stage=stage,
            kind=kind,
            payment_status=payment_status,
            search=search,
            date_from=date_from,
            date_to=date_to,
            sort=sort,
            limit=limit,
            offset=offset,
        )
    )
    return PurchaseDocumentPageResponse.model_validate(page)


@router.get("/documents/{document_id}", responses=_NOT_FOUND_RESPONSE)
async def get_purchase_document(
    document_id: UUID, _: AccountantDep, bus: BusDep
) -> PurchaseDocumentResponse:
    try:
        document = await bus.query(GetPurchaseDocument(document_id=document_id))
    except PurchaseDocumentNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    return PurchaseDocumentResponse.model_validate(document)


@router.get("/documents/{document_id}/file", responses=_NOT_FOUND_RESPONSE)
async def download_purchase_file(document_id: UUID, _: AccountantDep, bus: BusDep) -> FileResponse:
    try:
        file = await bus.query(GetPurchaseFilePath(document_id=document_id))
    except PurchaseDocumentNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    return FileResponse(file.path, filename=file.file_name, media_type=file.content_type)


@router.post(
    "/documents/{document_id}/discard",
    responses={
        **_NOT_FOUND_RESPONSE,
        status.HTTP_409_CONFLICT: {"description": "Already discarded or already rebilled"},
    },
)
async def discard_purchase_document(
    document_id: UUID, current_user: AccountantDep, bus: BusDep
) -> PurchaseDocumentResponse:
    try:
        document = await bus.execute(
            DiscardPurchaseDocument(document_id=document_id, actor_id=current_user.id)
        )
    except PurchaseDocumentNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    except PurchaseDocumentStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return PurchaseDocumentResponse.model_validate(document)


@router.post(
    "/documents/{document_id}/register",
    responses={**_NOT_FOUND_RESPONSE, **_CONFLICT_RESPONSE, **_INVALID_RESPONSE},
    summary="Classify an inbox document",
)
async def register_purchase_document(
    document_id: UUID, body: PurchaseDetailsRequest, current_user: AccountantDep, bus: BusDep
) -> PurchaseDocumentResponse:
    try:
        document = await bus.execute(
            RegisterPurchaseDocument(
                document_id=document_id, actor_id=current_user.id, details=body.to_details()
            )
        )
    except PurchaseDocumentNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    except PurchaseValidationError as exc:
        raise _bad_request(exc) from exc
    except PurchaseDocumentStateError as exc:
        raise _conflict(exc) from exc
    return PurchaseDocumentResponse.model_validate(document)


@router.put(
    "/documents/{document_id}",
    responses={**_NOT_FOUND_RESPONSE, **_CONFLICT_RESPONSE, **_INVALID_RESPONSE},
    summary="Replace a registered document's fields",
)
async def update_purchase_document(
    document_id: UUID, body: UpdatePurchaseRequest, current_user: AccountantDep, bus: BusDep
) -> PurchaseDocumentResponse:
    try:
        document = await bus.execute(
            UpdatePurchaseDocument(
                document_id=document_id,
                actor_id=current_user.id,
                details=body.to_details(),
                recompute_conversion=body.recompute_conversion,
            )
        )
    except PurchaseDocumentNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    except PurchaseValidationError as exc:
        raise _bad_request(exc) from exc
    except PurchaseDocumentStateError as exc:
        raise _conflict(exc) from exc
    return PurchaseDocumentResponse.model_validate(document)


@router.post(
    "/documents/{document_id}/return-to-inbox",
    responses={**_NOT_FOUND_RESPONSE, **_CONFLICT_RESPONSE},
)
async def return_purchase_to_inbox(
    document_id: UUID, current_user: AccountantDep, bus: BusDep
) -> PurchaseDocumentResponse:
    try:
        document = await bus.execute(
            ReturnPurchaseToInbox(document_id=document_id, actor_id=current_user.id)
        )
    except PurchaseDocumentNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    except PurchaseDocumentStateError as exc:
        raise _conflict(exc) from exc
    return PurchaseDocumentResponse.model_validate(document)


@router.post(
    "/documents/{document_id}/paid",
    responses={**_NOT_FOUND_RESPONSE, **_CONFLICT_RESPONSE},
    summary="Mark an unpaid invoice paid",
)
async def mark_purchase_paid(
    document_id: UUID, body: MarkPaidRequest, current_user: AccountantDep, bus: BusDep
) -> PurchaseDocumentResponse:
    try:
        document = await bus.execute(
            MarkPurchasePaid(
                document_id=document_id,
                actor_id=current_user.id,
                paid_on=body.paid_on,
                payment_method=body.payment_method,
                amount_base=body.amount_base,
            )
        )
    except PurchaseDocumentNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    except PurchaseDocumentStateError as exc:
        raise _conflict(exc) from exc
    return PurchaseDocumentResponse.model_validate(document)


@router.post(
    "/documents/{document_id}/unpaid",
    responses={**_NOT_FOUND_RESPONSE, **_CONFLICT_RESPONSE},
    summary="Undo a payment",
)
async def mark_purchase_unpaid(
    document_id: UUID, current_user: AccountantDep, bus: BusDep
) -> PurchaseDocumentResponse:
    try:
        document = await bus.execute(
            MarkPurchaseUnpaid(document_id=document_id, actor_id=current_user.id)
        )
    except PurchaseDocumentNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    except PurchaseDocumentStateError as exc:
        raise _conflict(exc) from exc
    return PurchaseDocumentResponse.model_validate(document)


@router.get("/card-receipts/unlinked", summary="Card receipts not yet linked to a card invoice")
async def list_unlinked_card_receipts(
    _: AccountantDep, bus: BusDep, date_from: date | None = None, date_to: date | None = None
) -> list[PurchaseDocumentResponse]:
    receipts = await bus.query(ListUnlinkedCardReceipts(date_from=date_from, date_to=date_to))
    return [PurchaseDocumentResponse.model_validate(receipt) for receipt in receipts]


@router.get(
    "/documents/{document_id}/card-invoice",
    responses={**_NOT_FOUND_RESPONSE, **_CONFLICT_RESPONSE},
    summary="A card invoice with its linked receipts, their sum and the difference",
)
async def get_card_invoice(document_id: UUID, _: AccountantDep, bus: BusDep) -> CardInvoiceResponse:
    try:
        card_invoice = await bus.query(GetCardInvoice(card_invoice_id=document_id))
    except PurchaseDocumentNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    except PurchaseDocumentStateError as exc:
        raise _conflict(exc) from exc
    return CardInvoiceResponse.model_validate(card_invoice)


@router.post(
    "/documents/{document_id}/card-receipts",
    responses={**_NOT_FOUND_RESPONSE, **_CONFLICT_RESPONSE, **_INVALID_RESPONSE},
    summary="Link card receipts to a card invoice, with their amounts from its lines",
)
async def link_card_receipts(
    document_id: UUID, body: LinkCardReceiptsRequest, current_user: AccountantDep, bus: BusDep
) -> CardInvoiceResponse:
    try:
        card_invoice = await bus.execute(
            LinkCardReceipts(
                card_invoice_id=document_id,
                actor_id=current_user.id,
                links=tuple(
                    CardReceiptLink(receipt_id=link.receipt_id, amount_base=link.amount_base)
                    for link in body.links
                ),
            )
        )
    except PurchaseDocumentNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    except PurchaseValidationError as exc:
        raise _bad_request(exc) from exc
    except PurchaseDocumentStateError as exc:
        raise _conflict(exc) from exc
    return CardInvoiceResponse.model_validate(card_invoice)


@router.put(
    "/documents/{document_id}/card-amount",
    responses={**_NOT_FOUND_RESPONSE, **_CONFLICT_RESPONSE, **_INVALID_RESPONSE},
    summary="Change a linked card receipt's amount from the card invoice",
)
async def update_card_receipt_amount(
    document_id: UUID, body: CardReceiptAmountRequest, current_user: AccountantDep, bus: BusDep
) -> PurchaseDocumentResponse:
    try:
        receipt = await bus.execute(
            UpdateCardReceiptAmount(
                receipt_id=document_id, actor_id=current_user.id, amount_base=body.amount_base
            )
        )
    except PurchaseDocumentNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    except PurchaseValidationError as exc:
        raise _bad_request(exc) from exc
    except PurchaseDocumentStateError as exc:
        raise _conflict(exc) from exc
    return PurchaseDocumentResponse.model_validate(receipt)


@router.post(
    "/documents/{document_id}/unlink-card",
    responses={**_NOT_FOUND_RESPONSE, **_CONFLICT_RESPONSE},
    summary="Detach a card receipt from its card invoice",
)
async def unlink_card_receipt(
    document_id: UUID, current_user: AccountantDep, bus: BusDep
) -> PurchaseDocumentResponse:
    try:
        receipt = await bus.execute(
            UnlinkCardReceipt(receipt_id=document_id, actor_id=current_user.id)
        )
    except PurchaseDocumentNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    except PurchaseDocumentStateError as exc:
        raise _conflict(exc) from exc
    return PurchaseDocumentResponse.model_validate(receipt)


@router.get("/summary", summary="Inbox and unpaid figures for the dashboard")
async def get_purchases_summary(
    _: AccountantDep, bus: BusDep, today: date | None = None
) -> PurchasesSummaryResponse:
    summary = await bus.query(GetPurchasesSummary(today=today or date.today()))
    return PurchasesSummaryResponse.model_validate(summary)


@router.get(
    "/months/{year}/{month}",
    summary="Registered documents dated in a month, card receipts under their card invoice",
)
async def list_month_purchases(
    year: Annotated[int, Path(ge=2000, le=2100)],
    month: Annotated[int, Path(ge=1, le=12)],
    _: AccountantDep,
    bus: BusDep,
) -> list[MonthPurchaseResponse]:
    entries = await bus.query(ListMonthPurchases(year=year, month=month))
    return [MonthPurchaseResponse.model_validate(entry) for entry in entries]


@router.get(
    "/documents/{document_id}/rebill-suggestion",
    responses={**_NOT_FOUND_RESPONSE, **_CONFLICT_RESPONSE, **_INVALID_RESPONSE},
    summary="Prefill for rebilling a document to a project",
)
async def get_rebill_suggestion(
    document_id: UUID, project_id: UUID, _: AccountantDep, bus: BusDep
) -> RebillSuggestionResponse:
    try:
        suggestion = await bus.execute(
            SuggestRebillAmount(document_id=document_id, project_id=project_id)
        )
    except PurchaseDocumentNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    except PurchaseValidationError as exc:
        raise _bad_request(exc) from exc
    except PurchaseDocumentStateError as exc:
        raise _conflict(exc) from exc
    return RebillSuggestionResponse.model_validate(suggestion)


@router.post(
    "/documents/{document_id}/rebill",
    responses={**_NOT_FOUND_RESPONSE, **_CONFLICT_RESPONSE, **_INVALID_RESPONSE},
    summary="File a document to a project's expense report (your own, for the month)",
)
async def rebill_purchase(
    document_id: UUID, body: RebillRequest, current_user: AccountantDep, bus: BusDep
) -> PurchaseDocumentResponse:
    try:
        document = await bus.execute(
            RebillPurchase(document_id=document_id, actor_id=current_user.id, **body.model_dump())
        )
    except PurchaseDocumentNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    except PurchaseValidationError as exc:
        raise _bad_request(exc) from exc
    except PurchaseDocumentStateError as exc:
        raise _conflict(exc) from exc
    return PurchaseDocumentResponse.model_validate(document)
