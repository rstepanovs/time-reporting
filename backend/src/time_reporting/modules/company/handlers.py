"""Command and query handlers of the company module (registered in ``company.module``).

Handlers translate between bus messages and the service/repository and never return ORM entities.
``UpdateCompanySettings``/``SetCompanyLogo``/``ClearCompanyLogo`` take a ``Bus`` (not a plain
session) because they execute a nested ``RecordAuditEvent``.
"""

from uuid import UUID

from time_reporting.core.cqrs import Bus
from time_reporting.modules.audit.contracts import AuditAction, RecordAuditEvent
from time_reporting.modules.company.contracts import (
    AllocateCustomerNumber,
    AllocateInvoiceNumber,
    ClearCompanyLogo,
    CompanyAddressDTO,
    CompanyLogoDTO,
    CompanySettingsDTO,
    GetCompanyLogo,
    GetCompanySettings,
    SetCompanyLogo,
    UpdateCompanySettings,
)
from time_reporting.modules.company.models import CompanySettings
from time_reporting.modules.company.repository import CompanyRepository
from time_reporting.modules.company.service import CompanyService

_ENTITY_TYPE = "company"
_ENTITY_ID = "company"


def to_dto(settings: CompanySettings) -> CompanySettingsDTO:
    return CompanySettingsDTO(
        legal_name=settings.legal_name,
        org_number=settings.org_number,
        vat_number=settings.vat_number,
        address=CompanyAddressDTO(
            street=settings.address_street,
            street2=settings.address_street2,
            postal_code=settings.address_postal_code,
            city=settings.address_city,
            country=settings.address_country,
        ),
        email=settings.email,
        phone=settings.phone,
        registered_office=settings.registered_office,
        bankgiro=settings.bankgiro,
        iban=settings.iban,
        bic=settings.bic,
        f_tax_approved=settings.f_tax_approved,
        default_invoice_locale=settings.default_invoice_locale,
        late_interest=settings.late_interest,
        invoice_number_prefix=settings.invoice_number_prefix,
        next_invoice_number=settings.next_invoice_number,
        customer_number_prefix=settings.customer_number_prefix,
        next_customer_number=settings.next_customer_number,
        allow_self_review=settings.allow_self_review,
        has_logo=settings.logo is not None,
        updated_at=settings.updated_at,
    )


async def _record_update(bus: Bus, actor_id: UUID | None, changed: tuple[str, ...]) -> None:
    if not changed:
        return
    await bus.execute(
        RecordAuditEvent(
            actor_id=actor_id,
            action=AuditAction.COMPANY_UPDATED,
            entity_type=_ENTITY_TYPE,
            entity_id=_ENTITY_ID,
            summary=f"Updated company settings ({', '.join(changed)})",
            details={"fields": list(changed)},
        )
    )


# --- Queries ---


class GetCompanySettingsHandler:
    def __init__(self, bus: Bus) -> None:
        self._company = CompanyRepository(bus.session)

    async def handle(self, query: GetCompanySettings) -> CompanySettingsDTO:
        return to_dto(await self._company.get())


class GetCompanyLogoHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = CompanyService(bus.session)

    async def handle(self, query: GetCompanyLogo) -> CompanyLogoDTO | None:
        settings = await self._service.get_settings()
        if settings.logo is None or settings.logo_content_type is None:
            return None
        return CompanyLogoDTO(content=settings.logo, content_type=settings.logo_content_type)


# --- Commands ---


class UpdateCompanySettingsHandler:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._service = CompanyService(bus.session)

    async def handle(self, command: UpdateCompanySettings) -> CompanySettingsDTO:
        settings, changed = await self._service.update_settings(command)
        await _record_update(self._bus, command.actor_id, changed)
        return to_dto(settings)


class SetCompanyLogoHandler:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._service = CompanyService(bus.session)

    async def handle(self, command: SetCompanyLogo) -> CompanySettingsDTO:
        settings = await self._service.set_logo(
            content_type=command.content_type, content=command.content
        )
        await _record_update(self._bus, command.actor_id, ("logo",))
        return to_dto(settings)


class ClearCompanyLogoHandler:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._service = CompanyService(bus.session)

    async def handle(self, command: ClearCompanyLogo) -> CompanySettingsDTO:
        settings = await self._service.clear_logo()
        await _record_update(self._bus, command.actor_id, ("logo",))
        return to_dto(settings)


class AllocateInvoiceNumberHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = CompanyService(bus.session)

    async def handle(self, command: AllocateInvoiceNumber) -> str:
        return await self._service.allocate_invoice_number()


class AllocateCustomerNumberHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = CompanyService(bus.session)

    async def handle(self, command: AllocateCustomerNumber) -> str:
        return await self._service.allocate_customer_number()
