"""Persistence of ``PurchaseDocument`` entities. Flushes but never commits — the bus owns
transactions."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from time_reporting.modules.purchases.contracts import PurchaseKind, PurchaseStage
from time_reporting.modules.purchases.models import PurchaseDocument

_EXTERNAL_REF_CONSTRAINT = "uq_purchase_documents_external_ref"


class ExternalRefTakenError(Exception):
    """Another transaction stored a document with the same ``external_ref`` first."""


class PurchaseDocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, document_id: UUID) -> PurchaseDocument | None:
        return await self._session.get(PurchaseDocument, document_id)

    async def get_by_external_ref(self, external_ref: str) -> PurchaseDocument | None:
        result = await self._session.scalars(
            select(PurchaseDocument).where(PurchaseDocument.external_ref == external_ref)
        )
        return result.one_or_none()

    async def list(
        self, *, stage: PurchaseStage | None, kind: PurchaseKind | None, limit: int
    ) -> Sequence[PurchaseDocument]:
        statement = select(PurchaseDocument).order_by(
            PurchaseDocument.created_at.desc(), PurchaseDocument.id
        )
        if stage is not None:
            statement = statement.where(PurchaseDocument.stage == stage)
        if kind is not None:
            statement = statement.where(PurchaseDocument.kind == kind)
        result = await self._session.scalars(statement.limit(limit))
        return result.all()

    async def list_storage_keys(self) -> frozenset[str]:
        result = await self._session.scalars(select(PurchaseDocument.storage_key))
        return frozenset(result.all())

    async def save(self, document: PurchaseDocument) -> None:
        """Add ``document`` (if new) and flush. A duplicate ``external_ref`` raises
        ``ExternalRefTakenError`` and leaves the session usable (the flush runs in a savepoint)."""
        self._session.add(document)
        try:
            async with self._session.begin_nested():
                await self._session.flush()
        except IntegrityError as exc:
            if _EXTERNAL_REF_CONSTRAINT in str(exc.orig):
                self._session.expunge(document)
                raise ExternalRefTakenError from exc
            raise

    async def count_linked_receipts(self, card_invoice_id: UUID) -> int:
        result = await self._session.scalar(
            select(func.count())
            .select_from(PurchaseDocument)
            .where(PurchaseDocument.card_invoice_id == card_invoice_id)
        )
        return result or 0
