from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
import pytest

from time_reporting.core.config import get_settings
from time_reporting.modules.auth.exceptions import InvalidTokenError
from time_reporting.modules.auth.jwt import create_access_token, decode_access_token


def _valid_claims() -> dict[str, Any]:
    now = datetime.now(UTC)
    return {"sub": str(uuid4()), "ver": 0, "iat": now, "exp": now + timedelta(minutes=5)}


def _encode(claims: dict[str, Any], key: str | None = None) -> str:
    secret = key or get_settings().jwt_secret_key.get_secret_value()
    return jwt.encode(claims, secret, algorithm="HS256")


def test_round_trip() -> None:
    user_id = uuid4()

    access_token = create_access_token(user_id, token_version=3)
    payload = decode_access_token(access_token.token)

    assert payload.user_id == user_id
    assert payload.token_version == 3
    assert access_token.expires_in == get_settings().access_token_expire_minutes * 60


def test_expired_token_is_rejected() -> None:
    access_token = create_access_token(
        uuid4(), token_version=0, now=datetime.now(UTC) - timedelta(days=1)
    )

    with pytest.raises(InvalidTokenError):
        decode_access_token(access_token.token)


def test_foreign_signature_is_rejected() -> None:
    token = _encode(_valid_claims(), key="another-secret-key-that-is-long-enough-for-hs256")

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_unsigned_token_is_rejected() -> None:
    token = jwt.encode(_valid_claims(), key=None, algorithm="none")

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


@pytest.mark.parametrize("claim", ["sub", "ver", "iat", "exp"])
def test_missing_claim_is_rejected(claim: str) -> None:
    claims = _valid_claims()
    del claims[claim]

    with pytest.raises(InvalidTokenError):
        decode_access_token(_encode(claims))


@pytest.mark.parametrize(("claim", "value"), [("sub", "not-a-uuid"), ("ver", "1"), ("ver", True)])
def test_malformed_claim_is_rejected(claim: str, value: object) -> None:
    claims = _valid_claims() | {claim: value}

    with pytest.raises(InvalidTokenError):
        decode_access_token(_encode(claims))


def test_garbage_is_rejected() -> None:
    with pytest.raises(InvalidTokenError):
        decode_access_token("not-a-jwt")
