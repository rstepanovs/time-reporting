from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from support import ADMIN, EMPLOYEE, MANAGER, ProjectFactory, UserFactory
from time_reporting.core.cqrs import Bus
from time_reporting.modules.projects.contracts import (
    AddProjectMember,
    BillingItemPreset,
    ListProjectBillingItems,
    UpdateProject,
    UpdateProjectBillingItem,
)
from time_reporting.modules.timesheets.contracts import (
    ApproveTimesheetWeek,
    CountTimeEntries,
    DailyHoursExceededError,
    DuplicateChangeError,
    EntryDateOutsideWeekError,
    GetTimesheetWeek,
    InvalidWeekStatusTransitionError,
    ListSubmittedTimesheetWeeks,
    ListTimesheetOptions,
    QuantityOutOfRangeError,
    ReturnCommentRequiredError,
    ReturnTimesheetWeek,
    RowCommentChange,
    SaveTimesheetWeek,
    SelfReviewError,
    SubmitTimesheetWeek,
    TimeEntryChange,
    TimesheetBillingItemNotFoundError,
    TimesheetRowClosedError,
    TimesheetWeekLockedError,
    TimesheetWeekStatus,
    WeekStartNotMondayError,
)
from time_reporting.modules.users.contracts import UserNotFoundError

# 2026-09-14 is a Monday.
A_MONDAY = date(2026, 9, 14)
A_TUESDAY = date(2026, 9, 15)


async def _normal_hours_item_id(bus: Bus, project_id: UUID) -> UUID:
    items = await bus.query(ListProjectBillingItems(project_id=project_id))
    return next(item.id for item in items if item.preset == BillingItemPreset.NORMAL_HOURS)


async def _per_diem_item_id(bus: Bus, project_id: UUID) -> UUID:
    items = await bus.query(ListProjectBillingItems(project_id=project_id))
    return next(item.id for item in items if item.preset == BillingItemPreset.PER_DIEM)


async def test_save_week_creates_updates_and_deletes_a_cell(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user = await make_user()
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))
    item_id = await _normal_hours_item_id(bus, project.id)

    created = await bus.execute(
        SaveTimesheetWeek(
            user_id=user.id,
            week_start=A_MONDAY,
            changes=(
                TimeEntryChange(
                    billing_item_id=item_id, date=A_MONDAY, quantity=Decimal("8"), note="Kickoff"
                ),
            ),
        )
    )
    row = next(r for r in created.rows if r.billing_item.id == item_id)
    assert [(e.date, e.quantity, e.note) for e in row.entries] == [
        (A_MONDAY, Decimal("8.00"), "Kickoff")
    ]
    assert row.is_open is True

    updated = await bus.execute(
        SaveTimesheetWeek(
            user_id=user.id,
            week_start=A_MONDAY,
            changes=(
                TimeEntryChange(billing_item_id=item_id, date=A_MONDAY, quantity=Decimal("6")),
            ),
        )
    )
    row = next(r for r in updated.rows if r.billing_item.id == item_id)
    assert [(e.date, e.quantity, e.note) for e in row.entries] == [
        (A_MONDAY, Decimal("6.00"), None)
    ]

    deleted = await bus.execute(
        SaveTimesheetWeek(
            user_id=user.id,
            week_start=A_MONDAY,
            changes=(TimeEntryChange(billing_item_id=item_id, date=A_MONDAY, quantity=None),),
        )
    )
    assert deleted.rows == ()


async def test_get_week_reflects_ownership_and_calendar(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    owner = await make_user()
    viewer = await make_user()
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=owner.id))
    item_id = await _normal_hours_item_id(bus, project.id)
    await bus.execute(
        SaveTimesheetWeek(
            user_id=owner.id,
            week_start=A_MONDAY,
            changes=(
                TimeEntryChange(billing_item_id=item_id, date=A_MONDAY, quantity=Decimal("8")),
            ),
        )
    )

    own_week = await bus.query(
        GetTimesheetWeek(user_id=owner.id, week_start=A_MONDAY, viewer_id=owner.id)
    )
    other_week = await bus.query(
        GetTimesheetWeek(user_id=owner.id, week_start=A_MONDAY, viewer_id=viewer.id)
    )

    assert own_week.can_edit is True
    assert other_week.can_edit is False
    assert len(own_week.days) == 7
    assert own_week.days[0].day == A_MONDAY


async def test_get_week_for_unknown_user_raises(bus: Bus) -> None:
    with pytest.raises(UserNotFoundError):
        await bus.query(GetTimesheetWeek(user_id=uuid4(), week_start=A_MONDAY, viewer_id=uuid4()))


async def test_get_week_rejects_non_monday(bus: Bus, make_user: UserFactory) -> None:
    user = await make_user()
    with pytest.raises(WeekStartNotMondayError):
        await bus.query(GetTimesheetWeek(user_id=user.id, week_start=A_TUESDAY, viewer_id=user.id))


async def test_save_week_rejects_non_monday(bus: Bus, make_user: UserFactory) -> None:
    user = await make_user()
    with pytest.raises(WeekStartNotMondayError):
        await bus.execute(SaveTimesheetWeek(user_id=user.id, week_start=A_TUESDAY, changes=()))


async def test_save_week_rejects_date_outside_week(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user = await make_user()
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))
    item_id = await _normal_hours_item_id(bus, project.id)

    with pytest.raises(EntryDateOutsideWeekError):
        await bus.execute(
            SaveTimesheetWeek(
                user_id=user.id,
                week_start=A_MONDAY,
                changes=(
                    TimeEntryChange(
                        billing_item_id=item_id, date=date(2026, 9, 21), quantity=Decimal("1")
                    ),
                ),
            )
        )


async def test_save_week_rejects_duplicate_change(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user = await make_user()
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))
    item_id = await _normal_hours_item_id(bus, project.id)

    with pytest.raises(DuplicateChangeError):
        await bus.execute(
            SaveTimesheetWeek(
                user_id=user.id,
                week_start=A_MONDAY,
                changes=(
                    TimeEntryChange(billing_item_id=item_id, date=A_MONDAY, quantity=Decimal("1")),
                    TimeEntryChange(billing_item_id=item_id, date=A_MONDAY, quantity=Decimal("2")),
                ),
            )
        )


async def test_save_week_rejects_unknown_billing_item(bus: Bus, make_user: UserFactory) -> None:
    user = await make_user()

    with pytest.raises(TimesheetBillingItemNotFoundError):
        await bus.execute(
            SaveTimesheetWeek(
                user_id=user.id,
                week_start=A_MONDAY,
                changes=(
                    TimeEntryChange(billing_item_id=uuid4(), date=A_MONDAY, quantity=Decimal("1")),
                ),
            )
        )


async def test_save_week_rejects_non_member(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user = await make_user()
    project = await make_project()
    item_id = await _normal_hours_item_id(bus, project.id)

    with pytest.raises(TimesheetRowClosedError):
        await bus.execute(
            SaveTimesheetWeek(
                user_id=user.id,
                week_start=A_MONDAY,
                changes=(
                    TimeEntryChange(billing_item_id=item_id, date=A_MONDAY, quantity=Decimal("1")),
                ),
            )
        )


async def test_save_week_rejects_archived_project(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user = await make_user()
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))
    item_id = await _normal_hours_item_id(bus, project.id)
    await bus.execute(UpdateProject(project_id=project.id, is_active=False))

    with pytest.raises(TimesheetRowClosedError):
        await bus.execute(
            SaveTimesheetWeek(
                user_id=user.id,
                week_start=A_MONDAY,
                changes=(
                    TimeEntryChange(billing_item_id=item_id, date=A_MONDAY, quantity=Decimal("1")),
                ),
            )
        )


async def test_save_week_rejects_archived_billing_item(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user = await make_user()
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))
    item_id = await _normal_hours_item_id(bus, project.id)
    await bus.execute(
        UpdateProjectBillingItem(project_id=project.id, item_id=item_id, is_active=False)
    )

    with pytest.raises(TimesheetRowClosedError):
        await bus.execute(
            SaveTimesheetWeek(
                user_id=user.id,
                week_start=A_MONDAY,
                changes=(
                    TimeEntryChange(billing_item_id=item_id, date=A_MONDAY, quantity=Decimal("1")),
                ),
            )
        )


async def test_existing_entries_on_a_now_closed_row_are_read_only_but_listed(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user = await make_user()
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))
    item_id = await _normal_hours_item_id(bus, project.id)
    await bus.execute(
        SaveTimesheetWeek(
            user_id=user.id,
            week_start=A_MONDAY,
            changes=(
                TimeEntryChange(billing_item_id=item_id, date=A_MONDAY, quantity=Decimal("8")),
            ),
        )
    )

    await bus.execute(UpdateProject(project_id=project.id, is_active=False))

    week = await bus.query(
        GetTimesheetWeek(user_id=user.id, week_start=A_MONDAY, viewer_id=user.id)
    )
    row = next(r for r in week.rows if r.billing_item.id == item_id)
    assert row.is_open is False
    assert len(row.entries) == 1

    with pytest.raises(TimesheetRowClosedError):
        await bus.execute(
            SaveTimesheetWeek(
                user_id=user.id,
                week_start=A_MONDAY,
                changes=(TimeEntryChange(billing_item_id=item_id, date=A_MONDAY, quantity=None),),
            )
        )


@pytest.mark.parametrize("quantity", ["0", "-1", "25"])
async def test_save_week_rejects_out_of_range_hour_quantity(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory, quantity: str
) -> None:
    user = await make_user()
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))
    item_id = await _normal_hours_item_id(bus, project.id)

    with pytest.raises(QuantityOutOfRangeError):
        await bus.execute(
            SaveTimesheetWeek(
                user_id=user.id,
                week_start=A_MONDAY,
                changes=(
                    TimeEntryChange(
                        billing_item_id=item_id, date=A_MONDAY, quantity=Decimal(quantity)
                    ),
                ),
            )
        )


@pytest.mark.parametrize("quantity", ["0", "-1", "1.5"])
async def test_save_week_rejects_out_of_range_day_quantity(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory, quantity: str
) -> None:
    user = await make_user()
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))
    item_id = await _per_diem_item_id(bus, project.id)

    with pytest.raises(QuantityOutOfRangeError):
        await bus.execute(
            SaveTimesheetWeek(
                user_id=user.id,
                week_start=A_MONDAY,
                changes=(
                    TimeEntryChange(
                        billing_item_id=item_id, date=A_MONDAY, quantity=Decimal(quantity)
                    ),
                ),
            )
        )


async def test_save_week_allows_amount_with_no_upper_bound(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user = await make_user()
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))
    items = await bus.query(ListProjectBillingItems(project_id=project.id))
    expense_item = next(i for i in items if i.preset == BillingItemPreset.OTHER_EXPENSES)

    updated = await bus.execute(
        SaveTimesheetWeek(
            user_id=user.id,
            week_start=A_MONDAY,
            changes=(
                TimeEntryChange(
                    billing_item_id=expense_item.id, date=A_MONDAY, quantity=Decimal("999.99")
                ),
            ),
        )
    )
    row = next(r for r in updated.rows if r.billing_item.id == expense_item.id)
    assert row.entries[0].quantity == Decimal("999.99")


async def test_save_week_rejects_more_than_24_hours_on_one_day(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user = await make_user()
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))
    normal_id = await _normal_hours_item_id(bus, project.id)
    items = await bus.query(ListProjectBillingItems(project_id=project.id))
    overtime_id = next(i for i in items if i.preset == BillingItemPreset.OVERTIME_HOURS).id

    await bus.execute(
        SaveTimesheetWeek(
            user_id=user.id,
            week_start=A_MONDAY,
            changes=(
                TimeEntryChange(billing_item_id=normal_id, date=A_MONDAY, quantity=Decimal("20")),
            ),
        )
    )

    with pytest.raises(DailyHoursExceededError):
        await bus.execute(
            SaveTimesheetWeek(
                user_id=user.id,
                week_start=A_MONDAY,
                changes=(
                    TimeEntryChange(
                        billing_item_id=overtime_id, date=A_MONDAY, quantity=Decimal("10")
                    ),
                ),
            )
        )

    # The rejected batch changed nothing: still only the original 20 hours.
    week = await bus.query(
        GetTimesheetWeek(user_id=user.id, week_start=A_MONDAY, viewer_id=user.id)
    )
    total_hours = sum(
        (entry.quantity for row in week.rows for entry in row.entries), start=Decimal("0")
    )
    assert total_hours == Decimal("20.00")


async def test_save_week_allows_moving_hours_between_rows_within_the_limit(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user = await make_user()
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))
    normal_id = await _normal_hours_item_id(bus, project.id)
    items = await bus.query(ListProjectBillingItems(project_id=project.id))
    overtime_id = next(i for i in items if i.preset == BillingItemPreset.OVERTIME_HOURS).id

    await bus.execute(
        SaveTimesheetWeek(
            user_id=user.id,
            week_start=A_MONDAY,
            changes=(
                TimeEntryChange(billing_item_id=normal_id, date=A_MONDAY, quantity=Decimal("20")),
            ),
        )
    )

    # Move 10 hours from normal to overtime in one batch: total stays 20, well within the limit,
    # even though the intermediate per-change state briefly would not be.
    updated = await bus.execute(
        SaveTimesheetWeek(
            user_id=user.id,
            week_start=A_MONDAY,
            changes=(
                TimeEntryChange(billing_item_id=normal_id, date=A_MONDAY, quantity=Decimal("10")),
                TimeEntryChange(billing_item_id=overtime_id, date=A_MONDAY, quantity=Decimal("10")),
            ),
        )
    )
    total_hours = sum(
        (entry.quantity for row in updated.rows for entry in row.entries), start=Decimal("0")
    )
    assert total_hours == Decimal("20.00")


async def test_list_timesheet_options_matches_member_projects(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user = await make_user()
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))

    options = await bus.query(ListTimesheetOptions(user_id=user.id))

    assert [option.project.id for option in options] == [project.id]


async def test_count_time_entries_filters(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user_a = await make_user()
    user_b = await make_user()
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user_a.id))
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user_b.id))
    item_id = await _normal_hours_item_id(bus, project.id)
    await bus.execute(
        SaveTimesheetWeek(
            user_id=user_a.id,
            week_start=A_MONDAY,
            changes=(
                TimeEntryChange(billing_item_id=item_id, date=A_MONDAY, quantity=Decimal("1")),
            ),
        )
    )
    await bus.execute(
        SaveTimesheetWeek(
            user_id=user_b.id,
            week_start=A_MONDAY,
            changes=(
                TimeEntryChange(billing_item_id=item_id, date=A_TUESDAY, quantity=Decimal("1")),
            ),
        )
    )

    assert await bus.query(CountTimeEntries(user_id=user_a.id)) == 1
    assert await bus.query(CountTimeEntries(project_id=project.id)) == 2
    assert await bus.query(CountTimeEntries(billing_item_id=item_id)) == 2
    assert await bus.query(CountTimeEntries(user_id=uuid4())) == 0


# --- Row comments ---


async def test_row_comment_is_created_updated_and_cleared(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user = await make_user()
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))
    item_id = await _normal_hours_item_id(bus, project.id)

    created = await bus.execute(
        SaveTimesheetWeek(
            user_id=user.id,
            week_start=A_MONDAY,
            changes=(),
            row_comments=(RowCommentChange(billing_item_id=item_id, comment="Please review"),),
        )
    )
    row = next(r for r in created.rows if r.billing_item.id == item_id)
    assert row.comment == "Please review"
    assert row.entries == ()

    updated = await bus.execute(
        SaveTimesheetWeek(
            user_id=user.id,
            week_start=A_MONDAY,
            changes=(),
            row_comments=(RowCommentChange(billing_item_id=item_id, comment="Updated note"),),
        )
    )
    row = next(r for r in updated.rows if r.billing_item.id == item_id)
    assert row.comment == "Updated note"

    cleared = await bus.execute(
        SaveTimesheetWeek(
            user_id=user.id,
            week_start=A_MONDAY,
            changes=(),
            row_comments=(RowCommentChange(billing_item_id=item_id, comment=None),),
        )
    )
    assert cleared.rows == ()


async def test_save_week_rejects_duplicate_row_comment(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user = await make_user()
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))
    item_id = await _normal_hours_item_id(bus, project.id)

    with pytest.raises(DuplicateChangeError):
        await bus.execute(
            SaveTimesheetWeek(
                user_id=user.id,
                week_start=A_MONDAY,
                changes=(),
                row_comments=(
                    RowCommentChange(billing_item_id=item_id, comment="a"),
                    RowCommentChange(billing_item_id=item_id, comment="b"),
                ),
            )
        )


async def test_deleting_every_cell_and_the_comment_removes_the_row(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user = await make_user()
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))
    item_id = await _normal_hours_item_id(bus, project.id)

    await bus.execute(
        SaveTimesheetWeek(
            user_id=user.id,
            week_start=A_MONDAY,
            changes=(
                TimeEntryChange(billing_item_id=item_id, date=A_MONDAY, quantity=Decimal("8")),
                TimeEntryChange(billing_item_id=item_id, date=A_TUESDAY, quantity=Decimal("8")),
            ),
            row_comments=(RowCommentChange(billing_item_id=item_id, comment="Sprint work"),),
        )
    )

    deleted = await bus.execute(
        SaveTimesheetWeek(
            user_id=user.id,
            week_start=A_MONDAY,
            changes=(
                TimeEntryChange(billing_item_id=item_id, date=A_MONDAY, quantity=None),
                TimeEntryChange(billing_item_id=item_id, date=A_TUESDAY, quantity=None),
            ),
            row_comments=(RowCommentChange(billing_item_id=item_id, comment=None),),
        )
    )
    assert deleted.rows == ()


# --- Submit / approve / return workflow ---


async def _member_worker_and_manager(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> tuple[UUID, UUID, UUID]:
    """A worker booked onto a project, plus its normal-hours item id and a project manager."""
    worker = await make_user(roles=EMPLOYEE)
    manager = await make_user(roles=MANAGER)
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=worker.id))
    item_id = await _normal_hours_item_id(bus, project.id)
    return worker.id, item_id, manager.id


async def test_submit_moves_draft_to_submitted_and_locks_editing(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    worker_id, item_id, _manager_id = await _member_worker_and_manager(bus, make_project, make_user)
    await bus.execute(
        SaveTimesheetWeek(
            user_id=worker_id,
            week_start=A_MONDAY,
            changes=(
                TimeEntryChange(billing_item_id=item_id, date=A_MONDAY, quantity=Decimal("8")),
            ),
        )
    )

    submitted = await bus.execute(SubmitTimesheetWeek(user_id=worker_id, week_start=A_MONDAY))

    assert submitted.status is TimesheetWeekStatus.SUBMITTED
    assert submitted.submitted_at is not None
    assert submitted.can_edit is False
    assert submitted.can_submit is False

    with pytest.raises(TimesheetWeekLockedError):
        await bus.execute(
            SaveTimesheetWeek(
                user_id=worker_id,
                week_start=A_MONDAY,
                changes=(
                    TimeEntryChange(billing_item_id=item_id, date=A_MONDAY, quantity=Decimal("1")),
                ),
            )
        )


async def test_submit_twice_is_rejected(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    worker_id, _item_id, _manager_id = await _member_worker_and_manager(
        bus, make_project, make_user
    )
    await bus.execute(SubmitTimesheetWeek(user_id=worker_id, week_start=A_MONDAY))

    with pytest.raises(InvalidWeekStatusTransitionError):
        await bus.execute(SubmitTimesheetWeek(user_id=worker_id, week_start=A_MONDAY))


async def test_approve_requires_submitted_status(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    worker_id, _item_id, manager_id = await _member_worker_and_manager(bus, make_project, make_user)

    with pytest.raises(InvalidWeekStatusTransitionError):
        await bus.execute(
            ApproveTimesheetWeek(user_id=worker_id, week_start=A_MONDAY, reviewer_id=manager_id)
        )


async def test_approve_then_return_workflow(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    worker_id, _item_id, manager_id = await _member_worker_and_manager(bus, make_project, make_user)
    await bus.execute(SubmitTimesheetWeek(user_id=worker_id, week_start=A_MONDAY))

    approved = await bus.execute(
        ApproveTimesheetWeek(user_id=worker_id, week_start=A_MONDAY, reviewer_id=manager_id)
    )
    assert approved.status is TimesheetWeekStatus.APPROVED
    assert approved.reviewed_at is not None

    returned = await bus.execute(
        ReturnTimesheetWeek(
            user_id=worker_id,
            week_start=A_MONDAY,
            reviewer_id=manager_id,
            comment="Please add the missing Friday hours",
        )
    )
    assert returned.status is TimesheetWeekStatus.RETURNED
    assert returned.return_comment == "Please add the missing Friday hours"

    # The command result reflects the reviewer's own view (can_edit is always False for someone
    # else's week); re-read as the owner to check the week is editable again after being returned.
    owner_view = await bus.query(
        GetTimesheetWeek(user_id=worker_id, week_start=A_MONDAY, viewer_id=worker_id)
    )
    assert owner_view.can_edit is True
    assert owner_view.can_submit is True


async def test_return_requires_a_non_blank_comment(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    worker_id, _item_id, manager_id = await _member_worker_and_manager(bus, make_project, make_user)
    await bus.execute(SubmitTimesheetWeek(user_id=worker_id, week_start=A_MONDAY))

    with pytest.raises(ReturnCommentRequiredError):
        await bus.execute(
            ReturnTimesheetWeek(
                user_id=worker_id, week_start=A_MONDAY, reviewer_id=manager_id, comment="   "
            )
        )


async def test_project_manager_cannot_review_their_own_week(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    manager = await make_user(roles=MANAGER)
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=manager.id))
    await bus.execute(SubmitTimesheetWeek(user_id=manager.id, week_start=A_MONDAY))

    with pytest.raises(SelfReviewError):
        await bus.execute(
            ApproveTimesheetWeek(user_id=manager.id, week_start=A_MONDAY, reviewer_id=manager.id)
        )


async def test_admin_can_review_their_own_week(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    admin = await make_user(roles=ADMIN)
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=admin.id))
    await bus.execute(SubmitTimesheetWeek(user_id=admin.id, week_start=A_MONDAY))

    approved = await bus.execute(
        ApproveTimesheetWeek(user_id=admin.id, week_start=A_MONDAY, reviewer_id=admin.id)
    )
    assert approved.status is TimesheetWeekStatus.APPROVED


async def test_can_review_reflects_role_and_status(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    worker_id, _item_id, manager_id = await _member_worker_and_manager(bus, make_project, make_user)
    other_worker = await make_user(roles=EMPLOYEE)

    draft_view = await bus.query(
        GetTimesheetWeek(user_id=worker_id, week_start=A_MONDAY, viewer_id=manager_id)
    )
    assert draft_view.can_review is False

    await bus.execute(SubmitTimesheetWeek(user_id=worker_id, week_start=A_MONDAY))

    manager_view = await bus.query(
        GetTimesheetWeek(user_id=worker_id, week_start=A_MONDAY, viewer_id=manager_id)
    )
    assert manager_view.can_review is True

    worker_view = await bus.query(
        GetTimesheetWeek(user_id=worker_id, week_start=A_MONDAY, viewer_id=other_worker.id)
    )
    assert worker_view.can_review is False


async def test_list_submitted_weeks_reports_totals(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    worker_id, item_id, _manager_id = await _member_worker_and_manager(bus, make_project, make_user)
    await bus.execute(
        SaveTimesheetWeek(
            user_id=worker_id,
            week_start=A_MONDAY,
            changes=(
                TimeEntryChange(billing_item_id=item_id, date=A_MONDAY, quantity=Decimal("8")),
            ),
        )
    )
    await bus.execute(SubmitTimesheetWeek(user_id=worker_id, week_start=A_MONDAY))

    summaries = await bus.query(ListSubmittedTimesheetWeeks())

    matching = next(s for s in summaries if s.user.id == worker_id)
    assert matching.status is TimesheetWeekStatus.SUBMITTED
    assert matching.week_start == A_MONDAY
    assert matching.total_hours == Decimal("8.00")
