"""Persistence of ``User`` entities. Flushes but never commits — the bus owns transactions."""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from time_reporting.db.queries import escape_like
from time_reporting.modules.users.contracts import EmailAlreadyExistsError, UserInUseError
from time_reporting.modules.users.models import User

_EMAIL_UNIQUE_CONSTRAINT = "uq_users_email"


def normalize_email(email: str) -> str:
    return email.strip().lower()


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.scalars(
            select(User).where(User.email == normalize_email(email))
        )
        return result.one_or_none()

    async def get_by_ids(self, user_ids: frozenset[UUID]) -> Sequence[User]:
        if not user_ids:
            return ()
        result = await self._session.scalars(
            select(User).where(User.id.in_(user_ids)).order_by(User.name, User.id)
        )
        return result.all()

    async def get_page(
        self, *, limit: int, offset: int, search: str | None, include_inactive: bool
    ) -> Sequence[User]:
        statement = (
            self._filtered(select(User), search=search, include_inactive=include_inactive)
            .order_by(User.created_at, User.id)
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.scalars(statement)
        return result.all()

    async def count(self, *, search: str | None, include_inactive: bool) -> int:
        statement = self._filtered(
            select(func.count()).select_from(User), search=search, include_inactive=include_inactive
        )
        result = await self._session.execute(statement)
        return result.scalar_one()

    def _filtered[T: tuple[Any, ...]](
        self, statement: Select[T], *, search: str | None, include_inactive: bool
    ) -> Select[T]:
        if not include_inactive:
            statement = statement.where(User.is_active.is_(True))
        if search:
            pattern = f"%{escape_like(search)}%"
            statement = statement.where(
                or_(User.name.ilike(pattern, escape="\\"), User.email.ilike(pattern, escape="\\"))
            )
        return statement

    async def save(self, user: User) -> None:
        """Add ``user`` to the session (if new) and flush pending changes."""
        self._session.add(user)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            # A concurrent request may have taken the email after the service's pre-check.
            if _EMAIL_UNIQUE_CONSTRAINT in str(exc.orig):
                raise EmailAlreadyExistsError(user.email) from exc
            raise

    async def delete(self, user: User) -> None:
        """Delete ``user``. Raises ``UserInUseError`` if other data (a project membership, a time
        entry, ...) still references it."""
        user_id = user.id  # read before flush: a failed flush may expire ORM attributes
        await self._session.delete(user)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            if "foreign key constraint" in str(exc.orig):
                raise UserInUseError(user_id) from exc
            raise
