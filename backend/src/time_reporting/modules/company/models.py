"""CompanySettings ORM entity, internal to the module — other modules use ``company.contracts``.

A singleton: ``id`` is fixed to ``SINGLETON_ID`` and a check constraint enforces it, so a second
row can never be inserted (its primary key would collide). The migration inserts the one row with
placeholder values; there is no create/delete path in the service, only read/update.
"""

from sqlalchemy import CheckConstraint, LargeBinary, String, false
from sqlalchemy.orm import Mapped, mapped_column

from time_reporting.db.base import Base
from time_reporting.db.mixins import TimestampMixin

SINGLETON_ID = 1


class CompanySettings(TimestampMixin, Base):
    __tablename__ = "company_settings"
    __table_args__ = (
        CheckConstraint(f"id = {SINGLETON_ID}", name="company_settings_singleton"),
        CheckConstraint("next_invoice_number > 0", name="next_invoice_number_positive"),
        CheckConstraint(
            "default_invoice_locale IN ('sv', 'en')", name="default_invoice_locale_valid"
        ),
        CheckConstraint(
            "logo_content_type IS NULL OR logo_content_type IN "
            "('image/svg+xml', 'image/png', 'image/jpeg')",
            name="logo_content_type_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, default=SINGLETON_ID)
    legal_name: Mapped[str] = mapped_column(String(255), default="", server_default="")
    org_number: Mapped[str] = mapped_column(String(64), default="", server_default="")
    vat_number: Mapped[str] = mapped_column(String(64), default="", server_default="")

    # Address; the country is stored as an upper-case ISO 3166-1 alpha-2 code, "" until set.
    address_street: Mapped[str] = mapped_column(String(255), default="", server_default="")
    address_street2: Mapped[str | None] = mapped_column(String(255))
    address_postal_code: Mapped[str] = mapped_column(String(32), default="", server_default="")
    address_city: Mapped[str] = mapped_column(String(255), default="", server_default="")
    address_country: Mapped[str] = mapped_column(String(2), default="", server_default="")

    email: Mapped[str] = mapped_column(String(320), default="", server_default="")
    phone: Mapped[str] = mapped_column(String(64), default="", server_default="")
    registered_office: Mapped[str] = mapped_column(String(255), default="", server_default="")

    bankgiro: Mapped[str] = mapped_column(String(64), default="", server_default="")
    iban: Mapped[str] = mapped_column(String(64), default="", server_default="")
    bic: Mapped[str] = mapped_column(String(64), default="", server_default="")
    f_tax_approved: Mapped[bool] = mapped_column(default=False, server_default=false())

    # "sv" or "en" (see company.contracts.INVOICE_LOCALES).
    default_invoice_locale: Mapped[str] = mapped_column(
        String(2), default="sv", server_default="sv"
    )
    late_interest: Mapped[str] = mapped_column(String(255), default="", server_default="")

    invoice_number_prefix: Mapped[str] = mapped_column(String(20), default="", server_default="")
    next_invoice_number: Mapped[int] = mapped_column(default=1, server_default="1")

    # Lets a one-person company review and approve its own timesheet weeks/expense reports —
    # see timesheets.CLAUDE.md / expenses.CLAUDE.md for where this is read. Off by default: any
    # other company keeps today's "nobody reviews their own work" rule.
    allow_self_review: Mapped[bool] = mapped_column(default=False, server_default=false())

    # Stored as bytea, so `pg_dump` backups already cover it — no new Docker volume. Size and
    # content type are validated in CompanyService, not by a database constraint (mirrors
    # expenses.ExpenseAttachment, which validates size the same way).
    logo: Mapped[bytes | None] = mapped_column(LargeBinary)
    logo_content_type: Mapped[str | None] = mapped_column(String(50))
