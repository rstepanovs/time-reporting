from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from time_reporting.core.passwords import hash_password, verify_dummy, verify_password


async def test_hash_and_verify() -> None:
    password_hash = await hash_password("correct-horse")

    assert "correct-horse" not in password_hash
    assert await verify_password("correct-horse", password_hash) == (True, None)
    assert (await verify_password("wrong-horse", password_hash))[0] is False


async def test_outdated_hash_is_upgraded_on_verification() -> None:
    weak_hasher = PasswordHash((Argon2Hasher(time_cost=1, memory_cost=8192, parallelism=1),))
    weak_hash = weak_hasher.hash("correct-horse")

    is_valid, upgraded = await verify_password("correct-horse", weak_hash)

    assert is_valid
    assert upgraded is not None
    assert upgraded != weak_hash
    assert await verify_password("correct-horse", upgraded) == (True, None)


async def test_verify_dummy_completes_for_any_password() -> None:
    await verify_dummy("anything")
