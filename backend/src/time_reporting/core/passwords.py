"""Password hashing (Argon2id).

Hashing is deliberately CPU-expensive, so it runs in a worker thread to keep the event loop free.
"""

import asyncio
from functools import cache

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128

_hasher = PasswordHash((Argon2Hasher(),))


async def hash_password(password: str) -> str:
    return await asyncio.to_thread(_hasher.hash, password)


async def verify_password(password: str, password_hash: str) -> tuple[bool, str | None]:
    """Check ``password``; the second item is a fresh hash when the stored one is outdated."""
    return await asyncio.to_thread(_hasher.verify_and_update, password, password_hash)


async def verify_dummy(password: str) -> None:
    """Spend as long as a real check, so unknown accounts cannot be detected by response time."""

    def verify() -> None:
        _hasher.verify(password, _dummy_hash())

    await asyncio.to_thread(verify)


@cache
def _dummy_hash() -> str:
    return _hasher.hash("dummy password used only to equalize verification time")
