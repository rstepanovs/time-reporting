"""User ORM entity. Internal to the users module — other modules use ``users.contracts``."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, true
from sqlalchemy.orm import Mapped, mapped_column

from time_reporting.db.base import Base
from time_reporting.db.mixins import TimestampMixin
from time_reporting.modules.users.contracts import UserRole


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    # Always stored normalized (see repository.normalize_email).
    email: Mapped[str] = mapped_column(String(320), unique=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", values_callable=lambda roles: [r.value for r in roles])
    )
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    # Embedded in access tokens; incrementing it invalidates every token issued before.
    token_version: Mapped[int] = mapped_column(default=0, server_default="0")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
