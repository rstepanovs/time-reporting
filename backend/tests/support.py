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


class UserFactory(Protocol):
    async def __call__(
        self,
        *,
        role: UserRole = UserRole.WORKER,
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
    ) -> ProjectDTO: ...
