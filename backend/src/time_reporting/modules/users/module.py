"""Registers the users module's handlers on the bus."""

from time_reporting.core.cqrs import HandlerRegistry
from time_reporting.modules.users.contracts import (
    ChangeOwnPassword,
    CreateUser,
    GetUserById,
    GetUserCredentialsByEmail,
    GetUsersByIds,
    ListUsers,
    RecordSuccessfulLogin,
    ResetUserPassword,
    UpdateUser,
)
from time_reporting.modules.users.handlers import (
    ChangeOwnPasswordHandler,
    CreateUserHandler,
    GetUserByIdHandler,
    GetUserCredentialsByEmailHandler,
    GetUsersByIdsHandler,
    ListUsersHandler,
    RecordSuccessfulLoginHandler,
    ResetUserPasswordHandler,
    UpdateUserHandler,
)


def register(registry: HandlerRegistry) -> None:
    registry.query(GetUserById, GetUserByIdHandler)
    registry.query(GetUsersByIds, GetUsersByIdsHandler)
    registry.query(GetUserCredentialsByEmail, GetUserCredentialsByEmailHandler)
    registry.query(ListUsers, ListUsersHandler)

    registry.command(CreateUser, CreateUserHandler)
    registry.command(UpdateUser, UpdateUserHandler)
    registry.command(ResetUserPassword, ResetUserPasswordHandler)
    registry.command(ChangeOwnPassword, ChangeOwnPasswordHandler)
    registry.command(RecordSuccessfulLogin, RecordSuccessfulLoginHandler)
