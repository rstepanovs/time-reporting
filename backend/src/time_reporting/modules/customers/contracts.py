"""Public contract of the customers module.

Other modules may import only this file: DTOs, commands, queries and domain exceptions. Handlers
for these messages are registered in ``customers.module``; ORM entities never leave the module.
"""

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Literal, get_args
from uuid import UUID

from time_reporting.core.cqrs import Command, Query


class BillingIntervalUnit(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


type ClearableCustomerField = Literal["legal_name", "tax_id", "billing_email", "notes"]

# Optional text fields that ``UpdateCustomer.clear_fields`` can reset to ``None``.
CLEARABLE_CUSTOMER_FIELDS: tuple[ClearableCustomerField, ...] = get_args(
    ClearableCustomerField.__value__
)


# --- DTOs ---


@dataclass(frozen=True, slots=True, kw_only=True)
class BillingAddressDTO:
    line1: str
    line2: str | None = None
    city: str
    region: str | None = None
    postal_code: str | None = None
    # ISO 3166-1 alpha-2 code; normalized to upper case on write.
    country: str


@dataclass(frozen=True, slots=True, kw_only=True)
class BillingPeriodDTO:
    """Consecutive billing periods of ``interval_count`` ``interval_unit``s from ``anchor_date``."""

    interval_count: int
    interval_unit: BillingIntervalUnit
    anchor_date: date


@dataclass(frozen=True, slots=True, kw_only=True)
class CustomerDTO:
    id: UUID
    name: str
    legal_name: str | None
    tax_id: str | None
    billing_email: str | None
    billing_address: BillingAddressDTO
    billing_period: BillingPeriodDTO
    # ISO 4217 code; normalized to upper case on write.
    currency: str
    payment_terms_days: int
    notes: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class CustomerPageDTO:
    items: tuple[CustomerDTO, ...]
    total: int
    limit: int
    offset: int


# --- Queries ---


@dataclass(frozen=True, slots=True, kw_only=True)
class GetCustomerById(Query[CustomerDTO | None]):
    customer_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ListCustomers(Query[CustomerPageDTO]):
    """Customers ordered by name; archived (inactive) ones only if ``include_inactive``."""

    limit: int
    offset: int
    include_inactive: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class GetCustomersByIds(Query[tuple[CustomerDTO, ...]]):
    """Customers matching ``customer_ids`` (active or archived), ordered by name then id.

    Unknown ids are silently omitted.
    """

    customer_ids: frozenset[UUID]


# --- Commands ---


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateCustomer(Command[CustomerDTO]):
    name: str
    billing_address: BillingAddressDTO
    billing_period: BillingPeriodDTO
    currency: str
    legal_name: str | None = None
    tax_id: str | None = None
    billing_email: str | None = None
    payment_terms_days: int = 30
    notes: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateCustomer(Command[CustomerDTO]):
    """Partial update: fields left as ``None`` are not changed.

    ``billing_address`` and ``billing_period`` replace the whole value. Optional text fields named
    in ``clear_fields`` are reset to ``None``. Customers are never deleted; archive them with
    ``is_active=False``.
    """

    customer_id: UUID
    name: str | None = None
    legal_name: str | None = None
    tax_id: str | None = None
    billing_email: str | None = None
    billing_address: BillingAddressDTO | None = None
    billing_period: BillingPeriodDTO | None = None
    currency: str | None = None
    payment_terms_days: int | None = None
    notes: str | None = None
    is_active: bool | None = None
    clear_fields: frozenset[ClearableCustomerField] = frozenset()


# --- Exceptions ---


class CustomerError(Exception):
    """Base class for customers module domain errors."""


class CustomerNotFoundError(CustomerError):
    def __init__(self, customer_id: UUID) -> None:
        super().__init__(f"Customer {customer_id} not found")
        self.customer_id = customer_id


class CustomerNameAlreadyExistsError(CustomerError):
    def __init__(self, name: str) -> None:
        super().__init__(f"A customer named {name!r} already exists")
        self.name = name
