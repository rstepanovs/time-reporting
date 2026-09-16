"""Replace users.role with a roles array

Revision ID: 635a2361699d
Revises: b749088f080a
Create Date: 2026-09-15 23:04:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "635a2361699d"
down_revision: str | Sequence[str] | None = "b749088f080a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Hand-written: autogenerate can't express "enum column -> array of a differently-valued enum".
# The old `user_role` type (admin/project_manager/worker) is dropped and a new one (admin/manager/
# accountant) takes its name, so the ORM's `Enum(UserRole, name="user_role")` needs no code-side
# distinction between the two.
_NEW_ROLE_VALUES = ("admin", "manager", "accountant")
_OLD_ROLE_VALUES = ("admin", "project_manager", "worker")


def _enum_literal(values: Sequence[str]) -> str:
    return "(" + ", ".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
    op.execute(f"CREATE TYPE user_role_new AS ENUM {_enum_literal(_NEW_ROLE_VALUES)}")
    op.add_column(
        "users",
        sa.Column(
            "roles",
            postgresql.ARRAY(
                postgresql.ENUM(*_NEW_ROLE_VALUES, name="user_role_new", create_type=False)
            ),
            nullable=False,
            server_default=sa.text("'{}'::user_role_new[]"),
        ),
    )
    op.execute(
        """
        UPDATE users
        SET roles = CASE role::text
            WHEN 'admin' THEN ARRAY['admin', 'manager']::user_role_new[]
            WHEN 'project_manager' THEN ARRAY['manager']::user_role_new[]
            ELSE ARRAY[]::user_role_new[]
        END
        """
    )
    op.drop_column("users", "role")
    op.execute("DROP TYPE user_role")
    op.execute("ALTER TYPE user_role_new RENAME TO user_role")


def downgrade() -> None:
    op.execute(f"CREATE TYPE user_role_old AS ENUM {_enum_literal(_OLD_ROLE_VALUES)}")
    op.add_column(
        "users",
        sa.Column(
            "role",
            postgresql.ENUM(*_OLD_ROLE_VALUES, name="user_role_old", create_type=False),
            nullable=True,
        ),
    )
    op.execute(
        """
        UPDATE users
        SET role = (CASE
            WHEN 'admin' = ANY(roles) THEN 'admin'
            WHEN 'manager' = ANY(roles) THEN 'project_manager'
            ELSE 'worker'
        END)::user_role_old
        """
    )
    op.alter_column("users", "role", nullable=False)
    op.drop_column("users", "roles")
    op.execute("DROP TYPE user_role")
    op.execute("ALTER TYPE user_role_old RENAME TO user_role")
