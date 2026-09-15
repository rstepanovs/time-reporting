from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from support import CustomerFactory, ProjectFactory, UserFactory
from time_reporting.core.cqrs import Bus
from time_reporting.modules.customers.contracts import UpdateCustomer
from time_reporting.modules.projects.contracts import (
    DEFAULT_BILLING_ITEMS,
    AddProjectBillingItem,
    AddProjectMember,
    BillingItemNameAlreadyExistsError,
    BillingItemNotFoundError,
    BillingItemPricingError,
    BillingUnit,
    CreateProject,
    DeleteProject,
    DeleteProjectBillingItem,
    GetProjectBillingItemsByIds,
    GetProjectById,
    GetProjectsByIds,
    ListManagedProjectsWithMembers,
    ListMemberProjectsWithBillingItems,
    ListProjectBillingItems,
    ListProjectMembers,
    ListProjects,
    MemberUserInactiveError,
    MemberUserNotFoundError,
    ProjectArchivedError,
    ProjectBillingItemDTO,
    ProjectCustomerArchivedError,
    ProjectCustomerNotFoundError,
    ProjectManagerNotEligibleError,
    ProjectManagerNotFoundError,
    ProjectMemberAlreadyExistsError,
    ProjectMemberNotFoundError,
    ProjectNameAlreadyExistsError,
    ProjectNotFoundError,
    RemoveProjectMember,
    RemoveUserFromAllProjects,
    UpdateProject,
    UpdateProjectBillingItem,
)
from time_reporting.modules.projects.models import ProjectBillingItem
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


async def _billing_items(session: AsyncSession, project_id: UUID) -> list[ProjectBillingItem]:
    result = await session.scalars(
        select(ProjectBillingItem)
        .where(ProjectBillingItem.project_id == project_id)
        .order_by(ProjectBillingItem.position)
    )
    return list(result.all())


async def test_create_project_adds_default_billing_items_without_rates(
    bus: Bus, db_session: AsyncSession, make_customer: CustomerFactory
) -> None:
    customer = await make_customer()

    project = await bus.execute(CreateProject(customer_id=customer.id, name="With Defaults"))

    items = await _billing_items(db_session, project.id)
    assert [(item.position, item.preset, item.name, item.unit) for item in items] == [
        (position, default.preset, default.name, default.unit)
        for position, default in enumerate(DEFAULT_BILLING_ITEMS, start=1)
    ]
    assert all(item.unit_rate is None and item.markup_percent is None for item in items)
    assert all(item.is_active for item in items)


async def test_billing_item_pricing_must_match_its_unit_in_the_database(
    db_session: AsyncSession, make_project: ProjectFactory
) -> None:
    project = await make_project()
    expense = (await _billing_items(db_session, project.id))[-1]

    expense.unit_rate = Decimal("10.00")

    with pytest.raises(IntegrityError, match="unit_rate_not_for_amount"):
        await db_session.flush()


async def test_create_project_defaults_normal_working_hours_to_eight(
    bus: Bus, make_customer: CustomerFactory
) -> None:
    customer = await make_customer()

    project = await bus.execute(CreateProject(customer_id=customer.id, name="Default Hours"))

    assert project.normal_working_hours == Decimal("8")


async def test_create_project_accepts_custom_normal_working_hours(
    bus: Bus, make_customer: CustomerFactory
) -> None:
    customer = await make_customer()

    project = await bus.execute(
        CreateProject(
            customer_id=customer.id, name="Part Time", normal_working_hours=Decimal("4.5")
        )
    )

    assert project.normal_working_hours == Decimal("4.50")


async def test_update_project_changes_normal_working_hours(
    bus: Bus, make_project: ProjectFactory
) -> None:
    project = await make_project()

    updated = await bus.execute(
        UpdateProject(project_id=project.id, normal_working_hours=Decimal("6"))
    )

    assert updated.normal_working_hours == Decimal("6.00")


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


# --- Project manager ---


async def test_create_project_with_manager_embeds_manager(
    bus: Bus, make_customer: CustomerFactory, make_user: UserFactory
) -> None:
    manager = await make_user(role=UserRole.PROJECT_MANAGER, name="Mark Manager")
    customer = await make_customer()

    project = await bus.execute(
        CreateProject(customer_id=customer.id, name="Managed", manager_id=manager.id)
    )

    assert project.manager is not None
    assert project.manager.id == manager.id
    assert project.manager.name == "Mark Manager"


async def test_create_project_manager_must_exist(bus: Bus, make_customer: CustomerFactory) -> None:
    customer = await make_customer()

    with pytest.raises(ProjectManagerNotFoundError):
        await bus.execute(CreateProject(customer_id=customer.id, name="X", manager_id=uuid4()))


async def test_create_project_rejects_worker_as_manager(
    bus: Bus, make_customer: CustomerFactory, make_user: UserFactory
) -> None:
    worker = await make_user(role=UserRole.WORKER)
    customer = await make_customer()

    with pytest.raises(ProjectManagerNotEligibleError):
        await bus.execute(CreateProject(customer_id=customer.id, name="X", manager_id=worker.id))


async def test_create_project_rejects_inactive_manager(
    bus: Bus, make_customer: CustomerFactory, make_user: UserFactory
) -> None:
    admin = await make_user(role=UserRole.ADMIN)
    manager = await make_user(role=UserRole.PROJECT_MANAGER)
    await bus.execute(UpdateUser(user_id=manager.id, acting_user_id=admin.id, is_active=False))
    customer = await make_customer()

    with pytest.raises(ProjectManagerNotEligibleError):
        await bus.execute(CreateProject(customer_id=customer.id, name="X", manager_id=manager.id))


async def test_update_project_assigns_and_clears_manager(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    project = await make_project()
    manager = await make_user(role=UserRole.ADMIN)

    assigned = await bus.execute(UpdateProject(project_id=project.id, manager_id=manager.id))
    assert assigned.manager is not None
    assert assigned.manager.id == manager.id

    cleared = await bus.execute(
        UpdateProject(project_id=project.id, clear_fields=frozenset({"manager_id"}))
    )
    assert cleared.manager is None


async def test_update_project_rejects_ineligible_manager(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    project = await make_project()
    worker = await make_user(role=UserRole.WORKER)

    with pytest.raises(ProjectManagerNotEligibleError):
        await bus.execute(UpdateProject(project_id=project.id, manager_id=worker.id))


async def test_list_projects_filters_by_manager(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    manager = await make_user(role=UserRole.PROJECT_MANAGER)
    managed = await make_project(manager_id=manager.id)
    await make_project()

    page = await bus.query(ListProjects(limit=100, offset=0, manager_id=manager.id))

    assert {p.id for p in page.items} == {managed.id}


async def test_remove_user_from_all_projects_clears_manager_assignment(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    manager = await make_user(role=UserRole.PROJECT_MANAGER)
    project = await make_project(manager_id=manager.id)

    await bus.execute(RemoveUserFromAllProjects(user_id=manager.id))

    refreshed = await bus.query(GetProjectById(project_id=project.id))
    assert refreshed is not None
    assert refreshed.manager is None


# --- Managed projects with members ---


async def test_list_managed_projects_with_members_filters_by_manager(
    bus: Bus,
    make_customer: CustomerFactory,
    make_project: ProjectFactory,
    make_user: UserFactory,
) -> None:
    manager = await make_user(role=UserRole.PROJECT_MANAGER)
    other_manager = await make_user(role=UserRole.PROJECT_MANAGER)
    customer_b = await make_customer(name="Beta")
    customer_a = await make_customer(name="Alpha")
    managed_a = await make_project(customer_id=customer_a.id, name="A", manager_id=manager.id)
    managed_b = await make_project(customer_id=customer_b.id, name="B", manager_id=manager.id)
    await make_project(manager_id=other_manager.id)
    member = await make_user()
    await bus.execute(AddProjectMember(project_id=managed_a.id, user_id=member.id))

    entries = await bus.query(ListManagedProjectsWithMembers(manager_id=manager.id))

    assert [entry.project.id for entry in entries] == [managed_a.id, managed_b.id]
    assert {m.user_id for m in entries[0].members} == {member.id}
    assert entries[1].members == ()


async def test_list_managed_projects_with_members_none_means_all_active(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    manager = await make_user(role=UserRole.PROJECT_MANAGER)
    managed = await make_project(manager_id=manager.id)
    unmanaged = await make_project()
    archived = await make_project()
    await bus.execute(UpdateProject(project_id=archived.id, is_active=False))

    entries = await bus.query(ListManagedProjectsWithMembers(manager_id=None))

    ids = {entry.project.id for entry in entries}
    assert {managed.id, unmanaged.id} <= ids
    assert archived.id not in ids


async def test_list_managed_projects_with_members_excludes_archived_projects(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    manager = await make_user(role=UserRole.PROJECT_MANAGER)
    archived = await make_project(manager_id=manager.id)
    await bus.execute(UpdateProject(project_id=archived.id, is_active=False))

    entries = await bus.query(ListManagedProjectsWithMembers(manager_id=manager.id))

    assert entries == ()


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


async def test_delete_project_cascades_to_members_and_billing_items(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    project = await make_project()
    user = await make_user()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))

    await bus.execute(DeleteProject(project_id=project.id))

    assert await bus.query(GetProjectById(project_id=project.id)) is None
    with pytest.raises(ProjectNotFoundError):
        await bus.query(ListProjectMembers(project_id=project.id))
    assert await _billing_items(bus.session, project.id) == []


async def test_delete_unknown_project_raises(bus: Bus) -> None:
    with pytest.raises(ProjectNotFoundError):
        await bus.execute(DeleteProject(project_id=uuid4()))


async def test_remove_user_from_all_projects_returns_count(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    project_a = await make_project()
    project_b = await make_project()
    user = await make_user()
    await bus.execute(AddProjectMember(project_id=project_a.id, user_id=user.id))
    await bus.execute(AddProjectMember(project_id=project_b.id, user_id=user.id))

    removed = await bus.execute(RemoveUserFromAllProjects(user_id=user.id))

    assert removed == 2
    assert await bus.query(ListProjectMembers(project_id=project_a.id)) == ()
    assert await bus.query(ListProjectMembers(project_id=project_b.id)) == ()


async def test_remove_user_from_all_projects_with_no_memberships_returns_zero(
    bus: Bus, make_user: UserFactory
) -> None:
    user = await make_user()

    assert await bus.execute(RemoveUserFromAllProjects(user_id=user.id)) == 0


# --- Billing items ---


async def _item_by_name(
    bus: Bus, project_id: UUID, name: str, *, include_inactive: bool = True
) -> ProjectBillingItemDTO:
    items = await bus.query(
        ListProjectBillingItems(project_id=project_id, include_inactive=include_inactive)
    )
    return next(item for item in items if item.name == name)


async def test_add_billing_item_appends_after_the_defaults(
    bus: Bus, make_project: ProjectFactory
) -> None:
    project = await make_project()

    item = await bus.execute(
        AddProjectBillingItem(
            project_id=project.id,
            name="On-call standby",
            unit=BillingUnit.HOUR,
            description="Weekend on-call",
            unit_rate=Decimal("50.00"),
        )
    )

    assert item.preset is None
    assert item.position == len(DEFAULT_BILLING_ITEMS) + 1
    assert item.unit_rate == Decimal("50.00")
    assert item.markup_percent is None
    assert item.is_active


async def test_add_billing_item_to_unknown_project_raises(bus: Bus) -> None:
    with pytest.raises(ProjectNotFoundError):
        await bus.execute(
            AddProjectBillingItem(project_id=uuid4(), name="Extra", unit=BillingUnit.HOUR)
        )


async def test_add_billing_item_to_archived_project_raises(
    bus: Bus, make_project: ProjectFactory
) -> None:
    project = await make_project()
    await bus.execute(UpdateProject(project_id=project.id, is_active=False))

    with pytest.raises(ProjectArchivedError):
        await bus.execute(
            AddProjectBillingItem(project_id=project.id, name="Extra", unit=BillingUnit.HOUR)
        )


async def test_billing_item_name_conflict_within_project_but_allowed_in_another_project(
    bus: Bus, make_project: ProjectFactory
) -> None:
    project = await make_project()
    await bus.execute(
        AddProjectBillingItem(project_id=project.id, name="Shared Name", unit=BillingUnit.HOUR)
    )

    with pytest.raises(BillingItemNameAlreadyExistsError):
        await bus.execute(
            AddProjectBillingItem(project_id=project.id, name="Shared Name", unit=BillingUnit.DAY)
        )

    other_project = await make_project()
    other_item = await bus.execute(
        AddProjectBillingItem(project_id=other_project.id, name="Shared Name", unit=BillingUnit.DAY)
    )
    assert other_item.name == "Shared Name"


@pytest.mark.parametrize(
    ("unit", "unit_rate", "markup_percent"),
    [
        (BillingUnit.AMOUNT, Decimal("10.00"), None),
        (BillingUnit.HOUR, None, Decimal("10.00")),
        (BillingUnit.DAY, None, Decimal("10.00")),
    ],
)
async def test_add_billing_item_rejects_pricing_that_does_not_match_its_unit(
    bus: Bus,
    make_project: ProjectFactory,
    unit: BillingUnit,
    unit_rate: Decimal | None,
    markup_percent: Decimal | None,
) -> None:
    project = await make_project()

    with pytest.raises(BillingItemPricingError):
        await bus.execute(
            AddProjectBillingItem(
                project_id=project.id,
                name="Extra",
                unit=unit,
                unit_rate=unit_rate,
                markup_percent=markup_percent,
            )
        )


async def test_list_billing_items_excludes_archived_by_default(
    bus: Bus, make_project: ProjectFactory
) -> None:
    project = await make_project()
    item = await bus.execute(
        AddProjectBillingItem(project_id=project.id, name="Extra", unit=BillingUnit.HOUR)
    )
    await bus.execute(
        UpdateProjectBillingItem(project_id=project.id, item_id=item.id, is_active=False)
    )

    active = await bus.query(ListProjectBillingItems(project_id=project.id))
    assert "Extra" not in {i.name for i in active}

    all_items = await bus.query(
        ListProjectBillingItems(project_id=project.id, include_inactive=True)
    )
    assert "Extra" in {i.name for i in all_items}


async def test_list_billing_items_for_unknown_project_raises(bus: Bus) -> None:
    with pytest.raises(ProjectNotFoundError):
        await bus.query(ListProjectBillingItems(project_id=uuid4()))


async def test_update_billing_item_changes_name_description_and_rate(
    bus: Bus, make_project: ProjectFactory
) -> None:
    project = await make_project()
    item = await bus.execute(
        AddProjectBillingItem(project_id=project.id, name="Extra", unit=BillingUnit.HOUR)
    )

    updated = await bus.execute(
        UpdateProjectBillingItem(
            project_id=project.id,
            item_id=item.id,
            name="Renamed",
            description="New description",
            unit_rate=Decimal("75.00"),
        )
    )

    assert updated.name == "Renamed"
    assert updated.description == "New description"
    assert updated.unit_rate == Decimal("75.00")


async def test_update_billing_item_clears_unit_rate(bus: Bus, make_project: ProjectFactory) -> None:
    project = await make_project()
    item = await bus.execute(
        AddProjectBillingItem(
            project_id=project.id, name="Extra", unit=BillingUnit.HOUR, unit_rate=Decimal("50.00")
        )
    )

    updated = await bus.execute(
        UpdateProjectBillingItem(
            project_id=project.id, item_id=item.id, clear_fields=frozenset({"unit_rate"})
        )
    )

    assert updated.unit_rate is None


async def test_update_billing_item_rejects_pricing_that_does_not_match_its_unit(
    bus: Bus, make_project: ProjectFactory
) -> None:
    project = await make_project()
    hours = await _item_by_name(bus, project.id, "Normal working hours")

    with pytest.raises(BillingItemPricingError):
        await bus.execute(
            UpdateProjectBillingItem(
                project_id=project.id, item_id=hours.id, markup_percent=Decimal("10.00")
            )
        )


async def test_archive_and_restore_billing_item(bus: Bus, make_project: ProjectFactory) -> None:
    project = await make_project()
    item = await bus.execute(
        AddProjectBillingItem(project_id=project.id, name="Extra", unit=BillingUnit.HOUR)
    )

    archived = await bus.execute(
        UpdateProjectBillingItem(project_id=project.id, item_id=item.id, is_active=False)
    )
    assert not archived.is_active

    restored = await bus.execute(
        UpdateProjectBillingItem(project_id=project.id, item_id=item.id, is_active=True)
    )
    assert restored.is_active


async def test_restore_billing_item_under_archived_project_raises(
    bus: Bus, make_project: ProjectFactory
) -> None:
    project = await make_project()
    item = await bus.execute(
        AddProjectBillingItem(project_id=project.id, name="Extra", unit=BillingUnit.HOUR)
    )
    await bus.execute(
        UpdateProjectBillingItem(project_id=project.id, item_id=item.id, is_active=False)
    )
    await bus.execute(UpdateProject(project_id=project.id, is_active=False))

    with pytest.raises(ProjectArchivedError):
        await bus.execute(
            UpdateProjectBillingItem(project_id=project.id, item_id=item.id, is_active=True)
        )


async def test_default_items_can_be_renamed_and_archived(
    bus: Bus, make_project: ProjectFactory
) -> None:
    project = await make_project()
    per_diem = await _item_by_name(bus, project.id, "Per diems")

    updated = await bus.execute(
        UpdateProjectBillingItem(
            project_id=project.id, item_id=per_diem.id, name="Daily allowance", is_active=False
        )
    )

    assert updated.name == "Daily allowance"
    assert not updated.is_active
    assert updated.preset == per_diem.preset


async def test_update_unknown_billing_item_raises(bus: Bus, make_project: ProjectFactory) -> None:
    project = await make_project()

    with pytest.raises(BillingItemNotFoundError):
        await bus.execute(UpdateProjectBillingItem(project_id=project.id, item_id=uuid4()))


async def test_update_billing_item_with_unknown_project_raises(bus: Bus) -> None:
    with pytest.raises(ProjectNotFoundError):
        await bus.execute(UpdateProjectBillingItem(project_id=uuid4(), item_id=uuid4()))


async def test_update_billing_item_with_wrong_project_id_raises_not_found(
    bus: Bus, make_project: ProjectFactory
) -> None:
    project = await make_project()
    other_project = await make_project()
    item = await bus.execute(
        AddProjectBillingItem(project_id=project.id, name="Extra", unit=BillingUnit.HOUR)
    )

    # other_project exists, so this is a mismatch, not a missing project: BillingItemNotFoundError.
    with pytest.raises(BillingItemNotFoundError):
        await bus.execute(
            UpdateProjectBillingItem(project_id=other_project.id, item_id=item.id, name="Renamed")
        )


async def test_delete_billing_item(bus: Bus, make_project: ProjectFactory) -> None:
    project = await make_project()
    item = await bus.execute(
        AddProjectBillingItem(project_id=project.id, name="Extra", unit=BillingUnit.HOUR)
    )

    await bus.execute(DeleteProjectBillingItem(project_id=project.id, item_id=item.id))

    items = await bus.query(ListProjectBillingItems(project_id=project.id, include_inactive=True))
    assert item.id not in {i.id for i in items}


async def test_delete_unknown_billing_item_raises(bus: Bus, make_project: ProjectFactory) -> None:
    project = await make_project()

    with pytest.raises(BillingItemNotFoundError):
        await bus.execute(DeleteProjectBillingItem(project_id=project.id, item_id=uuid4()))


# --- Batch queries (GetProjectsByIds, GetProjectBillingItemsByIds,
# ListMemberProjectsWithBillingItems) ---


async def test_get_projects_by_ids_orders_by_name_and_omits_unknown_ids(
    bus: Bus, make_project: ProjectFactory
) -> None:
    zed = await make_project(name="Zed Project")
    ann = await make_project(name="Ann Project")

    result = await bus.query(GetProjectsByIds(project_ids=frozenset({zed.id, ann.id, uuid4()})))

    assert [p.id for p in result] == [ann.id, zed.id]


async def test_get_projects_by_ids_with_empty_set_returns_empty(bus: Bus) -> None:
    assert await bus.query(GetProjectsByIds(project_ids=frozenset())) == ()


async def test_get_project_billing_items_by_ids_omits_unknown_ids(
    bus: Bus, make_project: ProjectFactory
) -> None:
    project = await make_project()
    item = await bus.execute(
        AddProjectBillingItem(project_id=project.id, name="Extra", unit=BillingUnit.HOUR)
    )

    result = await bus.query(
        GetProjectBillingItemsByIds(billing_item_ids=frozenset({item.id, uuid4()}))
    )

    assert [i.id for i in result] == [item.id]


async def test_get_project_billing_items_by_ids_with_empty_set_returns_empty(bus: Bus) -> None:
    assert await bus.query(GetProjectBillingItemsByIds(billing_item_ids=frozenset())) == ()


async def test_list_member_projects_with_billing_items_orders_by_name(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user = await make_user()
    zed = await make_project(name="Zed Project")
    ann = await make_project(name="Ann Project")
    await bus.execute(AddProjectMember(project_id=zed.id, user_id=user.id))
    await bus.execute(AddProjectMember(project_id=ann.id, user_id=user.id))

    options = await bus.query(ListMemberProjectsWithBillingItems(user_id=user.id))

    assert [option.project.id for option in options] == [ann.id, zed.id]
    for option in options:
        assert len(option.billing_items) == len(DEFAULT_BILLING_ITEMS)


async def test_list_member_projects_with_billing_items_excludes_non_member_projects(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user = await make_user()
    await make_project()

    assert await bus.query(ListMemberProjectsWithBillingItems(user_id=user.id)) == ()


async def test_list_member_projects_with_billing_items_excludes_archived_project(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user = await make_user()
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))
    await bus.execute(UpdateProject(project_id=project.id, is_active=False))

    assert await bus.query(ListMemberProjectsWithBillingItems(user_id=user.id)) == ()


async def test_list_member_projects_with_billing_items_excludes_archived_billing_items(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user = await make_user()
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))
    item = await bus.execute(
        AddProjectBillingItem(project_id=project.id, name="Extra", unit=BillingUnit.HOUR)
    )
    await bus.execute(
        UpdateProjectBillingItem(project_id=project.id, item_id=item.id, is_active=False)
    )

    options = await bus.query(ListMemberProjectsWithBillingItems(user_id=user.id))

    assert len(options) == 1
    item_ids = {i.id for i in options[0].billing_items}
    assert item.id not in item_ids
    assert len(item_ids) == len(DEFAULT_BILLING_ITEMS)
