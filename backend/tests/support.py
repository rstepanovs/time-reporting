"""Shared test helpers (types and constants used together with the fixtures in ``conftest``)."""

from collections.abc import Callable
from typing import Protocol

from time_reporting.modules.users.contracts import UserDTO, UserRole

DEFAULT_PASSWORD = "correct-horse-battery"

type AuthHeaders = Callable[[UserDTO], dict[str, str]]


class UserFactory(Protocol):
    async def __call__(
        self,
        *,
        role: UserRole = UserRole.WORKER,
        email: str | None = None,
        name: str = "Test User",
        password: str = DEFAULT_PASSWORD,
    ) -> UserDTO: ...
