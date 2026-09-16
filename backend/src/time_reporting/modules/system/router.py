"""System status/configuration and backups HTTP API — admin only.

Two routers: `router` (`/admin/system/...`) and `backups_router` (`/admin/backups/...`), both from
this one module — see its `CLAUDE.md`.
"""

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse

from time_reporting.api.deps import BusDep
from time_reporting.modules.auth.dependencies import AdminDep
from time_reporting.modules.system.contracts import (
    BackupFailedError,
    BackupInProgressError,
    BackupNotFoundError,
    CreateBackup,
    GetBackupPath,
    GetSystemConfig,
    GetSystemStatus,
    ListBackups,
)
from time_reporting.modules.system.schemas import (
    BackupListResponse,
    BackupResponse,
    SystemConfigResponse,
    SystemStatusResponse,
)

router = APIRouter(prefix="/admin/system", tags=["system"])
backups_router = APIRouter(prefix="/admin/backups", tags=["backups"])


@router.get("/status")
async def get_system_status(
    _admin: AdminDep, bus: BusDep, request: Request
) -> SystemStatusResponse:
    status_dto = await bus.query(GetSystemStatus(started_at=request.app.state.started_at))
    return SystemStatusResponse.model_validate(status_dto)


@router.get("/config")
async def get_system_config(_admin: AdminDep, bus: BusDep) -> SystemConfigResponse:
    config = await bus.query(GetSystemConfig())
    return SystemConfigResponse.model_validate(config)


@backups_router.get("")
async def list_backups(_admin: AdminDep, bus: BusDep) -> BackupListResponse:
    backups = await bus.query(ListBackups())
    return BackupListResponse.model_validate(backups)


@backups_router.post("", status_code=status.HTTP_201_CREATED)
async def create_backup(_admin: AdminDep, bus: BusDep) -> BackupResponse:
    try:
        backup = await bus.execute(CreateBackup())
    except BackupInProgressError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except BackupFailedError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc
    # `only_if_migrations_pending` defaults to False, so a manual backup never comes back `None`.
    assert backup is not None
    return BackupResponse.model_validate(backup)


@backups_router.get("/{name}")
async def download_backup(name: str, _admin: AdminDep, bus: BusDep) -> FileResponse:
    try:
        path = await bus.query(GetBackupPath(name=name))
    except BackupNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return FileResponse(path, filename=name, media_type="application/octet-stream")
