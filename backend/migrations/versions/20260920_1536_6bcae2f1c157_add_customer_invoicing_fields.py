"""add customer invoicing fields

Revision ID: 6bcae2f1c157
Revises: 9091d3b29f5a
Create Date: 2026-09-20 15:36:01.681510+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6bcae2f1c157"
down_revision: str | Sequence[str] | None = "9091d3b29f5a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "customers", sa.Column("vat_rate", sa.Numeric(precision=5, scale=2), nullable=True)
    )
    op.add_column("customers", sa.Column("vat_note", sa.Text(), nullable=True))
    op.add_column("customers", sa.Column("invoice_locale", sa.String(length=2), nullable=True))
    op.add_column("customers", sa.Column("customer_number", sa.String(length=50), nullable=True))
    op.add_column("customers", sa.Column("your_reference", sa.String(length=255), nullable=True))
    op.create_check_constraint(
        op.f("ck_customers_vat_rate_range"),
        "customers",
        "vat_rate IS NULL OR (vat_rate >= 0 AND vat_rate <= 100)",
    )
    op.create_check_constraint(
        op.f("ck_customers_invoice_locale_valid"),
        "customers",
        "invoice_locale IS NULL OR invoice_locale IN ('sv', 'en')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_customers_invoice_locale_valid"), "customers", type_="check")
    op.drop_constraint(op.f("ck_customers_vat_rate_range"), "customers", type_="check")
    op.drop_column("customers", "your_reference")
    op.drop_column("customers", "customer_number")
    op.drop_column("customers", "invoice_locale")
    op.drop_column("customers", "vat_note")
    op.drop_column("customers", "vat_rate")
