"""Shared test helpers (types and constants used together with the fixtures in ``conftest``)."""

from collections.abc import Callable
from datetime import date
from typing import Protocol
from uuid import UUID

from time_reporting.modules.customers.contracts import (
    BillingAddressDTO,
    BillingIntervalUnit,
    BillingPeriodDTO,
    CustomerDTO,
)
from time_reporting.modules.projects.contracts import ProjectDTO
from time_reporting.modules.users.contracts import UserDTO, UserRole

DEFAULT_PASSWORD = "correct-horse-battery"
DEFAULT_BILLING_ADDRESS = BillingAddressDTO(
    line1="1 Test Street", city="Berlin", postal_code="10115", country="DE"
)
DEFAULT_BILLING_PERIOD = BillingPeriodDTO(
    interval_count=1, interval_unit=BillingIntervalUnit.MONTH, anchor_date=date(2026, 1, 1)
)

type AuthHeaders = Callable[[UserDTO], dict[str, str]]

# Shorthand level sets for tests, matching the demo/migration mapping of the old single-role model:
# an old ``admin`` kept today's effective rights (manager included), an old ``project_manager``
# becomes a plain manager, and an old ``worker`` is a plain employee (no levels).
ADMIN = frozenset({UserRole.ADMIN, UserRole.MANAGER})
MANAGER = frozenset({UserRole.MANAGER})
EMPLOYEE: frozenset[UserRole] = frozenset()
# An admin with no manager level, for tests of the (new) orthogonal guards.
ADMIN_ONLY = frozenset({UserRole.ADMIN})
ACCOUNTANT = frozenset({UserRole.ACCOUNTANT})


class UserFactory(Protocol):
    async def __call__(
        self,
        *,
        roles: frozenset[UserRole] = EMPLOYEE,
        email: str | None = None,
        name: str = "Test User",
        password: str = DEFAULT_PASSWORD,
    ) -> UserDTO: ...


class CustomerFactory(Protocol):
    async def __call__(self, *, name: str | None = None) -> CustomerDTO: ...


class ProjectFactory(Protocol):
    async def __call__(
        self,
        *,
        customer_id: UUID | None = None,
        name: str | None = None,
        description: str | None = None,
        is_internal: bool = False,
        manager_id: UUID | None = None,
    ) -> ProjectDTO: ...
