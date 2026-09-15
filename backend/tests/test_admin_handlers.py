from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from support import CustomerFactory, ProjectFactory, UserFactory
from time_reporting.core.cqrs import Bus
from time_reporting.modules.admin.contracts import (
    GetCustomerRemovalImpact,
    GetProjectRemovalImpact,
    GetUserRemovalImpact,
    RemovalBlockedError,
    RemovalBlockerKind,
    RemovalCountDTO,
    RemovalEffectKind,
    RemovalOutcome,
    RemovalTargetNotFoundError,
    RemoveCustomer,
    RemoveProject,
    RemoveUser,
    SelfRemovalError,
)
from time_reporting.modules.customers.contracts import GetCustomerById
from time_reporting.modules.projects.contracts import (
    DEFAULT_BILLING_ITEMS,
    AddProjectMember,
    BillingItemPreset,
    GetProjectById,
    ListProjectBillingItems,
    ListProjectMembers,
    UpdateProject,
)
from time_reporting.modules.timesheets.contracts import SaveTimesheetWeek, TimeEntryChange
from time_reporting.modules.users import repository as users_repository
from time_reporting.modules.users.contracts import GetUserById, UserRole

# 2026-09-14 is a Monday.
A_MONDAY = date(2026, 9, 14)


async def _book_normal_hours(bus: Bus, *, project_id: UUID, user_id: UUID) -> None:
    """Book one hour of normal working time for ``user_id`` on ``project_id``, for tests that need
    a project/user blocked by a real time entry rather than a project membership."""
    items = await bus.query(ListProjectBillingItems(project_id=project_id))
    item = next(i for i in items if i.preset == BillingItemPreset.NORMAL_HOURS)
    await bus.execute(
        SaveTimesheetWeek(
            user_id=user_id,
            week_start=A_MONDAY,
            changes=(
                TimeEntryChange(billing_item_id=item.id, date=A_MONDAY, quantity=Decimal("1")),
            ),
        )
    )


# --- Removal impact ---


async def test_user_removal_impact_with_no_dependencies(bus: Bus, make_user: UserFactory) -> None:
    admin = await make_user(role=UserRole.ADMIN)
    user = await make_user()

    impact = await bus.query(GetUserRemovalImpact(user_id=user.id, acting_user_id=admin.id))

    assert impact is not None
    assert impact.is_active is True
    assert impact.can_delete_permanently is True
    assert impact.blockers == ()
    assert impact.effects == ()


async def test_user_removal_impact_flags_self(bus: Bus, make_user: UserFactory) -> None:
    admin = await make_user(role=UserRole.ADMIN)

    impact = await bus.query(GetUserRemovalImpact(user_id=admin.id, acting_user_id=admin.id))

    assert impact is not None
    assert impact.can_delete_permanently is False
    assert impact.blockers == (RemovalCountDTO(kind=RemovalBlockerKind.SELF, count=1),)


async def test_user_removal_impact_lists_membership_effect(
    bus: Bus, make_user: UserFactory, make_project: ProjectFactory
) -> None:
    admin = await make_user(role=UserRole.ADMIN)
    user = await make_user()
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))

    impact = await bus.query(GetUserRemovalImpact(user_id=user.id, acting_user_id=admin.id))

    assert impact is not None
    assert impact.can_delete_permanently is True
    assert impact.effects[0].kind == RemovalEffectKind.PROJECT_MEMBERSHIPS
    assert impact.effects[0].count == 1


async def test_user_removal_impact_lists_managed_projects_effect(
    bus: Bus, make_user: UserFactory, make_project: ProjectFactory
) -> None:
    admin = await make_user(role=UserRole.ADMIN)
    manager = await make_user(role=UserRole.PROJECT_MANAGER)
    await make_project(manager_id=manager.id)

    impact = await bus.query(GetUserRemovalImpact(user_id=manager.id, acting_user_id=admin.id))

    assert impact is not None
    assert impact.can_delete_permanently is True
    managed = next(e for e in impact.effects if e.kind == RemovalEffectKind.MANAGED_PROJECTS)
    assert managed.count == 1


async def test_user_removal_impact_blocked_by_time_entries(
    bus: Bus, make_user: UserFactory, make_project: ProjectFactory
) -> None:
    admin = await make_user(role=UserRole.ADMIN)
    user = await make_user()
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))
    await _book_normal_hours(bus, project_id=project.id, user_id=user.id)

    impact = await bus.query(GetUserRemovalImpact(user_id=user.id, acting_user_id=admin.id))

    assert impact is not None
    assert impact.can_delete_permanently is False
    blocker = next(b for b in impact.blockers if b.kind == RemovalBlockerKind.TIME_ENTRIES)
    assert blocker.count == 1


async def test_user_removal_impact_unknown_user_returns_none(
    bus: Bus, make_user: UserFactory
) -> None:
    admin = await make_user(role=UserRole.ADMIN)

    assert await bus.query(GetUserRemovalImpact(user_id=uuid4(), acting_user_id=admin.id)) is None


async def test_customer_removal_impact_blocked_by_project(
    bus: Bus, make_customer: CustomerFactory, make_project: ProjectFactory
) -> None:
    customer = await make_customer()
    await make_project(customer_id=customer.id)

    impact = await bus.query(GetCustomerRemovalImpact(customer_id=customer.id))

    assert impact is not None
    assert impact.can_delete_permanently is False
    assert impact.blockers[0].kind == RemovalBlockerKind.PROJECTS
    assert impact.blockers[0].count == 1


async def test_customer_removal_impact_without_projects(
    bus: Bus, make_customer: CustomerFactory
) -> None:
    customer = await make_customer()

    impact = await bus.query(GetCustomerRemovalImpact(customer_id=customer.id))

    assert impact is not None
    assert impact.can_delete_permanently is True
    assert impact.blockers == ()


async def test_customer_removal_impact_unknown_returns_none(bus: Bus) -> None:
    assert await bus.query(GetCustomerRemovalImpact(customer_id=uuid4())) is None


async def test_project_removal_impact_lists_members_effect(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    project = await make_project()
    user = await make_user()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))

    impact = await bus.query(GetProjectRemovalImpact(project_id=project.id))

    assert impact is not None
    assert impact.can_delete_permanently is True
    assert impact.effects[0].kind == RemovalEffectKind.PROJECT_MEMBERS
    assert impact.effects[0].count == 1


async def test_project_removal_impact_lists_billing_items_effect(
    bus: Bus, make_project: ProjectFactory
) -> None:
    project = await make_project()

    impact = await bus.query(GetProjectRemovalImpact(project_id=project.id))

    assert impact is not None
    assert impact.can_delete_permanently is True
    # Every project has the six default billing items, so this effect is never empty.
    billing_items_effect = next(
        e for e in impact.effects if e.kind == RemovalEffectKind.PROJECT_BILLING_ITEMS
    )
    assert billing_items_effect.count == len(DEFAULT_BILLING_ITEMS)


async def test_project_removal_impact_blocked_by_time_entries(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    project = await make_project()
    user = await make_user()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))
    await _book_normal_hours(bus, project_id=project.id, user_id=user.id)

    impact = await bus.query(GetProjectRemovalImpact(project_id=project.id))

    assert impact is not None
    assert impact.can_delete_permanently is False
    blocker = next(b for b in impact.blockers if b.kind == RemovalBlockerKind.TIME_ENTRIES)
    assert blocker.count == 1


async def test_project_removal_impact_unknown_returns_none(bus: Bus) -> None:
    assert await bus.query(GetProjectRemovalImpact(project_id=uuid4())) is None


# --- Removal (archive) ---


async def test_remove_user_default_archives(bus: Bus, make_user: UserFactory) -> None:
    admin = await make_user(role=UserRole.ADMIN)
    user = await make_user()

    outcome = await bus.execute(RemoveUser(user_id=user.id, acting_user_id=admin.id))

    assert outcome is RemovalOutcome.ARCHIVED
    reloaded = await bus.query(GetUserById(user_id=user.id))
    assert reloaded is not None
    assert reloaded.is_active is False


async def test_remove_user_archive_is_idempotent(bus: Bus, make_user: UserFactory) -> None:
    admin = await make_user(role=UserRole.ADMIN)
    user = await make_user()

    await bus.execute(RemoveUser(user_id=user.id, acting_user_id=admin.id))
    outcome = await bus.execute(RemoveUser(user_id=user.id, acting_user_id=admin.id))

    assert outcome is RemovalOutcome.ARCHIVED


async def test_remove_user_rejects_self_in_both_modes(bus: Bus, make_user: UserFactory) -> None:
    admin = await make_user(role=UserRole.ADMIN)

    with pytest.raises(SelfRemovalError):
        await bus.execute(RemoveUser(user_id=admin.id, acting_user_id=admin.id))
    with pytest.raises(SelfRemovalError):
        await bus.execute(RemoveUser(user_id=admin.id, acting_user_id=admin.id, permanent=True))


async def test_remove_customer_default_archives(bus: Bus, make_customer: CustomerFactory) -> None:
    customer = await make_customer()

    outcome = await bus.execute(RemoveCustomer(customer_id=customer.id))

    assert outcome is RemovalOutcome.ARCHIVED
    reloaded = await bus.query(GetCustomerById(customer_id=customer.id))
    assert reloaded is not None
    assert reloaded.is_active is False


async def test_remove_project_default_archives(bus: Bus, make_project: ProjectFactory) -> None:
    project = await make_project()

    outcome = await bus.execute(RemoveProject(project_id=project.id))

    assert outcome is RemovalOutcome.ARCHIVED
    reloaded = await bus.query(GetProjectById(project_id=project.id))
    assert reloaded is not None
    assert reloaded.is_active is False


# --- Removal (permanent delete) ---


async def test_remove_user_permanently_deletes_and_cascades_memberships(
    bus: Bus, make_user: UserFactory, make_project: ProjectFactory
) -> None:
    admin = await make_user(role=UserRole.ADMIN)
    user = await make_user()
    project_a = await make_project()
    project_b = await make_project()
    await bus.execute(AddProjectMember(project_id=project_a.id, user_id=user.id))
    await bus.execute(AddProjectMember(project_id=project_b.id, user_id=user.id))

    outcome = await bus.execute(
        RemoveUser(user_id=user.id, acting_user_id=admin.id, permanent=True)
    )

    assert outcome is RemovalOutcome.DELETED
    assert await bus.query(GetUserById(user_id=user.id)) is None
    assert await bus.query(ListProjectMembers(project_id=project_a.id)) == ()
    assert await bus.query(ListProjectMembers(project_id=project_b.id)) == ()


async def test_remove_user_permanently_clears_manager_assignment(
    bus: Bus, make_user: UserFactory, make_project: ProjectFactory
) -> None:
    admin = await make_user(role=UserRole.ADMIN)
    manager = await make_user(role=UserRole.PROJECT_MANAGER)
    project = await make_project(manager_id=manager.id)

    outcome = await bus.execute(
        RemoveUser(user_id=manager.id, acting_user_id=admin.id, permanent=True)
    )

    assert outcome is RemovalOutcome.DELETED
    refreshed = await bus.query(GetProjectById(project_id=project.id))
    assert refreshed is not None
    assert refreshed.manager is None


async def test_remove_user_permanently_rolls_back_membership_removal_on_failure(
    bus: Bus, make_user: UserFactory, make_project: ProjectFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If deleting the user itself fails after its memberships were removed, the whole
    ``RemoveUser`` command rolls back — the memberships must still be there afterwards."""
    admin = await make_user(role=UserRole.ADMIN)
    user = await make_user()
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))

    async def failing_delete(self: object, target: object) -> None:
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(users_repository.UserRepository, "delete", failing_delete)

    with pytest.raises(RuntimeError, match="simulated failure"):
        await bus.execute(RemoveUser(user_id=user.id, acting_user_id=admin.id, permanent=True))

    members = await bus.query(ListProjectMembers(project_id=project.id))
    assert [m.user_id for m in members] == [user.id]


async def test_remove_user_permanently_blocked_by_time_entries(
    bus: Bus, make_user: UserFactory, make_project: ProjectFactory
) -> None:
    admin = await make_user(role=UserRole.ADMIN)
    user = await make_user()
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))
    await _book_normal_hours(bus, project_id=project.id, user_id=user.id)

    with pytest.raises(RemovalBlockedError) as exc_info:
        await bus.execute(RemoveUser(user_id=user.id, acting_user_id=admin.id, permanent=True))

    assert exc_info.value.blockers[0].kind == RemovalBlockerKind.TIME_ENTRIES
    assert await bus.query(GetUserById(user_id=user.id)) is not None


async def test_remove_customer_permanently_blocked_by_archived_project(
    bus: Bus, make_customer: CustomerFactory, make_project: ProjectFactory
) -> None:
    customer = await make_customer()
    project = await make_project(customer_id=customer.id)
    await bus.execute(UpdateProject(project_id=project.id, is_active=False))

    with pytest.raises(RemovalBlockedError) as exc_info:
        await bus.execute(RemoveCustomer(customer_id=customer.id, permanent=True))

    assert exc_info.value.blockers[0].kind == RemovalBlockerKind.PROJECTS
    reloaded = await bus.query(GetCustomerById(customer_id=customer.id))
    assert reloaded is not None
    assert reloaded.is_active is True


async def test_remove_project_permanently_deletes_with_members(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    project = await make_project()
    user = await make_user()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))

    outcome = await bus.execute(RemoveProject(project_id=project.id, permanent=True))

    assert outcome is RemovalOutcome.DELETED
    assert await bus.query(GetProjectById(project_id=project.id)) is None


async def test_remove_project_permanently_blocked_by_time_entries(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    project = await make_project()
    user = await make_user()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))
    await _book_normal_hours(bus, project_id=project.id, user_id=user.id)

    with pytest.raises(RemovalBlockedError) as exc_info:
        await bus.execute(RemoveProject(project_id=project.id, permanent=True))

    assert exc_info.value.blockers[0].kind == RemovalBlockerKind.TIME_ENTRIES
    assert await bus.query(GetProjectById(project_id=project.id)) is not None


async def test_remove_unknown_user_raises_not_found(bus: Bus, make_user: UserFactory) -> None:
    admin = await make_user(role=UserRole.ADMIN)

    with pytest.raises(RemovalTargetNotFoundError):
        await bus.execute(RemoveUser(user_id=uuid4(), acting_user_id=admin.id))
    with pytest.raises(RemovalTargetNotFoundError):
        await bus.execute(RemoveUser(user_id=uuid4(), acting_user_id=admin.id, permanent=True))
