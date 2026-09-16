"""Raw PostgreSQL catalog queries backing system status. Read-only, no ORM entities — this module
owns no tables of its own."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from time_reporting.modules.system.contracts import TableStatsDTO


class SystemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_server_version(self) -> str:
        result = await self._session.execute(text("SHOW server_version"))
        return str(result.scalar_one())

    async def get_database_size(self) -> int:
        result = await self._session.execute(text("SELECT pg_database_size(current_database())"))
        return int(result.scalar_one())

    async def get_connection_count(self) -> int:
        result = await self._session.execute(
            text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
        )
        return int(result.scalar_one())

    async def get_current_revision(self) -> str | None:
        result = await self._session.execute(text("SELECT version_num FROM alembic_version"))
        return result.scalar_one_or_none()

    async def get_table_stats(self) -> tuple[TableStatsDTO, ...]:
        result = await self._session.execute(
            text("SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY relname")
        )
        return tuple(
            TableStatsDTO(name=row.relname, estimated_rows=row.n_live_tup) for row in result
        )
