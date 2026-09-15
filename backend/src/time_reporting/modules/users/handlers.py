"""Command and query handlers of the users module (registered in ``users.module``).

Handlers translate between bus messages and the service/repository and never return ORM entities.
"""

from time_reporting.core.cqrs import Bus
from time_reporting.modules.users.contracts import (
    ChangeOwnPassword,
    CreateUser,
    DeleteUser,
    GetUserById,
    GetUserCredentialsByEmail,
    GetUsersByIds,
    ListUsers,
    RecordSuccessfulLogin,
    ResetUserPassword,
    UpdateUser,
    UserCredentialsDTO,
    UserDTO,
    UserPageDTO,
)
from time_reporting.modules.users.models import User
from time_reporting.modules.users.repository import UserRepository
from time_reporting.modules.users.service import UserService


def to_dto(user: User) -> UserDTO:
    return UserDTO(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        token_version=user.token_version,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


# --- Queries ---


class _QueryHandler:
    def __init__(self, bus: Bus) -> None:
        self._users = UserRepository(bus.session)


class GetUserByIdHandler(_QueryHandler):
    async def handle(self, query: GetUserById) -> UserDTO | None:
        user = await self._users.get_by_id(query.user_id)
        return None if user is None else to_dto(user)


class GetUserCredentialsByEmailHandler(_QueryHandler):
    async def handle(self, query: GetUserCredentialsByEmail) -> UserCredentialsDTO | None:
        user = await self._users.get_by_email(query.email)
        if user is None:
            return None
        return UserCredentialsDTO(
            id=user.id,
            password_hash=user.password_hash,
            is_active=user.is_active,
            token_version=user.token_version,
        )


class GetUsersByIdsHandler(_QueryHandler):
    async def handle(self, query: GetUsersByIds) -> tuple[UserDTO, ...]:
        users = await self._users.get_by_ids(query.user_ids)
        return tuple(to_dto(user) for user in users)


class ListUsersHandler(_QueryHandler):
    async def handle(self, query: ListUsers) -> UserPageDTO:
        users = await self._users.get_page(
            limit=query.limit,
            offset=query.offset,
            search=query.search,
            include_inactive=query.include_inactive,
            roles=query.roles,
        )
        return UserPageDTO(
            items=tuple(to_dto(user) for user in users),
            total=await self._users.count(
                search=query.search, include_inactive=query.include_inactive, roles=query.roles
            ),
            limit=query.limit,
            offset=query.offset,
        )


# --- Commands ---


class _CommandHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = UserService(bus.session)


class CreateUserHandler(_CommandHandler):
    async def handle(self, command: CreateUser) -> UserDTO:
        user = await self._service.create_user(
            name=command.name, email=command.email, role=command.role, password=command.password
        )
        return to_dto(user)


class UpdateUserHandler(_CommandHandler):
    async def handle(self, command: UpdateUser) -> UserDTO:
        user = await self._service.update_user(
            command.user_id,
            acting_user_id=command.acting_user_id,
            name=command.name,
            email=command.email,
            role=command.role,
            is_active=command.is_active,
        )
        return to_dto(user)


class ResetUserPasswordHandler(_CommandHandler):
    async def handle(self, command: ResetUserPassword) -> None:
        await self._service.reset_password(command.user_id, command.new_password)


class ChangeOwnPasswordHandler(_CommandHandler):
    async def handle(self, command: ChangeOwnPassword) -> None:
        await self._service.change_own_password(
            command.user_id,
            current_password=command.current_password,
            new_password=command.new_password,
        )


class RecordSuccessfulLoginHandler(_CommandHandler):
    async def handle(self, command: RecordSuccessfulLogin) -> None:
        await self._service.record_login(
            command.user_id, rehashed_password_hash=command.rehashed_password_hash
        )


class DeleteUserHandler(_CommandHandler):
    async def handle(self, command: DeleteUser) -> None:
        await self._service.delete_user(command.user_id, acting_user_id=command.acting_user_id)
