"""Purchase-document use cases: storing a file in the inbox, discarding."""

import hashlib
from uuid import UUID

from time_reporting.core.config import get_settings
from time_reporting.modules.purchases.contracts import (
    AddPurchaseDocument,
    DiscardPurchaseDocument,
    PurchaseDocumentNotFoundError,
    PurchaseDocumentStateError,
    PurchaseFileDTO,
    PurchaseStage,
)
from time_reporting.modules.purchases.models import PurchaseDocument
from time_reporting.modules.purchases.repository import (
    ExternalRefTakenError,
    PurchaseDocumentRepository,
)
from time_reporting.modules.purchases.storage import PurchaseFileStorage


class PurchaseService:
    def __init__(self, documents: PurchaseDocumentRepository) -> None:
        self._documents = documents
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
        return document
