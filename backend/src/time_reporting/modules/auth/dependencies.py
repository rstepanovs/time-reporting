"""Route guards: resolve the caller from the access token and enforce roles.

This is the auth module's public API for other modules' routers.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyCookie, OAuth2PasswordBearer

from time_reporting.api.deps import BusDep
from time_reporting.modules.auth.exceptions import InvalidTokenError
from time_reporting.modules.auth.jwt import decode_access_token
from time_reporting.modules.auth.session_cookie import ACCESS_TOKEN_COOKIE, CSRF_HEADER
from time_reporting.modules.users.contracts import GetUserById, UserDTO, UserRole

# Must match the login route: api_router prefix + auth router prefix + "/login".
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)
cookie_scheme = APIKeyCookie(
    name=ACCESS_TOKEN_COOKIE,
    auto_error=False,
    description="Session cookie set by POST /api/v1/auth/session for the web client.",
)

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _resolve_token(request: Request, bearer_token: str | None, cookie_token: str | None) -> str:
    # An explicit Authorization header wins over a cookie the browser may attach on its own.
    if bearer_token is not None:
        return bearer_token
    if cookie_token is None:
        raise _unauthorized()
    if request.method not in _SAFE_METHODS and CSRF_HEADER not in request.headers:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=f"Missing {CSRF_HEADER} header"
        )
    return cookie_token


async def get_current_user(
    request: Request,
    bearer_token: Annotated[str | None, Depends(oauth2_scheme)],
    cookie_token: Annotated[str | None, Depends(cookie_scheme)],
    bus: BusDep,
) -> UserDTO:
    token = _resolve_token(request, bearer_token, cookie_token)
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
# Administrators and project managers, who manage billing data such as customers.
ManagerDep = Annotated[UserDTO, Depends(require_roles(UserRole.ADMIN, UserRole.PROJECT_MANAGER))]
