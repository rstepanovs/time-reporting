"""Auth HTTP API."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from time_reporting.api.deps import BusDep
from time_reporting.modules.auth.exceptions import InvalidCredentialsError
from time_reporting.modules.auth.schemas import TokenResponse
from time_reporting.modules.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    responses={status.HTTP_401_UNAUTHORIZED: {"description": "Incorrect email or password"}},
)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], bus: BusDep
) -> TokenResponse:
    """Exchange email (sent as the OAuth2 ``username`` field) and password for an access token."""
    try:
        access_token = await AuthService(bus).login(form.username, form.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return TokenResponse(access_token=access_token.token, expires_in=access_token.expires_in)
