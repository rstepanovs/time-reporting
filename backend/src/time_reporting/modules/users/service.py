"""User domain logic on ORM entities.

Changes are flushed through the repository; the bus commits.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from time_reporting.core.passwords import hash_password, verify_password
from time_reporting.db.mixins import utc_now
from time_reporting.modules.users.contracts import (
    EmailAlreadyExistsError,
    InvalidCurrentPasswordError,
    SelfModificationError,
    UserNotFoundError,
    UserRole,
)
from time_reporting.modules.users.models import User
from time_reporting.modules.users.repository import UserRepository, normalize_email


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self._users = UserRepository(session)

    async def get_user(self, user_id: UUID) -> User:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(user_id)
        return user

    async def create_user(self, *, name: str, email: str, role: UserRole, password: str) -> User:
        email = normalize_email(email)
        await self._ensure_email_available(email)
        user = User(name=name, email=email, role=role, password_hash=await hash_password(password))
        await self._users.save(user)
        return user

    async def update_user(
        self,
        user_id: UUID,
        *,
        acting_user_id: UUID,
        name: str | None = None,
        email: str | None = None,
        role: UserRole | None = None,
        is_active: bool | None = None,
    ) -> User:
        user = await self.get_user(user_id)
        # Changing one's own role or deactivating oneself could lock the last admin out.
        if user.id == acting_user_id and (
            (role is not None and role != user.role) or is_active is False
        ):
            raise SelfModificationError()

        if name is not None:
            user.name = name
        if email is not None and normalize_email(email) != user.email:
            email = normalize_email(email)
            await self._ensure_email_available(email)
            user.email = email
        if role is not None:
            user.role = role
        if is_active is not None:
            user.is_active = is_active
        await self._users.save(user)
        return user

    async def reset_password(self, user_id: UUID, new_password: str) -> None:
        await self._set_password(await self.get_user(user_id), new_password)

    async def change_own_password(
        self, user_id: UUID, *, current_password: str, new_password: str
    ) -> None:
        user = await self.get_user(user_id)
        is_valid, _ = await verify_password(current_password, user.password_hash)
        if not is_valid:
            raise InvalidCurrentPasswordError()
        await self._set_password(user, new_password)

    async def delete_user(self, user_id: UUID, *, acting_user_id: UUID) -> None:
        user = await self.get_user(user_id)
        if user.id == acting_user_id:
            raise SelfModificationError()
        await self._users.delete(user)

    async def record_login(self, user_id: UUID, *, rehashed_password_hash: str | None) -> None:
        user = await self.get_user(user_id)
        user.last_login_at = utc_now()
        if rehashed_password_hash is not None:
            user.password_hash = rehashed_password_hash
        await self._users.save(user)

    async def _set_password(self, user: User, new_password: str) -> None:
        user.password_hash = await hash_password(new_password)
        user.token_version += 1
        await self._users.save(user)

    async def _ensure_email_available(self, email: str) -> None:
        if await self._users.get_by_email(email) is not None:
            raise EmailAlreadyExistsError(email)
