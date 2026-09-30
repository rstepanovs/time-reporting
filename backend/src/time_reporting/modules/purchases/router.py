"""Purchases HTTP API: the company's register of incoming receipts and invoices, accountant only."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse

from time_reporting.api.deps import BusDep
from time_reporting.core.config import get_settings
from time_reporting.modules.auth.dependencies import AccountantDep
from time_reporting.modules.purchases.contracts import (
    ALLOWED_PURCHASE_CONTENT_TYPES,
    DEFAULT_LIST_LIMIT,
    AddPurchaseDocument,
    DiscardPurchaseDocument,
    GetPurchaseDocument,
    GetPurchaseFilePath,
    ListPurchaseDocuments,
    PurchaseDocumentNotFoundError,
    PurchaseDocumentStateError,
    PurchaseFileTooLargeError,
    PurchaseFileTypeNotAllowedError,
    PurchaseKind,
    PurchaseStage,
)
from time_reporting.modules.purchases.schemas import PurchaseDocumentResponse

router = APIRouter(prefix="/purchases", tags=["purchases"])

_NOT_FOUND_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"description": "Purchase document not found"}
}


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)


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
    limit: Annotated[int, Query(ge=1, le=1000)] = DEFAULT_LIST_LIMIT,
) -> list[PurchaseDocumentResponse]:
    documents = await bus.query(ListPurchaseDocuments(stage=stage, kind=kind, limit=limit))
    return [PurchaseDocumentResponse.model_validate(document) for document in documents]


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
