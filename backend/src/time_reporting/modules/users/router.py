"""Users HTTP API: current-user endpoints and user management for administrators."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from time_reporting.api.deps import BusDep
from time_reporting.modules.auth.dependencies import AdminDep, CurrentUserDep, ManagerDep
from time_reporting.modules.users.contracts import (
    ChangeOwnPassword,
    CreateUser,
    EmailAlreadyExistsError,
    GetUserById,
    InvalidCurrentPasswordError,
    ListUsers,
    ResetUserPassword,
    SelfModificationError,
    UpdateUser,
    UserNotFoundError,
    UserRole,
)
from time_reporting.modules.users.schemas import (
    PasswordChangeRequest,
    PasswordResetRequest,
    UserCreateRequest,
    UserPageResponse,
    UserResponse,
    UserSummaryResponse,
    UserUpdateRequest,
)

router = APIRouter(prefix="/users", tags=["users"])

_NOT_FOUND_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"description": "User not found"}
}
_EMAIL_CONFLICT_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_409_CONFLICT: {"description": "A user with this email already exists"}
}


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")


def _email_conflict() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT, detail="A user with this email already exists"
    )


# /me and /directory routes are declared before /{user_id} so their literal segment is never
# parsed as an id.


@router.get("/me")
async def read_current_user(current_user: CurrentUserDep) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.post(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={status.HTTP_400_BAD_REQUEST: {"description": "Current password is incorrect"}},
)
async def change_own_password(
    body: PasswordChangeRequest, current_user: CurrentUserDep, bus: BusDep
) -> None:
    """Change the caller's password. All previously issued tokens stop working."""
    try:
        await bus.execute(
            ChangeOwnPassword(
                user_id=current_user.id,
                current_password=body.current_password,
                new_password=body.new_password,
            )
        )
    except InvalidCurrentPasswordError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect"
        ) from exc


@router.get("")
async def list_users(
    _admin: AdminDep,
    bus: BusDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    search: Annotated[str | None, Query(max_length=255)] = None,
    include_inactive: bool = True,
    role: Annotated[list[UserRole] | None, Query()] = None,
) -> UserPageResponse:
    page = await bus.query(
        ListUsers(
            limit=limit,
            offset=offset,
            search=search,
            include_inactive=include_inactive,
            roles=frozenset(role) if role else None,
        )
    )
    return UserPageResponse.model_validate(page)


@router.get("/directory")
async def search_user_directory(
    _manager: ManagerDep,
    bus: BusDep,
    search: Annotated[str | None, Query(max_length=255)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    role: Annotated[list[UserRole] | None, Query()] = None,
) -> list[UserSummaryResponse]:
    """Minimal, active-only user list for pickers (e.g. adding a project member or a project
    manager, the latter via ``role=manager``)."""
    page = await bus.query(
        ListUsers(
            limit=limit,
            offset=0,
            search=search,
            include_inactive=False,
            roles=frozenset(role) if role else None,
        )
    )
    return [UserSummaryResponse.model_validate(user) for user in page.items]


@router.post("", status_code=status.HTTP_201_CREATED, responses=_EMAIL_CONFLICT_RESPONSE)
async def create_user(body: UserCreateRequest, admin: AdminDep, bus: BusDep) -> UserResponse:
    try:
        user = await bus.execute(
            CreateUser(
                name=body.name,
                email=body.email,
                roles=body.roles,
                password=body.password,
                actor_id=admin.id,
            )
        )
    except EmailAlreadyExistsError as exc:
        raise _email_conflict() from exc
    return UserResponse.model_validate(user)


@router.get("/{user_id}", responses=_NOT_FOUND_RESPONSE)
async def read_user(user_id: UUID, _admin: AdminDep, bus: BusDep) -> UserResponse:
    user = await bus.query(GetUserById(user_id=user_id))
    if user is None:
        raise _not_found()
    return UserResponse.model_validate(user)


@router.patch(
    "/{user_id}",
    responses={
        **_NOT_FOUND_RESPONSE,
        **_EMAIL_CONFLICT_RESPONSE,
        status.HTTP_400_BAD_REQUEST: {
            "description": "Users cannot remove their own administrator access, or deactivate "
            "or delete themselves"
        },
    },
)
async def update_user(
    user_id: UUID, body: UserUpdateRequest, admin: AdminDep, bus: BusDep
) -> UserResponse:
    try:
        user = await bus.execute(
            UpdateUser(
                user_id=user_id,
                acting_user_id=admin.id,
                name=body.name,
                email=body.email,
                roles=body.roles,
                is_active=body.is_active,
            )
        )
    except UserNotFoundError as exc:
        raise _not_found() from exc
    except EmailAlreadyExistsError as exc:
        raise _email_conflict() from exc
    except SelfModificationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return UserResponse.model_validate(user)


@router.put(
    "/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT, responses=_NOT_FOUND_RESPONSE
)
async def reset_user_password(
    user_id: UUID, body: PasswordResetRequest, admin: AdminDep, bus: BusDep
) -> None:
    """Set a user's password. All tokens previously issued to that user stop working."""
    try:
        await bus.execute(
            ResetUserPassword(user_id=user_id, new_password=body.new_password, actor_id=admin.id)
        )
    except UserNotFoundError as exc:
        raise _not_found() from exc
