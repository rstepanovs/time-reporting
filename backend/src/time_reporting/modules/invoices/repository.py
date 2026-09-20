"""Persistence of invoice entities. Flushes but never commits — the bus owns transactions."""

from collections.abc import Sequence
from datetime import date
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from time_reporting.modules.invoices.contracts import InvoiceStatus
from time_reporting.modules.invoices.models import Invoice, InvoiceBillingPeriod, InvoiceLine


class InvoiceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, invoice_id: UUID) -> Invoice | None:
        result = await self._session.scalars(select(Invoice).where(Invoice.id == invoice_id))
        return result.one_or_none()

    async def count_for_customer(self, customer_id: UUID) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(Invoice).where(Invoice.customer_id == customer_id)
        )
        return result.scalar_one()

    async def get_page(
        self,
        *,
        customer_id: UUID | None,
        status: InvoiceStatus | None,
        date_from: date | None,
        date_to: date | None,
        limit: int,
        offset: int,
    ) -> Sequence[Invoice]:
        statement = (
            self._filtered(
                select(Invoice),
                customer_id=customer_id,
                status=status,
                date_from=date_from,
                date_to=date_to,
            )
            .order_by(Invoice.invoice_date.desc(), Invoice.id)
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.scalars(statement)
        return result.all()

    async def count(
        self,
        *,
        customer_id: UUID | None,
        status: InvoiceStatus | None,
        date_from: date | None,
        date_to: date | None,
    ) -> int:
        statement = self._filtered(
            select(func.count()).select_from(Invoice),
            customer_id=customer_id,
            status=status,
            date_from=date_from,
            date_to=date_to,
        )
        result = await self._session.execute(statement)
        return result.scalar_one()

    def _filtered[T: tuple[object, ...]](
        self,
        statement: Select[T],
        *,
        customer_id: UUID | None,
        status: InvoiceStatus | None,
        date_from: date | None,
        date_to: date | None,
    ) -> Select[T]:
        if customer_id is not None:
            statement = statement.where(Invoice.customer_id == customer_id)
        if status is not None:
            statement = statement.where(Invoice.status == status)
        if date_from is not None:
            statement = statement.where(Invoice.invoice_date >= date_from)
        if date_to is not None:
            statement = statement.where(Invoice.invoice_date <= date_to)
        return statement

    async def save(self, invoice: Invoice) -> None:
        """Add ``invoice`` to the session (if new) and flush pending changes."""
        self._session.add(invoice)
        await self._session.flush()

    async def delete(self, invoice: Invoice) -> None:
        await self._session.delete(invoice)
        await self._session.flush()


class InvoiceLineRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, line_id: UUID) -> InvoiceLine | None:
        result = await self._session.scalars(select(InvoiceLine).where(InvoiceLine.id == line_id))
        return result.one_or_none()

    async def list_for_invoice(self, invoice_id: UUID) -> Sequence[InvoiceLine]:
        result = await self._session.scalars(
            select(InvoiceLine)
            .where(InvoiceLine.invoice_id == invoice_id)
            .order_by(InvoiceLine.position)
        )
        return result.all()

    async def next_position(self, invoice_id: UUID) -> int:
        """The position to give the next line added to ``invoice_id`` (existing max + 1, or 1)."""
        result = await self._session.execute(
            select(func.coalesce(func.max(InvoiceLine.position), 0) + 1).where(
                InvoiceLine.invoice_id == invoice_id
            )
        )
        return result.scalar_one()

    async def save(self, line: InvoiceLine) -> None:
        """Add ``line`` to the session (if new) and flush pending changes."""
        self._session.add(line)
        await self._session.flush()

    async def delete(self, line: InvoiceLine) -> None:
        await self._session.delete(line)
        await self._session.flush()


class InvoiceBillingPeriodRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_invoice(self, invoice_id: UUID) -> Sequence[InvoiceBillingPeriod]:
        result = await self._session.scalars(
            select(InvoiceBillingPeriod).where(InvoiceBillingPeriod.invoice_id == invoice_id)
        )
        return result.all()

    async def save(self, link: InvoiceBillingPeriod) -> None:
        """Add ``link`` to the session (if new) and flush pending changes."""
        self._session.add(link)
        await self._session.flush()
