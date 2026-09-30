"""Persistence of ``PurchaseDocument`` entities. Flushes but never commits — the bus owns
transactions."""

from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, NamedTuple
from uuid import UUID

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from time_reporting.db.queries import escape_like
from time_reporting.modules.purchases.contracts import (
    DUE_SOON_DAYS,
    PaymentMethod,
    PaymentStatus,
    PurchaseKind,
    PurchaseSort,
    PurchaseStage,
)
from time_reporting.modules.purchases.models import PurchaseDocument

_EXTERNAL_REF_CONSTRAINT = "uq_purchase_documents_external_ref"


class UnpaidFigures(NamedTuple):
    unpaid_count: int
    total_base: Decimal
    provisional_count: int
    unconverted_count: int
    overdue_count: int
    due_soon_count: int


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

    async def list_page(
        self,
        *,
        stage: PurchaseStage | None,
        kind: PurchaseKind | None,
        payment_status: PaymentStatus | None,
        search: str | None,
        date_from: date | None,
        date_to: date | None,
        sort: PurchaseSort,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[PurchaseDocument], int]:
        conditions: list[ColumnElement[bool]] = []
        if stage is not None:
            conditions.append(PurchaseDocument.stage == stage)
        if kind is not None:
            conditions.append(PurchaseDocument.kind == kind)
        if payment_status is not None:
            conditions.append(PurchaseDocument.payment_status == payment_status)
        if date_from is not None:
            conditions.append(PurchaseDocument.document_date >= date_from)
        if date_to is not None:
            conditions.append(PurchaseDocument.document_date <= date_to)
        if search:
            pattern = f"%{escape_like(search)}%"
            conditions.append(
                or_(
                    PurchaseDocument.vendor.ilike(pattern, escape="\\"),
                    PurchaseDocument.document_no.ilike(pattern, escape="\\"),
                    PurchaseDocument.description.ilike(pattern, escape="\\"),
                )
            )

        order: tuple[Any, ...]
        match sort:
            case PurchaseSort.DUE_DATE:
                order = (PurchaseDocument.due_date.asc().nulls_last(), PurchaseDocument.created_at)
            case PurchaseSort.DOCUMENT_DATE:
                order = (
                    PurchaseDocument.document_date.desc().nulls_last(),
                    PurchaseDocument.created_at.desc(),
                )
            case PurchaseSort.NEWEST:
                order = (PurchaseDocument.created_at.desc(),)

        total = await self._session.scalar(
            select(func.count()).select_from(PurchaseDocument).where(*conditions)
        )
        result = await self._session.scalars(
            select(PurchaseDocument)
            .where(*conditions)
            .order_by(*order, PurchaseDocument.id)
            .limit(limit)
            .offset(offset)
        )
        return result.all(), total or 0

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

    async def list_linked_receipts(self, card_invoice_id: UUID) -> Sequence[PurchaseDocument]:
        result = await self._session.scalars(
            select(PurchaseDocument)
            .where(PurchaseDocument.card_invoice_id == card_invoice_id)
            .order_by(PurchaseDocument.document_date, PurchaseDocument.created_at)
        )
        return result.all()

    async def list_unlinked_card_receipts(
        self, date_from: date | None, date_to: date | None
    ) -> Sequence[PurchaseDocument]:
        statement = (
            select(PurchaseDocument)
            .where(
                PurchaseDocument.stage == PurchaseStage.REGISTERED,
                PurchaseDocument.kind.in_((PurchaseKind.RECEIPT, PurchaseKind.INVOICE)),
                PurchaseDocument.payment_method == PaymentMethod.CARD,
                PurchaseDocument.card_invoice_id.is_(None),
            )
            .order_by(PurchaseDocument.document_date, PurchaseDocument.created_at)
        )
        if date_from is not None:
            statement = statement.where(PurchaseDocument.document_date >= date_from)
        if date_to is not None:
            statement = statement.where(PurchaseDocument.document_date <= date_to)
        result = await self._session.scalars(statement)
        return result.all()

    async def count_inbox(self) -> int:
        result = await self._session.scalar(
            select(func.count())
            .select_from(PurchaseDocument)
            .where(PurchaseDocument.stage == PurchaseStage.INBOX)
        )
        return result or 0

    async def unpaid_figures(self, today: date) -> UnpaidFigures:
        """Aggregates over registered, unpaid invoices and card invoices."""
        is_unpaid = (
            (PurchaseDocument.stage == PurchaseStage.REGISTERED)
            & (PurchaseDocument.payment_status == PaymentStatus.UNPAID)
            & PurchaseDocument.kind.in_((PurchaseKind.INVOICE, PurchaseKind.CARD_INVOICE))
        )
        has_base = PurchaseDocument.amount_base.is_not(None)
        row = (
            await self._session.execute(
                select(
                    func.count(),
                    func.coalesce(func.sum(PurchaseDocument.amount_base), Decimal(0)),
                    func.count().filter(has_base & ~PurchaseDocument.amount_base_final),
                    func.count().filter(~has_base),
                    func.count().filter(PurchaseDocument.due_date < today),
                    func.count().filter(
                        PurchaseDocument.due_date.between(
                            today, today + timedelta(days=DUE_SOON_DAYS - 1)
                        )
                    ),
                ).where(is_unpaid)
            )
        ).one()
        return UnpaidFigures(*row)

    async def list_registered_in_range(
        self, date_from: date, date_to: date
    ) -> Sequence[PurchaseDocument]:
        """Registered documents dated in the range that are not linked to a card invoice."""
        result = await self._session.scalars(
            select(PurchaseDocument)
            .where(
                PurchaseDocument.stage == PurchaseStage.REGISTERED,
                PurchaseDocument.card_invoice_id.is_(None),
                PurchaseDocument.document_date >= date_from,
                PurchaseDocument.document_date <= date_to,
            )
            .order_by(PurchaseDocument.document_date, PurchaseDocument.created_at)
        )
        return result.all()

    async def list_receipts_of(
        self, card_invoice_ids: Sequence[UUID]
    ) -> Sequence[PurchaseDocument]:
        if not card_invoice_ids:
            return []
        result = await self._session.scalars(
            select(PurchaseDocument)
            .where(PurchaseDocument.card_invoice_id.in_(card_invoice_ids))
            .order_by(PurchaseDocument.document_date, PurchaseDocument.created_at)
        )
        return result.all()
