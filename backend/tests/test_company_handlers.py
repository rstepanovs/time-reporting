from uuid import UUID

import pytest

from support import UserFactory
from time_reporting.core.cqrs import Bus
from time_reporting.modules.audit.contracts import AuditAction, ListAuditEvents
from time_reporting.modules.company.contracts import (
    AllocateCustomerNumber,
    AllocateInvoiceNumber,
    ClearCompanyLogo,
    CompanyAddressDTO,
    CompanyLogoTooLargeError,
    CompanyLogoTypeNotAllowedError,
    GetCompanyLogo,
    GetCompanySettings,
    InvalidInvoiceLocaleError,
    SetCompanyLogo,
    UpdateCompanySettings,
)
from time_reporting.modules.company.service import CompanyService

_SVG_LOGO = b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"

_ADDRESS = CompanyAddressDTO(
    street="1 Main Street", street2=None, postal_code="123 45", city="Lund", country="se"
)


def _update(
    actor_id: UUID,
    *,
    default_invoice_locale: str = "sv",
    invoice_number_prefix: str = "",
    next_invoice_number: int = 1,
    customer_number_prefix: str = "",
    next_customer_number: int = 1,
) -> UpdateCompanySettings:
    return UpdateCompanySettings(
        actor_id=actor_id,
        legal_name="Belt & Braces Software AB",
        org_number="556677-8899",
        vat_number="SE556677889901",
        address=_ADDRESS,
        email="info@example.se",
        phone="070-000 00 00",
        registered_office="Lund",
        bankgiro="123-4567",
        iban="",
        bic="",
        f_tax_approved=True,
        default_invoice_locale=default_invoice_locale,
        late_interest="8.00 %",
        invoice_number_prefix=invoice_number_prefix,
        customer_number_prefix=customer_number_prefix,
        next_customer_number=next_customer_number,
        next_invoice_number=next_invoice_number,
        allow_self_review=False,
    )


async def test_default_settings_are_blank(bus: Bus) -> None:
    settings = await bus.query(GetCompanySettings())

    assert settings.legal_name == ""
    assert settings.address.country == ""
    assert settings.default_invoice_locale == "sv"
    assert settings.invoice_number_prefix == ""
    assert settings.next_invoice_number == 1
    assert settings.customer_number_prefix == ""
    assert settings.next_customer_number == 1
    assert settings.allow_self_review is False
    assert settings.has_logo is False


async def test_update_settings_replaces_the_row_and_audits_changed_fields(
    bus: Bus, make_user: UserFactory
) -> None:
    admin = await make_user()

    updated = await bus.execute(_update(admin.id))

    assert updated.legal_name == "Belt & Braces Software AB"
    assert updated.address.country == "SE"
    assert updated.f_tax_approved is True

    events = await bus.query(
        ListAuditEvents(
            limit=10, offset=0, action=AuditAction.COMPANY_UPDATED, entity_type="company"
        )
    )
    assert len(events.items) == 1
    event = events.items[0]
    assert event.actor_id == admin.id
    assert event.details is not None
    assert "legal_name" in event.details["fields"]
    assert "address" in event.details["fields"]


async def test_update_settings_with_no_changes_does_not_audit(
    bus: Bus, make_user: UserFactory
) -> None:
    admin = await make_user()
    await bus.execute(_update(admin.id))

    await bus.execute(_update(admin.id))

    events = await bus.query(
        ListAuditEvents(
            limit=10, offset=0, action=AuditAction.COMPANY_UPDATED, entity_type="company"
        )
    )
    assert len(events.items) == 1


async def test_update_settings_rejects_unknown_locale(bus: Bus, make_user: UserFactory) -> None:
    admin = await make_user()

    with pytest.raises(InvalidInvoiceLocaleError):
        await bus.execute(_update(admin.id, default_invoice_locale="xx"))


async def test_set_and_clear_logo(bus: Bus, make_user: UserFactory) -> None:
    admin = await make_user()

    updated = await bus.execute(
        SetCompanyLogo(actor_id=admin.id, content_type="image/svg+xml", content=_SVG_LOGO)
    )
    assert updated.has_logo is True

    logo = await bus.query(GetCompanyLogo())
    assert logo is not None
    assert logo.content == _SVG_LOGO
    assert logo.content_type == "image/svg+xml"

    cleared = await bus.execute(ClearCompanyLogo(actor_id=admin.id))
    assert cleared.has_logo is False
    assert await bus.query(GetCompanyLogo()) is None

    events = await bus.query(
        ListAuditEvents(
            limit=10, offset=0, action=AuditAction.COMPANY_UPDATED, entity_type="company"
        )
    )
    fields = [event.details["fields"] for event in events.items if event.details is not None]
    assert fields == [["logo"], ["logo"]]


async def test_set_logo_rejects_disallowed_type(bus: Bus, make_user: UserFactory) -> None:
    admin = await make_user()

    with pytest.raises(CompanyLogoTypeNotAllowedError):
        await bus.execute(
            SetCompanyLogo(actor_id=admin.id, content_type="application/pdf", content=b"%PDF")
        )


async def test_set_logo_rejects_oversize(bus: Bus, make_user: UserFactory) -> None:
    admin = await make_user()

    with pytest.raises(CompanyLogoTooLargeError):
        await bus.execute(
            SetCompanyLogo(
                actor_id=admin.id,
                content_type="image/png",
                content=b"\x00" * (512 * 1024 + 1),
            )
        )


async def test_allocate_invoice_number_is_consecutive(bus: Bus, make_user: UserFactory) -> None:
    admin = await make_user()
    await bus.execute(_update(admin.id, invoice_number_prefix="INV-", next_invoice_number=41))

    first = await bus.execute(AllocateInvoiceNumber())
    second = await bus.execute(AllocateInvoiceNumber())

    assert (first, second) == ("INV-41", "INV-42")


async def test_allocation_rolled_back_does_not_burn_a_number(bus: Bus) -> None:
    service = CompanyService(bus.session)

    with pytest.raises(RuntimeError):
        async with bus.session.begin_nested():
            await service.allocate_invoice_number()
            raise RuntimeError("boom")

    number = await bus.execute(AllocateInvoiceNumber())
    assert number == "1"


async def test_allocate_customer_number_is_consecutive(bus: Bus, make_user: UserFactory) -> None:
    admin = await make_user()
    await bus.execute(_update(admin.id, customer_number_prefix="CUST-", next_customer_number=41))

    first = await bus.execute(AllocateCustomerNumber())
    second = await bus.execute(AllocateCustomerNumber())

    assert (first, second) == ("CUST-41", "CUST-42")


async def test_customer_number_allocation_rolled_back_does_not_burn_a_number(bus: Bus) -> None:
    service = CompanyService(bus.session)

    with pytest.raises(RuntimeError):
        async with bus.session.begin_nested():
            await service.allocate_customer_number()
            raise RuntimeError("boom")

    number = await bus.execute(AllocateCustomerNumber())
    assert number == "1"
