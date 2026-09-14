"""Project ORM entities, internal to the module — other modules use ``projects.contracts``."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func, true
from sqlalchemy.orm import Mapped, mapped_column

from time_reporting.db.base import Base
from time_reporting.db.mixins import TimestampMixin, utc_now


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("customer_id", "name", name="uq_projects_customer_id_name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Immutable after creation; referenced by table name, never by importing customers.models.
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    # Archived by default (billing data will reference projects); the admin module can permanently
    # delete one that nothing references yet.
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())


class ProjectMember(Base):
    """A user added to a project. A plain link with no per-project role."""

    __tablename__ = "project_members"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
