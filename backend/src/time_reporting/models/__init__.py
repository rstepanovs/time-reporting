"""ORM models.

Import every model module here so that ``Base.metadata`` is complete when
Alembic runs autogenerate.
"""

from time_reporting.db.base import Base
from time_reporting.modules.users.models import User

__all__ = ["Base", "User"]
