"""Route guards: resolve the caller from the bearer token and enforce roles.

This is the auth module's public API for other modules' routers.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from time_reporting.api.deps import BusDep
from time_reporting.modules.auth.exceptions import InvalidTokenError
from time_reporting.modules.auth.jwt import decode_access_token
from time_reporting.modules.users.contracts import GetUserById, UserDTO, UserRole

# Must match the login route: api_router prefix + auth router prefix + "/login".
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], bus: BusDep) -> UserDTO:
    try:
        payload = decode_access_token(token)
    except InvalidTokenError as exc:
        raise _unauthorized() from exc

    # Status and role are read from the database on every request, so deactivation, role changes
    # and password changes (token_version) take effect immediately.
    user = await bus.query(GetUserById(user_id=payload.user_id))
    if user is None or not user.is_active or user.token_version != payload.token_version:
        raise _unauthorized()
    return user


CurrentUserDep = Annotated[UserDTO, Depends(get_current_user)]


def require_roles(*roles: UserRole) -> Callable[[UserDTO], Awaitable[UserDTO]]:
    """Build a dependency that admits only users with one of ``roles``."""
    allowed = frozenset(roles)

    async def dependency(user: CurrentUserDep) -> UserDTO:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
            )
        return user

    return dependency


AdminDep = Annotated[UserDTO, Depends(require_roles(UserRole.ADMIN))]
