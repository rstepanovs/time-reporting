"""add customer number counter to company settings

Revision ID: c74b2ff851ad
Revises: 89e6d37b2498
Create Date: 2026-09-22 15:11:15.012324+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c74b2ff851ad"
down_revision: str | Sequence[str] | None = "89e6d37b2498"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "company_settings",
        sa.Column(
            "customer_number_prefix", sa.String(length=20), server_default="", nullable=False
        ),
    )
    op.add_column(
        "company_settings",
        sa.Column("next_customer_number", sa.Integer(), server_default="1", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_company_settings_next_customer_number_positive"),
        "company_settings",
        "next_customer_number > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_company_settings_next_customer_number_positive"),
        "company_settings",
        type_="check",
    )
    op.drop_column("company_settings", "next_customer_number")
    op.drop_column("company_settings", "customer_number_prefix")
