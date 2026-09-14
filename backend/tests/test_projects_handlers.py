from uuid import uuid4

import pytest

from support import CustomerFactory, ProjectFactory, UserFactory
from time_reporting.core.cqrs import Bus
from time_reporting.modules.customers.contracts import UpdateCustomer
from time_reporting.modules.projects.contracts import (
    AddProjectMember,
    CreateProject,
    GetProjectById,
    ListProjectMembers,
    ListProjects,
    MemberUserInactiveError,
    MemberUserNotFoundError,
    ProjectArchivedError,
    ProjectCustomerArchivedError,
    ProjectCustomerNotFoundError,
    ProjectMemberAlreadyExistsError,
    ProjectMemberNotFoundError,
    ProjectNameAlreadyExistsError,
    ProjectNotFoundError,
    RemoveProjectMember,
    UpdateProject,
)
from time_reporting.modules.users.contracts import UpdateUser, UserRole


async def test_create_project_embeds_customer_and_defaults_description(
    bus: Bus, make_customer: CustomerFactory
) -> None:
    customer = await make_customer(name="Acme")

    project = await bus.execute(CreateProject(customer_id=customer.id, name="Website Revamp"))

    assert project.name == "Website Revamp"
    assert project.description is None
    assert project.is_active
    assert project.customer.id == customer.id
    assert project.customer.name == "Acme"
    assert project.customer.is_active is True
    assert await bus.query(GetProjectById(project_id=project.id)) == project


async def test_create_project_for_unknown_customer_raises(bus: Bus) -> None:
    with pytest.raises(ProjectCustomerNotFoundError):
        await bus.execute(CreateProject(customer_id=uuid4(), name="Orphan"))


async def test_create_project_for_archived_customer_raises(
    bus: Bus, make_customer: CustomerFactory
) -> None:
    customer = await make_customer()
    await bus.execute(UpdateCustomer(customer_id=customer.id, is_active=False))

    with pytest.raises(ProjectCustomerArchivedError):
        await bus.execute(CreateProject(customer_id=customer.id, name="Too Late"))


async def test_duplicate_name_per_customer_is_rejected_but_allowed_for_another_customer(
    bus: Bus, make_customer: CustomerFactory, make_project: ProjectFactory
) -> None:
    customer = await make_customer()
    existing = await make_project(customer_id=customer.id, name="Shared Name")

    with pytest.raises(ProjectNameAlreadyExistsError):
        await bus.execute(CreateProject(customer_id=customer.id, name="Shared Name"))

    other_customer = await make_customer()
    other_project = await bus.execute(
        CreateProject(customer_id=other_customer.id, name="Shared Name")
    )

    assert await bus.query(GetProjectById(project_id=existing.id)) == existing
    assert other_project.name == "Shared Name"


async def test_update_project_changes_only_given_fields(
    bus: Bus, make_project: ProjectFactory
) -> None:
    project = await make_project(name="Old Name", description="Original")

    updated = await bus.execute(UpdateProject(project_id=project.id, description="Updated"))

    assert updated.name == "Old Name"
    assert updated.description == "Updated"
    assert updated.updated_at >= project.updated_at


async def test_update_project_clears_description(bus: Bus, make_project: ProjectFactory) -> None:
    project = await make_project(description="Has notes")

    updated = await bus.execute(
        UpdateProject(project_id=project.id, clear_fields=frozenset({"description"}))
    )

    assert updated.description is None


async def test_update_unknown_project_raises(bus: Bus) -> None:
    with pytest.raises(ProjectNotFoundError):
        await bus.execute(UpdateProject(project_id=uuid4(), name="Nobody"))


async def test_rename_to_taken_name_within_same_customer_is_rejected(
    bus: Bus, make_customer: CustomerFactory, make_project: ProjectFactory
) -> None:
    customer = await make_customer()
    await make_project(customer_id=customer.id, name="Taken")
    project = await make_project(customer_id=customer.id)

    with pytest.raises(ProjectNameAlreadyExistsError):
        await bus.execute(UpdateProject(project_id=project.id, name="Taken"))


async def test_reactivating_project_under_archived_customer_is_rejected(
    bus: Bus, make_customer: CustomerFactory, make_project: ProjectFactory
) -> None:
    customer = await make_customer()
    project = await make_project(customer_id=customer.id)
    await bus.execute(UpdateProject(project_id=project.id, is_active=False))
    await bus.execute(UpdateCustomer(customer_id=customer.id, is_active=False))

    with pytest.raises(ProjectCustomerArchivedError):
        await bus.execute(UpdateProject(project_id=project.id, is_active=True))


async def test_archiving_project_does_not_require_active_customer(
    bus: Bus, make_project: ProjectFactory
) -> None:
    project = await make_project()

    archived = await bus.execute(UpdateProject(project_id=project.id, is_active=False))

    assert archived.is_active is False


async def test_list_projects_filters_by_customer_member_search_and_active_status(
    bus: Bus,
    make_customer: CustomerFactory,
    make_project: ProjectFactory,
    make_user: UserFactory,
) -> None:
    customer_a = await make_customer()
    customer_b = await make_customer()
    project_a1 = await make_project(customer_id=customer_a.id, name="Findable Alpha")
    project_a2 = await make_project(customer_id=customer_a.id, name="Other")
    project_b1 = await make_project(customer_id=customer_b.id, name="Findable Beta")
    await bus.execute(UpdateProject(project_id=project_a2.id, is_active=False))

    member = await make_user()
    await bus.execute(AddProjectMember(project_id=project_a1.id, user_id=member.id))

    by_customer = await bus.query(ListProjects(limit=100, offset=0, customer_id=customer_a.id))
    assert {p.id for p in by_customer.items} == {project_a1.id}

    by_customer_incl_inactive = await bus.query(
        ListProjects(limit=100, offset=0, customer_id=customer_a.id, include_inactive=True)
    )
    assert {p.id for p in by_customer_incl_inactive.items} == {project_a1.id, project_a2.id}

    by_member = await bus.query(ListProjects(limit=100, offset=0, member_id=member.id))
    assert {p.id for p in by_member.items} == {project_a1.id}

    by_search = await bus.query(ListProjects(limit=100, offset=0, search="Findable"))
    assert {p.id for p in by_search.items} == {project_a1.id, project_b1.id}

    assert by_customer.limit == 100
    assert by_customer.offset == 0


async def test_add_member_rejects_unknown_or_inactive_user_or_archived_project(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    project = await make_project()

    with pytest.raises(MemberUserNotFoundError):
        await bus.execute(AddProjectMember(project_id=project.id, user_id=uuid4()))

    inactive_user = await make_user()
    admin = await make_user(role=UserRole.ADMIN)
    await bus.execute(
        UpdateUser(user_id=inactive_user.id, acting_user_id=admin.id, is_active=False)
    )
    with pytest.raises(MemberUserInactiveError):
        await bus.execute(AddProjectMember(project_id=project.id, user_id=inactive_user.id))

    archived_project = await make_project()
    await bus.execute(UpdateProject(project_id=archived_project.id, is_active=False))
    active_user = await make_user()
    with pytest.raises(ProjectArchivedError):
        await bus.execute(AddProjectMember(project_id=archived_project.id, user_id=active_user.id))


async def test_add_member_twice_is_rejected(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    project = await make_project()
    user = await make_user()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))

    with pytest.raises(ProjectMemberAlreadyExistsError):
        await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))


async def test_list_members_orders_by_name_and_keeps_deactivated_members(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    project = await make_project()
    zed = await make_user(name="Zed")
    ann = await make_user(name="Ann")
    admin = await make_user(role=UserRole.ADMIN)
    await bus.execute(AddProjectMember(project_id=project.id, user_id=zed.id))
    await bus.execute(AddProjectMember(project_id=project.id, user_id=ann.id))
    await bus.execute(UpdateUser(user_id=zed.id, acting_user_id=admin.id, is_active=False))

    members = await bus.query(ListProjectMembers(project_id=project.id))

    assert [m.user_id for m in members] == [ann.id, zed.id]
    assert next(m for m in members if m.user_id == zed.id).is_active is False


async def test_list_members_of_unknown_project_raises(bus: Bus) -> None:
    with pytest.raises(ProjectNotFoundError):
        await bus.query(ListProjectMembers(project_id=uuid4()))


async def test_remove_member(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    project = await make_project()
    user = await make_user()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))

    await bus.execute(RemoveProjectMember(project_id=project.id, user_id=user.id))

    members = await bus.query(ListProjectMembers(project_id=project.id))
    assert members == ()


async def test_remove_unknown_member_raises(bus: Bus, make_project: ProjectFactory) -> None:
    project = await make_project()

    with pytest.raises(ProjectMemberNotFoundError):
        await bus.execute(RemoveProjectMember(project_id=project.id, user_id=uuid4()))


async def test_remove_member_from_unknown_project_raises(bus: Bus) -> None:
    with pytest.raises(ProjectNotFoundError):
        await bus.execute(RemoveProjectMember(project_id=uuid4(), user_id=uuid4()))
