"""The web client's session: the access token carried in an httpOnly cookie.

The cookie is ``HttpOnly`` (unreadable from JavaScript), ``SameSite=Strict`` and scoped to ``/api``.
Browsers attach cookies on their own, so cookie-authenticated unsafe requests must also carry
``CSRF_HEADER``: a page on another origin cannot add a custom header without passing CORS preflight.
"""

from fastapi import Response

from time_reporting.core.config import get_settings
from time_reporting.modules.auth.jwt import AccessToken

ACCESS_TOKEN_COOKIE = "access_token"
CSRF_HEADER = "X-Requested-With"
_COOKIE_PATH = "/api"


def set_access_token_cookie(response: Response, access_token: AccessToken) -> None:
    response.set_cookie(
        ACCESS_TOKEN_COOKIE,
        access_token.token,
        max_age=access_token.expires_in,
        path=_COOKIE_PATH,
        secure=get_settings().auth_cookie_secure,
        httponly=True,
        samesite="strict",
    )


def delete_access_token_cookie(response: Response) -> None:
    response.delete_cookie(
        ACCESS_TOKEN_COOKIE,
        path=_COOKIE_PATH,
        secure=get_settings().auth_cookie_secure,
        httponly=True,
        samesite="strict",
    )
