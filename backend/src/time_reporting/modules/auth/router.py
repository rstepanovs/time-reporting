"""Auth HTTP API.

``/auth/login`` issues a bearer token (OAuth2 password flow, used by the API docs and scripts);
``/auth/session`` signs the web client in and out with an httpOnly cookie instead.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from time_reporting.api.deps import BusDep
from time_reporting.modules.auth.exceptions import InvalidCredentialsError
from time_reporting.modules.auth.schemas import SessionCreateRequest, SessionResponse, TokenResponse
from time_reporting.modules.auth.service import AuthService
from time_reporting.modules.auth.session_cookie import (
    delete_access_token_cookie,
    set_access_token_cookie,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_INVALID_CREDENTIALS_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"description": "Incorrect email or password"}
}


def _invalid_credentials() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect email or password",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post("/login", responses=_INVALID_CREDENTIALS_RESPONSE)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], bus: BusDep
) -> TokenResponse:
    """Exchange email (sent as the OAuth2 ``username`` field) and password for an access token."""
    try:
        access_token = await AuthService(bus).login(form.username, form.password)
    except InvalidCredentialsError as exc:
        raise _invalid_credentials() from exc
    return TokenResponse(access_token=access_token.token, expires_in=access_token.expires_in)


@router.post("/session", responses=_INVALID_CREDENTIALS_RESPONSE)
async def create_session(
    body: SessionCreateRequest, response: Response, bus: BusDep
) -> SessionResponse:
    """Sign the web client in: the access token is set as an httpOnly cookie, never returned.

    The JSON-only body cannot be sent cross-origin without CORS preflight, which rules out
    login CSRF without requiring the CSRF header here.
    """
    try:
        access_token = await AuthService(bus).login(body.email, body.password)
    except InvalidCredentialsError as exc:
        raise _invalid_credentials() from exc
    set_access_token_cookie(response, access_token)
    return SessionResponse(expires_in=access_token.expires_in)


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(response: Response) -> None:
    """Sign the web client out by clearing the session cookie. Safe to call when signed out."""
    delete_access_token_cookie(response)
