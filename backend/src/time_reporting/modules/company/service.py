"""Company settings domain logic on the ORM entity.

Changes are flushed through the repository; the bus commits.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from time_reporting.modules.company.contracts import (
    ALLOWED_LOGO_CONTENT_TYPES,
    INVOICE_LOCALES,
    LOGO_MAX_BYTES,
    CompanyAddressDTO,
    CompanyLogoTooLargeError,
    CompanyLogoTypeNotAllowedError,
    InvalidInvoiceLocaleError,
    UpdateCompanySettings,
)
from time_reporting.modules.company.models import CompanySettings
from time_reporting.modules.company.repository import CompanyRepository


class CompanyService:
    def __init__(self, session: AsyncSession) -> None:
        self._settings = CompanyRepository(session)

    async def get_settings(self) -> CompanySettings:
        return await self._settings.get()

    async def update_settings(
        self, data: UpdateCompanySettings
    ) -> tuple[CompanySettings, tuple[str, ...]]:
        """Returns the updated row plus the names of the fields that actually changed, for the
        caller to audit."""
        if data.default_invoice_locale not in INVOICE_LOCALES:
            raise InvalidInvoiceLocaleError(data.default_invoice_locale)

        settings = await self._settings.get()
        changed = [
            field_name
            for field_name in _SCALAR_FIELDS
            if getattr(data, field_name) != getattr(settings, field_name)
        ]
        for field_name in _SCALAR_FIELDS:
            setattr(settings, field_name, getattr(data, field_name))
        if _address_changed(settings, data.address):
            changed.append("address")
        _set_address(settings, data.address)

        await self._settings.save(settings)
        return settings, tuple(changed)

    async def set_logo(self, *, content_type: str, content: bytes) -> CompanySettings:
        if content_type not in ALLOWED_LOGO_CONTENT_TYPES:
            raise CompanyLogoTypeNotAllowedError(content_type)
        if len(content) > LOGO_MAX_BYTES:
            raise CompanyLogoTooLargeError(len(content))

        settings = await self._settings.get()
        settings.logo = content
        settings.logo_content_type = content_type
        await self._settings.save(settings)
        return settings

    async def clear_logo(self) -> CompanySettings:
        settings = await self._settings.get()
        settings.logo = None
        settings.logo_content_type = None
        await self._settings.save(settings)
        return settings

    async def allocate_invoice_number(self) -> str:
        settings = await self._settings.get_for_update()
        number = f"{settings.invoice_number_prefix}{settings.next_invoice_number}"
        settings.next_invoice_number += 1
        await self._settings.save(settings)
        return number

    async def allocate_customer_number(self) -> str:
        settings = await self._settings.get_for_update()
        number = f"{settings.customer_number_prefix}{settings.next_customer_number}"
        settings.next_customer_number += 1
        await self._settings.save(settings)
        return number


# Fields copied verbatim from UpdateCompanySettings onto CompanySettings (everything except the
# address, which is a nested value compared/set as a whole by _address_changed/_set_address).
_SCALAR_FIELDS = (
    "legal_name",
    "org_number",
    "vat_number",
    "email",
    "phone",
    "registered_office",
    "bankgiro",
    "iban",
    "bic",
    "f_tax_approved",
    "default_invoice_locale",
    "late_interest",
    "invoice_number_prefix",
    "next_invoice_number",
    "customer_number_prefix",
    "next_customer_number",
    "allow_self_review",
)


def _address_changed(settings: CompanySettings, address: CompanyAddressDTO) -> bool:
    return (
        settings.address_street != address.street
        or settings.address_street2 != address.street2
        or settings.address_postal_code != address.postal_code
        or settings.address_city != address.city
        or settings.address_country != address.country.upper()
    )


def _set_address(settings: CompanySettings, address: CompanyAddressDTO) -> None:
    settings.address_street = address.street
    settings.address_street2 = address.street2
    settings.address_postal_code = address.postal_code
    settings.address_city = address.city
    settings.address_country = address.country.upper()
