from uuid import uuid4

import pytest

from support import ADMIN, ADMIN_ONLY, DEFAULT_PASSWORD, MANAGER, ProjectFactory, UserFactory
from time_reporting.core.cqrs import Bus
from time_reporting.core.passwords import verify_password
from time_reporting.modules.audit.contracts import AuditAction, AuditEventDTO, ListAuditEvents
from time_reporting.modules.projects.contracts import AddProjectMember, RemoveUserFromAllProjects
from time_reporting.modules.users.contracts import (
    ChangeOwnPassword,
    CreateUser,
    DeleteUser,
    EmailAlreadyExistsError,
    GetUserById,
    GetUserCredentialsByEmail,
    GetUsersByIds,
    InvalidCurrentPasswordError,
    ListUsers,
    RecordSuccessfulLogin,
    ResetUserPassword,
    SelfModificationError,
    UpdateUser,
    UserInUseError,
    UserNotFoundError,
    UserRole,
)


async def _user_events(
    bus: Bus, user_id: object, *, action: AuditAction | None = None
) -> tuple[AuditEventDTO, ...]:
    """``make_user`` itself calls ``CreateUser``, so a user created through it already has its own
    ``USER_CREATED`` event; pass ``action`` to isolate the event(s) a later command adds."""
    page = await bus.query(
        ListAuditEvents(
            limit=10, offset=0, entity_type="user", entity_id=str(user_id), action=action
        )
    )
    return page.items


async def test_create_user_normalizes_email_and_hashes_password(bus: Bus) -> None:
    user = await bus.execute(
        CreateUser(
            name="Ann",
            email="  Ann@Example.COM ",
            roles=MANAGER,
            password=DEFAULT_PASSWORD,
        )
    )

    assert user.email == "ann@example.com"
    assert user.roles == MANAGER
    assert user.is_active
    assert user.token_version == 0
    assert user.last_login_at is None

    credentials = await bus.query(GetUserCredentialsByEmail(email="ANN@example.com"))
    assert credentials is not None
    assert credentials.id == user.id
    assert (await verify_password(DEFAULT_PASSWORD, credentials.password_hash))[0]


async def test_create_user_records_one_audit_event_with_no_actor(bus: Bus) -> None:
    """The CLI's ``create-admin``/``seed-demo`` call ``CreateUser`` without an actor."""
    user = await bus.execute(
        CreateUser(name="Ann", email="ann2@example.com", roles=MANAGER, password=DEFAULT_PASSWORD)
    )

    events = await _user_events(bus, user.id)

    assert len(events) == 1
    assert events[0].action is AuditAction.USER_CREATED
    assert events[0].actor_id is None
    assert events[0].actor_name is None


async def test_create_user_records_one_audit_event_with_actor(
    bus: Bus, make_user: UserFactory
) -> None:
    admin = await make_user(roles=ADMIN)

    user = await bus.execute(
        CreateUser(
            name="Bob",
            email="bob2@example.com",
            roles=MANAGER,
            password=DEFAULT_PASSWORD,
            actor_id=admin.id,
        )
    )

    events = await _user_events(bus, user.id)

    assert len(events) == 1
    assert events[0].action is AuditAction.USER_CREATED
    assert events[0].actor_id == admin.id
    assert events[0].actor_name == admin.name


async def test_duplicate_email_is_rejected_and_session_stays_usable(
    bus: Bus, make_user: UserFactory
) -> None:
    existing = await make_user(email="dup@example.com")

    with pytest.raises(EmailAlreadyExistsError):
        await make_user(email="DUP@example.com")

    assert await bus.query(GetUserById(user_id=existing.id)) == existing


async def test_get_unknown_user_returns_none(bus: Bus) -> None:
    assert await bus.query(GetUserById(user_id=uuid4())) is None
    assert await bus.query(GetUserCredentialsByEmail(email="nobody@example.com")) is None


async def test_update_user_changes_only_given_fields(bus: Bus, make_user: UserFactory) -> None:
    admin = await make_user(roles=ADMIN)
    user = await make_user(name="Old Name")

    updated = await bus.execute(
        UpdateUser(
            user_id=user.id,
            acting_user_id=admin.id,
            email="New@Example.com",
            roles=MANAGER,
            is_active=False,
        )
    )

    assert updated.name == "Old Name"
    assert updated.email == "new@example.com"
    assert updated.roles == MANAGER
    assert not updated.is_active
    assert updated.updated_at >= user.updated_at

    # Both roles and is_active actually changed in this one command, so both get their own event.
    assert len(await _user_events(bus, user.id, action=AuditAction.USER_ROLES_CHANGED)) == 1
    assert len(await _user_events(bus, user.id, action=AuditAction.USER_DEACTIVATED)) == 1


async def test_update_user_roles_changed_records_one_audit_event(
    bus: Bus, make_user: UserFactory
) -> None:
    admin = await make_user(roles=ADMIN)
    user = await make_user()

    await bus.execute(UpdateUser(user_id=user.id, acting_user_id=admin.id, roles=MANAGER))

    events = await _user_events(bus, user.id, action=AuditAction.USER_ROLES_CHANGED)
    assert len(events) == 1
    assert events[0].actor_id == admin.id


async def test_update_user_roles_unchanged_records_no_audit_event(
    bus: Bus, make_user: UserFactory
) -> None:
    """Setting ``roles`` to the value it already has is not a change worth logging."""
    admin = await make_user(roles=ADMIN)
    user = await make_user(roles=MANAGER)

    await bus.execute(UpdateUser(user_id=user.id, acting_user_id=admin.id, roles=MANAGER))

    assert await _user_events(bus, user.id, action=AuditAction.USER_ROLES_CHANGED) == ()


async def test_update_user_activated_records_one_audit_event(
    bus: Bus, make_user: UserFactory
) -> None:
    admin = await make_user(roles=ADMIN)
    user = await make_user()
    await bus.execute(UpdateUser(user_id=user.id, acting_user_id=admin.id, is_active=False))

    await bus.execute(UpdateUser(user_id=user.id, acting_user_id=admin.id, is_active=True))

    assert len(await _user_events(bus, user.id, action=AuditAction.USER_ACTIVATED)) == 1
    assert len(await _user_events(bus, user.id, action=AuditAction.USER_DEACTIVATED)) == 1


async def test_update_unknown_user_raises(bus: Bus, make_user: UserFactory) -> None:
    admin = await make_user(roles=ADMIN)

    with pytest.raises(UserNotFoundError):
        await bus.execute(UpdateUser(user_id=uuid4(), acting_user_id=admin.id, name="X"))


async def test_update_rejects_taken_email(bus: Bus, make_user: UserFactory) -> None:
    admin = await make_user(roles=ADMIN)
    await make_user(email="taken@example.com")
    user = await make_user()

    with pytest.raises(EmailAlreadyExistsError):
        await bus.execute(
            UpdateUser(user_id=user.id, acting_user_id=admin.id, email="taken@example.com")
        )


@pytest.mark.parametrize(
    "changes", [{"roles": MANAGER}, {"is_active": False}], ids=["remove-own-admin", "deactivate"]
)
async def test_admin_cannot_remove_own_admin_level_or_deactivate_self(
    bus: Bus, make_user: UserFactory, changes: dict[str, object]
) -> None:
    admin = await make_user(roles=ADMIN)

    with pytest.raises(SelfModificationError):
        await bus.execute(UpdateUser(user_id=admin.id, acting_user_id=admin.id, **changes))  # type: ignore[arg-type]


async def test_admin_can_change_own_manager_level(bus: Bus, make_user: UserFactory) -> None:
    """An admin may drop their own ``manager`` level, unlike ``admin`` (lock-out guard)."""
    admin = await make_user(roles=ADMIN)

    updated = await bus.execute(
        UpdateUser(user_id=admin.id, acting_user_id=admin.id, roles=ADMIN_ONLY)
    )

    assert updated.roles == ADMIN_ONLY


async def test_admin_can_edit_own_profile(bus: Bus, make_user: UserFactory) -> None:
    admin = await make_user(roles=ADMIN)

    updated = await bus.execute(
        UpdateUser(
            user_id=admin.id,
            acting_user_id=admin.id,
            name="Renamed",
            roles=ADMIN,
            is_active=True,
        )
    )

    assert updated.name == "Renamed"


async def test_reset_password_invalidates_tokens(bus: Bus, make_user: UserFactory) -> None:
    admin = await make_user(roles=ADMIN)
    user = await make_user(email="reset@example.com")

    await bus.execute(
        ResetUserPassword(user_id=user.id, new_password="brand-new-password", actor_id=admin.id)
    )

    credentials = await bus.query(GetUserCredentialsByEmail(email="reset@example.com"))
    assert credentials is not None
    assert credentials.token_version == user.token_version + 1
    assert (await verify_password("brand-new-password", credentials.password_hash))[0]

    events = await _user_events(bus, user.id, action=AuditAction.USER_PASSWORD_RESET)
    assert len(events) == 1
    assert events[0].actor_id == admin.id


async def test_change_own_password_requires_current_password(
    bus: Bus, make_user: UserFactory
) -> None:
    user = await make_user()

    with pytest.raises(InvalidCurrentPasswordError):
        await bus.execute(
            ChangeOwnPassword(
                user_id=user.id, current_password="wrong-password", new_password="new-password"
            )
        )
    unchanged = await bus.query(GetUserById(user_id=user.id))
    assert unchanged is not None
    assert unchanged.token_version == user.token_version

    await bus.execute(
        ChangeOwnPassword(
            user_id=user.id, current_password=DEFAULT_PASSWORD, new_password="new-password"
        )
    )
    changed = await bus.query(GetUserById(user_id=user.id))
    assert changed is not None
    assert changed.token_version == user.token_version + 1

    # Self-service, not "password reset by admin" — not audited.
    assert await _user_events(bus, user.id, action=AuditAction.USER_PASSWORD_RESET) == ()


async def test_record_successful_login(bus: Bus, make_user: UserFactory) -> None:
    user = await make_user()

    await bus.execute(RecordSuccessfulLogin(user_id=user.id))

    logged_in = await bus.query(GetUserById(user_id=user.id))
    assert logged_in is not None
    assert logged_in.last_login_at is not None


async def test_list_users_is_paginated(bus: Bus, make_user: UserFactory) -> None:
    total_before = (await bus.query(ListUsers(limit=1, offset=0))).total
    for _ in range(3):
        await make_user()

    page = await bus.query(ListUsers(limit=2, offset=0))

    assert page.total == total_before + 3
    assert len(page.items) == 2
    assert (page.limit, page.offset) == (2, 0)


async def test_list_users_filters_by_search_and_active_status(
    bus: Bus, make_user: UserFactory
) -> None:
    match = await make_user(name="Searchable Match", email="searchable-match@example.com")
    await make_user(name="Someone Else", email="someone-else@example.com")
    inactive = await make_user(name="Searchable Inactive", email="searchable-inactive@example.com")
    await bus.execute(UpdateUser(user_id=inactive.id, acting_user_id=match.id, is_active=False))

    by_name = await bus.query(ListUsers(limit=100, offset=0, search="Searchable Match"))
    assert {u.id for u in by_name.items} == {match.id}

    by_email = await bus.query(ListUsers(limit=100, offset=0, search="SEARCHABLE-match@EXAMPLE"))
    assert {u.id for u in by_email.items} == {match.id}

    all_active_only = await bus.query(
        ListUsers(limit=100, offset=0, search="Searchable", include_inactive=False)
    )
    assert {u.id for u in all_active_only.items} == {match.id}

    all_including_inactive = await bus.query(
        ListUsers(limit=100, offset=0, search="Searchable", include_inactive=True)
    )
    assert {u.id for u in all_including_inactive.items} == {match.id, inactive.id}


async def test_list_users_filters_by_roles(bus: Bus, make_user: UserFactory) -> None:
    admin = await make_user(roles=ADMIN_ONLY, name="Ada Admin", email="ada-roles@example.com")
    manager = await make_user(roles=MANAGER, name="Mark Manager", email="mark-roles@example.com")
    await make_user(name="Wendy Worker", email="wendy-roles@example.com")

    page = await bus.query(
        ListUsers(limit=100, offset=0, roles=frozenset({UserRole.ADMIN, UserRole.MANAGER}))
    )

    ids = {u.id for u in page.items}
    assert admin.id in ids
    assert manager.id in ids


async def test_list_users_roles_filter_is_any_of(bus: Bus, make_user: UserFactory) -> None:
    """A user holding both levels matches a filter naming either one, not just the combination."""
    combined = await make_user(roles=ADMIN, name="Max Multi", email="max-roles@example.com")

    admin_only_page = await bus.query(
        ListUsers(limit=100, offset=0, roles=frozenset({UserRole.ADMIN}))
    )
    manager_only_page = await bus.query(
        ListUsers(limit=100, offset=0, roles=frozenset({UserRole.MANAGER}))
    )

    assert combined.id in {u.id for u in admin_only_page.items}
    assert combined.id in {u.id for u in manager_only_page.items}


async def test_list_users_search_treats_wildcards_as_literal(
    bus: Bus, make_user: UserFactory
) -> None:
    await make_user(name="100% Match", email="literal-percent@example.com")
    await make_user(name="Other", email="other-literal@example.com")

    page = await bus.query(ListUsers(limit=100, offset=0, search="100% Match"))

    assert {u.email for u in page.items} == {"literal-percent@example.com"}


async def test_get_users_by_ids_orders_by_name_and_omits_unknown(
    bus: Bus, make_user: UserFactory
) -> None:
    zed = await make_user(name="Zed")
    ann = await make_user(name="Ann")

    result = await bus.query(GetUsersByIds(user_ids=frozenset({zed.id, ann.id, uuid4()})))

    assert [user.id for user in result] == [ann.id, zed.id]


async def test_get_users_by_ids_with_empty_set_returns_empty(bus: Bus) -> None:
    assert await bus.query(GetUsersByIds(user_ids=frozenset())) == ()


async def test_delete_user_removes_the_row(bus: Bus, make_user: UserFactory) -> None:
    admin = await make_user(roles=ADMIN)
    user = await make_user()

    await bus.execute(DeleteUser(user_id=user.id, acting_user_id=admin.id))

    assert await bus.query(GetUserById(user_id=user.id)) is None


async def test_delete_user_rejects_self_deletion(bus: Bus, make_user: UserFactory) -> None:
    admin = await make_user(roles=ADMIN)

    with pytest.raises(SelfModificationError):
        await bus.execute(DeleteUser(user_id=admin.id, acting_user_id=admin.id))

    assert await bus.query(GetUserById(user_id=admin.id)) is not None


async def test_delete_unknown_user_raises(bus: Bus, make_user: UserFactory) -> None:
    admin = await make_user(roles=ADMIN)

    with pytest.raises(UserNotFoundError):
        await bus.execute(DeleteUser(user_id=uuid4(), acting_user_id=admin.id))


async def test_delete_user_blocked_by_project_membership(
    bus: Bus, make_user: UserFactory, make_project: ProjectFactory
) -> None:
    admin = await make_user(roles=ADMIN)
    user = await make_user()
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))

    with pytest.raises(UserInUseError):
        await bus.execute(DeleteUser(user_id=user.id, acting_user_id=admin.id))

    assert await bus.query(GetUserById(user_id=user.id)) is not None

    removed = await bus.execute(RemoveUserFromAllProjects(user_id=user.id))
    assert removed == 1

    await bus.execute(DeleteUser(user_id=user.id, acting_user_id=admin.id))
    assert await bus.query(GetUserById(user_id=user.id)) is None
