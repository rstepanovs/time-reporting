"""Public contract of the company module.

Other modules may import only this file: DTOs, commands, queries and domain exceptions. Handlers
for these messages are registered in ``company.module``; ORM entities never leave the module.

``CompanySettings`` is a singleton: there is always exactly one row, created by migration
``add_company_settings_table`` with placeholder values. Only ``customers`` depends on ``company``
(``AllocateCustomerNumber``), so ``company`` is still registered first, before it, in
``modules/registry.py``.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, get_args
from uuid import UUID

from time_reporting.core.cqrs import Command, Query

# Matches faktura_printer.available_locales(); duplicated here (not imported) since a module may
# only import another module's contracts.py, and faktura-printer is only a dependency of the
# future `invoices` module, not of `company`.
type InvoiceLocale = Literal["sv", "en"]
INVOICE_LOCALES: tuple[InvoiceLocale, ...] = get_args(InvoiceLocale.__value__)
ALLOWED_LOGO_CONTENT_TYPES = frozenset({"image/svg+xml", "image/png", "image/jpeg"})
LOGO_MAX_BYTES = 512 * 1024


# --- DTOs ---


@dataclass(frozen=True, slots=True, kw_only=True)
class CompanyAddressDTO:
    street: str
    street2: str | None
    postal_code: str
    city: str
    # ISO 3166-1 alpha-2 code; normalized to upper case on write. May be "" until set.
    country: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CompanySettingsDTO:
    legal_name: str
    org_number: str
    vat_number: str
    address: CompanyAddressDTO
    email: str
    phone: str
    registered_office: str
    bankgiro: str
    iban: str
    bic: str
    f_tax_approved: bool
    # "sv" or "en" — see INVOICE_LOCALES.
    default_invoice_locale: str
    late_interest: str
    invoice_number_prefix: str
    next_invoice_number: int
    customer_number_prefix: str
    next_customer_number: int
    allow_self_review: bool
    # The logo bytes never travel in this DTO — see GetCompanyLogo.
    has_logo: bool
    updated_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class CompanyLogoDTO:
    content: bytes
    content_type: str


# --- Queries ---


@dataclass(frozen=True, slots=True, kw_only=True)
class GetCompanySettings(Query[CompanySettingsDTO]):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class GetCompanyLogo(Query[CompanyLogoDTO | None]):
    pass


# --- Commands ---


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateCompanySettings(Command[CompanySettingsDTO]):
    """Replaces the whole settings row (a single admin form, not a partial patch).

    ``actor_id`` is ``None`` only for a CLI-triggered caller — no such caller exists today, but the
    field mirrors every other audited command's contract (see ``audit/CLAUDE.md``).
    """

    actor_id: UUID | None
    legal_name: str
    org_number: str
    vat_number: str
    address: CompanyAddressDTO
    email: str
    phone: str
    registered_office: str
    bankgiro: str
    iban: str
    bic: str
    f_tax_approved: bool
    default_invoice_locale: str
    late_interest: str
    invoice_number_prefix: str
    # Settable here (not only via AllocateInvoiceNumber) so a first-time setup can resume
    # numbering after an existing paper trail rather than always starting at 1.
    next_invoice_number: int
    customer_number_prefix: str
    # Settable here (not only via AllocateCustomerNumber) for the same reason.
    next_customer_number: int
    allow_self_review: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class SetCompanyLogo(Command[CompanySettingsDTO]):
    actor_id: UUID | None
    content_type: str
    content: bytes


@dataclass(frozen=True, slots=True, kw_only=True)
class ClearCompanyLogo(Command[CompanySettingsDTO]):
    actor_id: UUID | None


@dataclass(frozen=True, slots=True, kw_only=True)
class AllocateInvoiceNumber(Command[str]):
    """Nested-only: no HTTP route calls this directly.

    Locks the singleton settings row (``SELECT ... FOR UPDATE``), returns
    ``invoice_number_prefix + next_invoice_number`` and increments the counter. Gapless because it
    commits with the issuing (outer) transaction: if that transaction later fails, the whole thing
    — including this increment — rolls back with it, so the number is never burned.
    """


@dataclass(frozen=True, slots=True, kw_only=True)
class AllocateCustomerNumber(Command[str]):
    """Nested-only, same shape as ``AllocateInvoiceNumber``: locks the singleton settings row,
    returns ``customer_number_prefix + next_customer_number`` and increments the counter.

    Called by ``customers.CreateCustomer`` only when the caller left ``customer_number`` blank —
    an explicitly given number is used as-is and never allocated here.
    """


# --- Exceptions ---


class CompanyError(Exception):
    """Base class for company module domain errors."""


class CompanyLogoTooLargeError(CompanyError):
    def __init__(self, size_bytes: int) -> None:
        super().__init__(f"Logo is {size_bytes} bytes, over the {LOGO_MAX_BYTES}-byte limit")
        self.size_bytes = size_bytes


class CompanyLogoTypeNotAllowedError(CompanyError):
    def __init__(self, content_type: str) -> None:
        super().__init__(f"Logo type {content_type!r} is not allowed")
        self.content_type = content_type


class InvalidInvoiceLocaleError(CompanyError):
    def __init__(self, locale: str) -> None:
        available = ", ".join(sorted(INVOICE_LOCALES))
        super().__init__(f"Unknown invoice locale {locale!r}, available: {available}")
        self.locale = locale
