"""Persistence of ``Customer`` entities. Flushes but never commits — the bus owns transactions."""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from time_reporting.db.queries import escape_like
from time_reporting.modules.customers.contracts import (
    CustomerInUseError,
    CustomerNameAlreadyExistsError,
)
from time_reporting.modules.customers.models import Customer

_NAME_UNIQUE_CONSTRAINT = "uq_customers_name"
# The projects.customer_id foreign key (RESTRICT); referenced by table/constraint name only, never
# by importing the projects module.
_PROJECTS_FK_CONSTRAINT = "fk_projects_customer_id_customers"


class CustomerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, customer_id: UUID) -> Customer | None:
        return await self._session.get(Customer, customer_id)

    async def get_by_name(self, name: str) -> Customer | None:
        result = await self._session.scalars(select(Customer).where(Customer.name == name))
        return result.one_or_none()

    async def get_by_ids(self, customer_ids: frozenset[UUID]) -> Sequence[Customer]:
        if not customer_ids:
            return ()
        result = await self._session.scalars(
            select(Customer)
            .where(Customer.id.in_(customer_ids))
            .order_by(Customer.name, Customer.id)
        )
        return result.all()

    async def get_page(
        self, *, limit: int, offset: int, include_inactive: bool, search: str | None
    ) -> Sequence[Customer]:
        statement = (
            self._filtered(select(Customer), include_inactive=include_inactive, search=search)
            .order_by(Customer.name, Customer.id)
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.scalars(statement)
        return result.all()

    async def count(self, *, include_inactive: bool, search: str | None) -> int:
        statement = self._filtered(
            select(func.count()).select_from(Customer),
            include_inactive=include_inactive,
            search=search,
        )
        result = await self._session.execute(statement)
        return result.scalar_one()

    def _filtered[T: tuple[Any, ...]](
        self, statement: Select[T], *, include_inactive: bool, search: str | None
    ) -> Select[T]:
        if not include_inactive:
            statement = statement.where(Customer.is_active.is_(True))
        if search:
            pattern = f"%{escape_like(search)}%"
            statement = statement.where(
                or_(
                    Customer.name.ilike(pattern, escape="\\"),
                    Customer.legal_name.ilike(pattern, escape="\\"),
                )
            )
        return statement

    async def save(self, customer: Customer) -> None:
        """Add ``customer`` to the session (if new) and flush pending changes."""
        self._session.add(customer)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            # A concurrent request may have taken the name after the service's pre-check.
            if _NAME_UNIQUE_CONSTRAINT in str(exc.orig):
                raise CustomerNameAlreadyExistsError(customer.name) from exc
            raise

    async def delete(self, customer: Customer) -> None:
        """Delete ``customer``. Raises ``CustomerInUseError`` if it still has projects."""
        customer_id = customer.id  # read before flush: a failed flush may expire ORM attributes
        await self._session.delete(customer)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            if _PROJECTS_FK_CONSTRAINT in str(exc.orig):
                raise CustomerInUseError(customer_id) from exc
            raise
