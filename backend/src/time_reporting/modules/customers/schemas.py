"""HTTP request/response models of the customers API."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator

from time_reporting.modules.customers.contracts import (
    BillingAddressDTO,
    BillingIntervalUnit,
    BillingPeriodDTO,
)

# Kept as a plain inline Literal (not a named type alias) so it doesn't collide with
# ``company.contracts.InvoiceLocale``'s own hoisted OpenAPI schema of the same name — see
# ``customers.contracts.INVOICE_LOCALES``, the source of truth these two literals both mirror.
CustomerInvoiceLocale = Literal["sv", "en"]

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
TaxId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
PostalCode = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]
CountryCode = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z]{2}$"), Field(examples=["DE"])
]
CurrencyCode = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z]{3}$"), Field(examples=["EUR"])
]
PaymentTermsDays = Annotated[int, Field(ge=0, le=365)]
Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=10_000)]
VatRate = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]
CustomerNumber = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
]
YourReference = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
]


class BillingAddressRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line1: ShortText
    line2: ShortText | None = None
    city: ShortText
    region: ShortText | None = None
    postal_code: PostalCode | None = None
    country: CountryCode = Field(description="ISO 3166-1 alpha-2 country code")

    def to_dto(self) -> BillingAddressDTO:
        return BillingAddressDTO(**self.model_dump())


class BillingPeriodRequest(BaseModel):
    """Consecutive billing periods of ``interval_count`` ``interval_unit``s from ``anchor_date``."""

    model_config = ConfigDict(extra="forbid")

    interval_count: Annotated[int, Field(ge=1, le=366)]
    interval_unit: BillingIntervalUnit
    anchor_date: date

    def to_dto(self) -> BillingPeriodDTO:
        return BillingPeriodDTO(**self.model_dump())


class CustomerCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ShortText
    legal_name: ShortText | None = None
    tax_id: TaxId | None = None
    billing_email: EmailStr | None = None
    billing_address: BillingAddressRequest
    billing_period: BillingPeriodRequest
    currency: CurrencyCode = Field(description="ISO 4217 currency code")
    payment_terms_days: PaymentTermsDays = 30
    notes: Notes | None = None
    vat_rate: VatRate | None = Field(default=None, description="Null prints no VAT line")
    vat_note: Notes | None = None
    invoice_locale: CustomerInvoiceLocale | None = Field(
        default=None, description="Falls back to the company's default when null"
    )
    customer_number: CustomerNumber | None = None
    your_reference: YourReference | None = None


# Fields of CustomerUpdateRequest that may be omitted but not set to null.
_NON_NULLABLE_UPDATE_FIELDS = (
    "name",
    "billing_address",
    "billing_period",
    "currency",
    "payment_terms_days",
    "is_active",
)


class CustomerUpdateRequest(BaseModel):
    """Partial update: omitted fields are left unchanged.

    ``null`` clears ``legal_name``, ``tax_id``, ``billing_email``, ``notes``, ``vat_rate``,
    ``vat_note``, ``invoice_locale``, ``customer_number`` or ``your_reference``; it is rejected
    for the other fields. ``billing_address`` and ``billing_period`` replace the whole object.
    """

    model_config = ConfigDict(extra="forbid")

    name: ShortText | None = None
    legal_name: ShortText | None = None
    tax_id: TaxId | None = None
    billing_email: EmailStr | None = None
    billing_address: BillingAddressRequest | None = None
    billing_period: BillingPeriodRequest | None = None
    currency: CurrencyCode | None = None
    payment_terms_days: PaymentTermsDays | None = None
    notes: Notes | None = None
    is_active: bool | None = None
    vat_rate: VatRate | None = None
    vat_note: Notes | None = None
    invoice_locale: CustomerInvoiceLocale | None = None
    customer_number: CustomerNumber | None = None
    your_reference: YourReference | None = None

    @model_validator(mode="after")
    def _reject_null_for_required_fields(self) -> Self:
        nulls = [
            name
            for name in _NON_NULLABLE_UPDATE_FIELDS
            if name in self.model_fields_set and getattr(self, name) is None
        ]
        if nulls:
            raise ValueError(f"These fields cannot be null: {', '.join(nulls)}")
        return self


class BillingAddressResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    line1: str
    line2: str | None
    city: str
    region: str | None
    postal_code: str | None
    country: str


class BillingPeriodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    interval_count: int
    interval_unit: BillingIntervalUnit
    anchor_date: date


class CustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    legal_name: str | None
    tax_id: str | None
    billing_email: str | None
    billing_address: BillingAddressResponse
    billing_period: BillingPeriodResponse
    currency: str
    payment_terms_days: int
    notes: str | None
    is_active: bool
    vat_rate: Decimal | None
    vat_note: str | None
    invoice_locale: str | None
    customer_number: str | None
    your_reference: str | None
    created_at: datetime
    updated_at: datetime


class CustomerPageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[CustomerResponse]
    total: int
    limit: int
    offset: int
