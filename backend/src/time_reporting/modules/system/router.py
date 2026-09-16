"""System status and configuration HTTP API — admin only."""

from fastapi import APIRouter, Request

from time_reporting.api.deps import BusDep
from time_reporting.modules.auth.dependencies import AdminDep
from time_reporting.modules.system.contracts import GetSystemConfig, GetSystemStatus
from time_reporting.modules.system.schemas import SystemConfigResponse, SystemStatusResponse

router = APIRouter(prefix="/admin/system", tags=["system"])


@router.get("/status")
async def get_system_status(
    _admin: AdminDep, bus: BusDep, request: Request
) -> SystemStatusResponse:
    status = await bus.query(GetSystemStatus(started_at=request.app.state.started_at))
    return SystemStatusResponse.model_validate(status)


@router.get("/config")
async def get_system_config(_admin: AdminDep, bus: BusDep) -> SystemConfigResponse:
    config = await bus.query(GetSystemConfig())
    return SystemConfigResponse.model_validate(config)
