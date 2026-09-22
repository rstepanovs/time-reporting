"""HTTP request/response models of the company API."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from time_reporting.modules.company.contracts import CompanyAddressDTO, InvoiceLocale

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]
CodeText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=64)]
PostalCode = Annotated[str, StringConstraints(strip_whitespace=True, max_length=32)]
CountryCode = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^([A-Za-z]{2})?$"),
    Field(examples=["SE"], description='ISO 3166-1 alpha-2 country code, or "" if not yet set'),
]
LateInterest = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]
InvoiceNumberPrefix = Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)]


class CompanyAddressRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    street: ShortText = ""
    street2: ShortText | None = None
    postal_code: PostalCode = ""
    city: ShortText = ""
    country: CountryCode = ""

    def to_dto(self) -> CompanyAddressDTO:
        return CompanyAddressDTO(**self.model_dump())


class CompanySettingsUpdateRequest(BaseModel):
    """A full replace of the settings row — the admin page always submits the whole form."""

    model_config = ConfigDict(extra="forbid")

    legal_name: ShortText = ""
    org_number: CodeText = ""
    vat_number: CodeText = ""
    address: CompanyAddressRequest = Field(default_factory=CompanyAddressRequest)
    email: EmailStr | Literal[""] = ""
    phone: CodeText = ""
    registered_office: ShortText = ""
    bankgiro: CodeText = ""
    iban: CodeText = ""
    bic: CodeText = ""
    f_tax_approved: bool = False
    default_invoice_locale: InvoiceLocale = "sv"
    late_interest: LateInterest = ""
    invoice_number_prefix: InvoiceNumberPrefix = ""
    next_invoice_number: Annotated[int, Field(ge=1)] = 1
    allow_self_review: bool = False


class CompanyAddressResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    street: str
    street2: str | None
    postal_code: str
    city: str
    country: str


class CompanySettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    legal_name: str
    org_number: str
    vat_number: str
    address: CompanyAddressResponse
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
    next_invoice_number: int
    allow_self_review: bool
    has_logo: bool
    updated_at: datetime
