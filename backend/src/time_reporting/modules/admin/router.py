"""Admin HTTP API: archive or permanently delete users, customers and projects.

Every route requires an administrator. Archiving customers and projects is still also available
to project managers through the existing ``PATCH`` endpoints in their own routers; this router adds
nothing beyond what an admin can already do except the permanent-delete path.
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from time_reporting.api.deps import BusDep
from time_reporting.modules.admin.contracts import (
    GetCustomerRemovalImpact,
    GetProjectRemovalImpact,
    GetUserRemovalImpact,
    RemovalBlockedError,
    RemovalImpactDTO,
    RemovalTargetNotFoundError,
    RemoveCustomer,
    RemoveProject,
    RemoveUser,
    SelfRemovalError,
)
from time_reporting.modules.admin.schemas import (
    RemovalCountResponse,
    RemovalImpactResponse,
    RemovalResponse,
)
from time_reporting.modules.auth.dependencies import AdminDep

router = APIRouter(prefix="/admin", tags=["admin"])

_NOT_FOUND_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"description": "Record not found"}
}
_BLOCKED_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_409_CONFLICT: {"description": "Referenced by other data; cannot be deleted"}
}
_SELF_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_400_BAD_REQUEST: {"description": "You cannot archive or delete your own account"}
}


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")


def _blocked(exc: RemovalBlockedError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "message": str(exc),
            "blockers": [
                {"kind": blocker.kind.value, "count": blocker.count} for blocker in exc.blockers
            ],
        },
    )


def _self_removal(exc: SelfRemovalError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _impact_response(impact: RemovalImpactDTO | None) -> RemovalImpactResponse:
    if impact is None:
        raise _not_found()
    return RemovalImpactResponse(
        is_active=impact.is_active,
        can_delete_permanently=impact.can_delete_permanently,
        blockers=[RemovalCountResponse.model_validate(b) for b in impact.blockers],
        effects=[RemovalCountResponse.model_validate(e) for e in impact.effects],
    )


@router.get("/users/{user_id}/removal-impact", responses=_NOT_FOUND_RESPONSE)
async def get_user_removal_impact(
    user_id: UUID, admin: AdminDep, bus: BusDep
) -> RemovalImpactResponse:
    impact = await bus.query(GetUserRemovalImpact(user_id=user_id, acting_user_id=admin.id))
    return _impact_response(impact)


@router.delete(
    "/users/{user_id}",
    responses={**_NOT_FOUND_RESPONSE, **_BLOCKED_RESPONSE, **_SELF_RESPONSE},
)
async def remove_user(
    user_id: UUID,
    admin: AdminDep,
    bus: BusDep,
    permanent: Annotated[bool, Query()] = False,
) -> RemovalResponse:
    try:
        outcome = await bus.execute(
            RemoveUser(user_id=user_id, acting_user_id=admin.id, permanent=permanent)
        )
    except RemovalTargetNotFoundError as exc:
        raise _not_found() from exc
    except SelfRemovalError as exc:
        raise _self_removal(exc) from exc
    except RemovalBlockedError as exc:
        raise _blocked(exc) from exc
    return RemovalResponse(outcome=outcome)


@router.get("/customers/{customer_id}/removal-impact", responses=_NOT_FOUND_RESPONSE)
async def get_customer_removal_impact(
    customer_id: UUID, _admin: AdminDep, bus: BusDep
) -> RemovalImpactResponse:
    impact = await bus.query(GetCustomerRemovalImpact(customer_id=customer_id))
    return _impact_response(impact)


@router.delete("/customers/{customer_id}", responses={**_NOT_FOUND_RESPONSE, **_BLOCKED_RESPONSE})
async def remove_customer(
    customer_id: UUID,
    _admin: AdminDep,
    bus: BusDep,
    permanent: Annotated[bool, Query()] = False,
) -> RemovalResponse:
    try:
        outcome = await bus.execute(RemoveCustomer(customer_id=customer_id, permanent=permanent))
    except RemovalTargetNotFoundError as exc:
        raise _not_found() from exc
    except RemovalBlockedError as exc:
        raise _blocked(exc) from exc
    return RemovalResponse(outcome=outcome)


@router.get("/projects/{project_id}/removal-impact", responses=_NOT_FOUND_RESPONSE)
async def get_project_removal_impact(
    project_id: UUID, _admin: AdminDep, bus: BusDep
) -> RemovalImpactResponse:
    impact = await bus.query(GetProjectRemovalImpact(project_id=project_id))
    return _impact_response(impact)


@router.delete("/projects/{project_id}", responses={**_NOT_FOUND_RESPONSE, **_BLOCKED_RESPONSE})
async def remove_project(
    project_id: UUID,
    _admin: AdminDep,
    bus: BusDep,
    permanent: Annotated[bool, Query()] = False,
) -> RemovalResponse:
    try:
        outcome = await bus.execute(RemoveProject(project_id=project_id, permanent=permanent))
    except RemovalTargetNotFoundError as exc:
        raise _not_found() from exc
    except RemovalBlockedError as exc:
        raise _blocked(exc) from exc
    return RemovalResponse(outcome=outcome)
