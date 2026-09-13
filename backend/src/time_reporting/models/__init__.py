"""ORM models.

Import every model module here so that ``Base.metadata`` is complete when
Alembic runs autogenerate.
"""

from time_reporting.db.base import Base

__all__ = ["Base"]
