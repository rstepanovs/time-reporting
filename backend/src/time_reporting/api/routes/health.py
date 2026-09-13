"""Liveness and readiness probes."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from time_reporting.api.deps import SessionDep
from time_reporting.schemas.health import HealthStatus

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def liveness() -> HealthStatus:
    return HealthStatus(status="ok")


@router.get(
    "/ready",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Database is unavailable"}},
)
async def readiness(session: SessionDep) -> HealthStatus:
    try:
        await session.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        ) from exc
    return HealthStatus(status="ok")
