"""Projects HTTP API: readable by any authenticated user, writable by managers."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from time_reporting.api.deps import BusDep
from time_reporting.modules.auth.dependencies import AdminDep, CurrentUserDep, ManagerDep
from time_reporting.modules.projects.contracts import (
    CLEARABLE_BILLING_ITEM_FIELDS,
    CLEARABLE_PROJECT_FIELDS,
    AddProjectBillingItem,
    AddProjectMember,
    BillingItemInUseError,
    BillingItemNameAlreadyExistsError,
    BillingItemNotFoundError,
    BillingItemPricingError,
    CreateProject,
    DeleteProjectBillingItem,
    GetProjectById,
    ListProjectBillingItems,
    ListProjectMembers,
    ListProjects,
    MemberUserInactiveError,
    MemberUserNotFoundError,
    ProjectArchivedError,
    ProjectCustomerArchivedError,
    ProjectCustomerNotFoundError,
    ProjectManagerNotEligibleError,
    ProjectManagerNotFoundError,
    ProjectMemberAlreadyExistsError,
    ProjectMemberNotFoundError,
    ProjectNameAlreadyExistsError,
    ProjectNotFoundError,
    RemoveProjectMember,
    UpdateProject,
    UpdateProjectBillingItem,
)
from time_reporting.modules.projects.schemas import (
    BillingItemCreateRequest,
    BillingItemUpdateRequest,
    ProjectBillingItemResponse,
    ProjectCreateRequest,
    ProjectMemberAddRequest,
    ProjectMemberResponse,
    ProjectPageResponse,
    ProjectResponse,
    ProjectUpdateRequest,
)

router = APIRouter(prefix="/projects", tags=["projects"])

_NOT_FOUND_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"description": "Project not found"}
}
_NAME_CONFLICT_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_409_CONFLICT: {"description": "A project with this name already exists"}
}
_CUSTOMER_RULE_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_400_BAD_REQUEST: {"description": "The customer does not exist or is archived"}
}
_MANAGER_RULE_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_400_BAD_REQUEST: {
        "description": "The manager does not exist, is inactive, or is not an admin/project manager"
    }
}
_BILLING_ITEM_NAME_CONFLICT_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_409_CONFLICT: {"description": "A billing item with this name already exists"}
}


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


def _billing_item_not_found(exc: BillingItemNotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _name_conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


@router.get("")
async def list_projects(
    _user: CurrentUserDep,
    bus: BusDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    include_inactive: bool = False,
    customer_id: UUID | None = None,
    member_id: UUID | None = None,
    manager_id: UUID | None = None,
    search: Annotated[str | None, Query(max_length=255)] = None,
) -> ProjectPageResponse:
    page = await bus.query(
        ListProjects(
            limit=limit,
            offset=offset,
            include_inactive=include_inactive,
            customer_id=customer_id,
            member_id=member_id,
            manager_id=manager_id,
            search=search,
        )
    )
    return ProjectPageResponse.model_validate(page)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={**_NAME_CONFLICT_RESPONSE, **_CUSTOMER_RULE_RESPONSE, **_MANAGER_RULE_RESPONSE},
)
async def create_project(
    body: ProjectCreateRequest, _manager: ManagerDep, bus: BusDep
) -> ProjectResponse:
    try:
        project = await bus.execute(
            CreateProject(
                customer_id=body.customer_id,
                name=body.name,
                description=body.description,
                normal_working_hours=body.normal_working_hours,
                manager_id=body.manager_id,
            )
        )
    except (ProjectCustomerNotFoundError, ProjectCustomerArchivedError) as exc:
        raise _bad_request(str(exc)) from exc
    except (ProjectManagerNotFoundError, ProjectManagerNotEligibleError) as exc:
        raise _bad_request(str(exc)) from exc
    except ProjectNameAlreadyExistsError as exc:
        raise _name_conflict(str(exc)) from exc
    return ProjectResponse.model_validate(project)


@router.get("/{project_id}", responses=_NOT_FOUND_RESPONSE)
async def read_project(project_id: UUID, _user: CurrentUserDep, bus: BusDep) -> ProjectResponse:
    project = await bus.query(GetProjectById(project_id=project_id))
    if project is None:
        raise _not_found()
    return ProjectResponse.model_validate(project)


@router.patch(
    "/{project_id}",
    responses={
        **_NOT_FOUND_RESPONSE,
        **_NAME_CONFLICT_RESPONSE,
        **_CUSTOMER_RULE_RESPONSE,
        **_MANAGER_RULE_RESPONSE,
    },
)
async def update_project(
    project_id: UUID, body: ProjectUpdateRequest, _manager: ManagerDep, bus: BusDep
) -> ProjectResponse:
    clear_fields = frozenset(
        name
        for name in CLEARABLE_PROJECT_FIELDS
        if name in body.model_fields_set and getattr(body, name) is None
    )
    try:
        project = await bus.execute(
            UpdateProject(
                project_id=project_id,
                name=body.name,
                description=body.description,
                is_active=body.is_active,
                normal_working_hours=body.normal_working_hours,
                manager_id=body.manager_id,
                clear_fields=clear_fields,
            )
        )
    except ProjectNotFoundError as exc:
        raise _not_found() from exc
    except ProjectNameAlreadyExistsError as exc:
        raise _name_conflict(str(exc)) from exc
    except ProjectCustomerArchivedError as exc:
        raise _bad_request(str(exc)) from exc
    except (ProjectManagerNotFoundError, ProjectManagerNotEligibleError) as exc:
        raise _bad_request(str(exc)) from exc
    return ProjectResponse.model_validate(project)


@router.get("/{project_id}/members", responses=_NOT_FOUND_RESPONSE)
async def list_project_members(
    project_id: UUID, _user: CurrentUserDep, bus: BusDep
) -> list[ProjectMemberResponse]:
    try:
        members = await bus.query(ListProjectMembers(project_id=project_id))
    except ProjectNotFoundError as exc:
        raise _not_found() from exc
    return [ProjectMemberResponse.model_validate(member) for member in members]


@router.post(
    "/{project_id}/members",
    status_code=status.HTTP_201_CREATED,
    responses={
        **_NOT_FOUND_RESPONSE,
        status.HTTP_400_BAD_REQUEST: {
            "description": "The user does not exist, is inactive, or the project is archived"
        },
        status.HTTP_409_CONFLICT: {"description": "The user is already a member of this project"},
    },
)
async def add_project_member(
    project_id: UUID, body: ProjectMemberAddRequest, _manager: ManagerDep, bus: BusDep
) -> ProjectMemberResponse:
    try:
        member = await bus.execute(AddProjectMember(project_id=project_id, user_id=body.user_id))
    except ProjectNotFoundError as exc:
        raise _not_found() from exc
    except (MemberUserNotFoundError, MemberUserInactiveError, ProjectArchivedError) as exc:
        raise _bad_request(str(exc)) from exc
    except ProjectMemberAlreadyExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return ProjectMemberResponse.model_validate(member)


@router.delete(
    "/{project_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Project not found, or the user is not a member"}
    },
)
async def remove_project_member(
    project_id: UUID, user_id: UUID, _manager: ManagerDep, bus: BusDep
) -> None:
    try:
        await bus.execute(RemoveProjectMember(project_id=project_id, user_id=user_id))
    except (ProjectNotFoundError, ProjectMemberNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{project_id}/billing-items", responses=_NOT_FOUND_RESPONSE)
async def list_project_billing_items(
    project_id: UUID,
    _user: CurrentUserDep,
    bus: BusDep,
    include_inactive: bool = False,
) -> list[ProjectBillingItemResponse]:
    try:
        items = await bus.query(
            ListProjectBillingItems(project_id=project_id, include_inactive=include_inactive)
        )
    except ProjectNotFoundError as exc:
        raise _not_found() from exc
    return [ProjectBillingItemResponse.model_validate(item) for item in items]


@router.post(
    "/{project_id}/billing-items",
    status_code=status.HTTP_201_CREATED,
    responses={
        **_NOT_FOUND_RESPONSE,
        **_BILLING_ITEM_NAME_CONFLICT_RESPONSE,
        status.HTTP_400_BAD_REQUEST: {
            "description": "The project is archived, or the pricing doesn't match the unit"
        },
    },
)
async def add_project_billing_item(
    project_id: UUID, body: BillingItemCreateRequest, _manager: ManagerDep, bus: BusDep
) -> ProjectBillingItemResponse:
    try:
        item = await bus.execute(
            AddProjectBillingItem(
                project_id=project_id,
                name=body.name,
                unit=body.unit,
                description=body.description,
                unit_rate=body.unit_rate,
                markup_percent=body.markup_percent,
            )
        )
    except ProjectNotFoundError as exc:
        raise _not_found() from exc
    except (ProjectArchivedError, BillingItemPricingError) as exc:
        raise _bad_request(str(exc)) from exc
    except BillingItemNameAlreadyExistsError as exc:
        raise _name_conflict(str(exc)) from exc
    return ProjectBillingItemResponse.model_validate(item)


@router.patch(
    "/{project_id}/billing-items/{item_id}",
    responses={
        **_NOT_FOUND_RESPONSE,
        **_BILLING_ITEM_NAME_CONFLICT_RESPONSE,
        status.HTTP_400_BAD_REQUEST: {
            "description": "The pricing doesn't match the unit, or the project is archived"
        },
    },
)
async def update_project_billing_item(
    project_id: UUID,
    item_id: UUID,
    body: BillingItemUpdateRequest,
    _manager: ManagerDep,
    bus: BusDep,
) -> ProjectBillingItemResponse:
    clear_fields = frozenset(
        name
        for name in CLEARABLE_BILLING_ITEM_FIELDS
        if name in body.model_fields_set and getattr(body, name) is None
    )
    try:
        item = await bus.execute(
            UpdateProjectBillingItem(
                project_id=project_id,
                item_id=item_id,
                name=body.name,
                description=body.description,
                unit_rate=body.unit_rate,
                markup_percent=body.markup_percent,
                is_active=body.is_active,
                clear_fields=clear_fields,
            )
        )
    except ProjectNotFoundError as exc:
        raise _not_found() from exc
    except BillingItemNotFoundError as exc:
        raise _billing_item_not_found(exc) from exc
    except (ProjectArchivedError, BillingItemPricingError) as exc:
        raise _bad_request(str(exc)) from exc
    except BillingItemNameAlreadyExistsError as exc:
        raise _name_conflict(str(exc)) from exc
    return ProjectBillingItemResponse.model_validate(item)


@router.delete(
    "/{project_id}/billing-items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        **_NOT_FOUND_RESPONSE,
        status.HTTP_409_CONFLICT: {
            "description": "The billing item is referenced by other data and cannot be deleted"
        },
    },
)
async def delete_project_billing_item(
    project_id: UUID, item_id: UUID, _admin: AdminDep, bus: BusDep
) -> None:
    try:
        await bus.execute(DeleteProjectBillingItem(project_id=project_id, item_id=item_id))
    except ProjectNotFoundError as exc:
        raise _not_found() from exc
    except BillingItemNotFoundError as exc:
        raise _billing_item_not_found(exc) from exc
    except BillingItemInUseError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
