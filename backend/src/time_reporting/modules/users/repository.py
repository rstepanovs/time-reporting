"""Persistence of ``User`` entities. Flushes but never commits — the bus owns transactions."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from time_reporting.modules.users.contracts import EmailAlreadyExistsError
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

    async def get_page(self, *, limit: int, offset: int) -> Sequence[User]:
        result = await self._session.scalars(
            select(User).order_by(User.created_at, User.id).limit(limit).offset(offset)
        )
        return result.all()

    async def count(self) -> int:
        result = await self._session.execute(select(func.count()).select_from(User))
        return result.scalar_one()

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
