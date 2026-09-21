"""Accounting HTTP API. Every route requires the ``accountant`` level."""

from typing import Annotated

from fastapi import APIRouter, Path
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from time_reporting.api.deps import BusDep
from time_reporting.modules.accounting.contracts import (
    BuildAccountantPackage,
    GetAccountantPackageStatus,
)
from time_reporting.modules.accounting.schemas import AccountantPackageStatusResponse
from time_reporting.modules.auth.dependencies import AccountantDep

router = APIRouter(prefix="/accounting", tags=["accounting"])

Year = Annotated[int, Path(ge=2000, le=2100)]
Month = Annotated[int, Path(ge=1, le=12)]


@router.get("/packages/{year}/{month}")
async def get_accountant_package_status(
    year: Year, month: Month, _accountant: AccountantDep, bus: BusDep
) -> AccountantPackageStatusResponse:
    status_dto = await bus.query(GetAccountantPackageStatus(year=year, month=month))
    return AccountantPackageStatusResponse.model_validate(status_dto)


@router.get("/packages/{year}/{month}.zip")
async def download_accountant_package(
    year: Year, month: Month, current_user: AccountantDep, bus: BusDep
) -> FileResponse:
    package = await bus.query(
        BuildAccountantPackage(year=year, month=month, actor_id=current_user.id)
    )
    return FileResponse(
        package.path,
        filename=package.filename,
        media_type="application/zip",
        background=BackgroundTask(package.path.unlink, missing_ok=True),
    )
