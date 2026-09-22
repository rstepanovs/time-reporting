"""Persistence of the singleton ``CompanySettings`` row. Flushes but never commits — the bus owns
transactions."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from time_reporting.modules.company.models import SINGLETON_ID, CompanySettings


class CompanyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self) -> CompanySettings:
        """The migration guarantees exactly one row; there is no "not found" case."""
        result = await self._session.execute(
            select(CompanySettings).where(CompanySettings.id == SINGLETON_ID)
        )
        return result.scalar_one()

    async def get_for_update(self) -> CompanySettings:
        """Locks the row (``SELECT ... FOR UPDATE``) so concurrent invoice-number allocations
        serialize instead of racing."""
        result = await self._session.execute(
            select(CompanySettings).where(CompanySettings.id == SINGLETON_ID).with_for_update()
        )
        return result.scalar_one()

    async def save(self, settings: CompanySettings) -> None:
        self._session.add(settings)
        await self._session.flush()
