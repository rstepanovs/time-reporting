"""Shared FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from time_reporting.core.cqrs import Bus, HandlerRegistry
from time_reporting.db.session import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_bus(request: Request, session: SessionDep) -> Bus:
    registry: HandlerRegistry = request.app.state.handlers
    return Bus(registry, session)


BusDep = Annotated[Bus, Depends(get_bus)]
