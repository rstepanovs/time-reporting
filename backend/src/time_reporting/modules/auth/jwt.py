"""Issuing and validating JWT access tokens."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from time_reporting.core.config import get_settings
from time_reporting.modules.auth.exceptions import InvalidTokenError

_REQUIRED_CLAIMS = ["sub", "ver", "iat", "exp"]


@dataclass(frozen=True, slots=True)
class AccessToken:
    token: str
    expires_in: int
    """Lifetime in seconds."""


@dataclass(frozen=True, slots=True)
class TokenPayload:
    user_id: UUID
    token_version: int


def create_access_token(
    user_id: UUID, *, token_version: int, now: datetime | None = None
) -> AccessToken:
    settings = get_settings()
    issued_at = now or datetime.now(UTC)
    lifetime = timedelta(minutes=settings.access_token_expire_minutes)
    claims = {
        "sub": str(user_id),
        "ver": token_version,
        "iat": issued_at,
        "exp": issued_at + lifetime,
    }
    token = jwt.encode(
        claims, settings.jwt_secret_key.get_secret_value(), algorithm=settings.jwt_algorithm
    )
    return AccessToken(token=token, expires_in=int(lifetime.total_seconds()))


def decode_access_token(token: str) -> TokenPayload:
    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            options={"require": _REQUIRED_CLAIMS},
        )
        user_id = UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError) as exc:
        raise InvalidTokenError() from exc

    token_version = claims["ver"]
    if not isinstance(token_version, int) or isinstance(token_version, bool):
        raise InvalidTokenError()
    return TokenPayload(user_id=user_id, token_version=token_version)
