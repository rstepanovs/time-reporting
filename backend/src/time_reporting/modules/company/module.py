"""Registers the company module's handlers on the bus."""

from time_reporting.core.cqrs import HandlerRegistry
from time_reporting.modules.company.contracts import (
    AllocateCustomerNumber,
    AllocateInvoiceNumber,
    ClearCompanyLogo,
    GetCompanyLogo,
    GetCompanySettings,
    SetCompanyLogo,
    UpdateCompanySettings,
)
from time_reporting.modules.company.handlers import (
    AllocateCustomerNumberHandler,
    AllocateInvoiceNumberHandler,
    ClearCompanyLogoHandler,
    GetCompanyLogoHandler,
    GetCompanySettingsHandler,
    SetCompanyLogoHandler,
    UpdateCompanySettingsHandler,
)


def register(registry: HandlerRegistry) -> None:
    registry.query(GetCompanySettings, GetCompanySettingsHandler)
    registry.query(GetCompanyLogo, GetCompanyLogoHandler)

    registry.command(UpdateCompanySettings, UpdateCompanySettingsHandler)
    registry.command(SetCompanyLogo, SetCompanyLogoHandler)
    registry.command(ClearCompanyLogo, ClearCompanyLogoHandler)
    registry.command(AllocateInvoiceNumber, AllocateInvoiceNumberHandler)
    registry.command(AllocateCustomerNumber, AllocateCustomerNumberHandler)
