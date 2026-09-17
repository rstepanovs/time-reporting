from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from support import ProjectFactory, UserFactory
from time_reporting.core.cqrs import Bus
from time_reporting.modules.expenses.contracts import (
    CreateExpenseReport,
    DeleteExpenseReport,
    ExpenseBillingItemNotFoundError,
    ExpenseDateOutsidePeriodError,
    ExpenseLineChange,
    ExpenseLineNotFoundError,
    ExpenseProjectClosedError,
    ExpenseReportAlreadyExistsError,
    ExpenseReportNotFoundError,
    ExpenseReportStatus,
    GetExpenseReport,
    SaveExpenseReportLines,
)
from time_reporting.modules.projects.contracts import (
    AddProjectMember,
    BillingItemPreset,
    ListProjectBillingItems,
    ProjectDTO,
    RemoveProjectMember,
    UpdateProject,
    UpdateProjectBillingItem,
)
from time_reporting.modules.users.contracts import UserDTO

# 2026-09 is the month under test throughout.
YEAR = 2026
MONTH = 9
PERIOD_START = date(2026, 9, 1)
PERIOD_END = date(2026, 9, 30)


async def _purchasing_item_id(bus: Bus, project_id: UUID) -> UUID:
    items = await bus.query(ListProjectBillingItems(project_id=project_id))
    return next(item.id for item in items if item.preset == BillingItemPreset.PURCHASING_EXPENSES)


async def _other_expenses_item_id(bus: Bus, project_id: UUID) -> UUID:
    items = await bus.query(ListProjectBillingItems(project_id=project_id))
    return next(item.id for item in items if item.preset == BillingItemPreset.OTHER_EXPENSES)


async def _member_project(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> tuple[UserDTO, ProjectDTO]:
    user = await make_user()
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))
    return user, project


# --- CreateExpenseReport ---


async def test_create_report_creates_an_empty_draft(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user, project = await _member_project(bus, make_project, make_user)

    report = await bus.execute(
        CreateExpenseReport(user_id=user.id, project_id=project.id, year=YEAR, month=MONTH)
    )

    assert report.status is ExpenseReportStatus.DRAFT
    assert report.period_start == PERIOD_START
    assert report.period_end == PERIOD_END
    assert report.lines == ()
    assert report.total == Decimal("0")
    assert report.can_edit is True
    assert report.can_submit is True
    assert report.can_review is False
    assert report.is_locked is False


async def test_create_report_rejects_duplicate_for_same_month(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user, project = await _member_project(bus, make_project, make_user)
    await bus.execute(
        CreateExpenseReport(user_id=user.id, project_id=project.id, year=YEAR, month=MONTH)
    )

    with pytest.raises(ExpenseReportAlreadyExistsError):
        await bus.execute(
            CreateExpenseReport(user_id=user.id, project_id=project.id, year=YEAR, month=MONTH)
        )


async def test_create_report_rejects_unknown_project(bus: Bus, make_user: UserFactory) -> None:
    user = await make_user()

    with pytest.raises(ExpenseProjectClosedError):
        await bus.execute(
            CreateExpenseReport(user_id=user.id, project_id=uuid4(), year=YEAR, month=MONTH)
        )


async def test_create_report_rejects_non_member(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user = await make_user()
    project = await make_project()

    with pytest.raises(ExpenseProjectClosedError):
        await bus.execute(
            CreateExpenseReport(user_id=user.id, project_id=project.id, year=YEAR, month=MONTH)
        )


async def test_create_report_rejects_archived_project(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user, project = await _member_project(bus, make_project, make_user)
    await bus.execute(UpdateProject(project_id=project.id, is_active=False))

    with pytest.raises(ExpenseProjectClosedError):
        await bus.execute(
            CreateExpenseReport(user_id=user.id, project_id=project.id, year=YEAR, month=MONTH)
        )


async def test_create_report_rejects_project_with_no_active_amount_items(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user, project = await _member_project(bus, make_project, make_user)
    for item in await bus.query(ListProjectBillingItems(project_id=project.id)):
        if item.unit.value == "amount":
            await bus.execute(
                UpdateProjectBillingItem(project_id=project.id, item_id=item.id, is_active=False)
            )

    with pytest.raises(ExpenseProjectClosedError):
        await bus.execute(
            CreateExpenseReport(user_id=user.id, project_id=project.id, year=YEAR, month=MONTH)
        )


# --- GetExpenseReport ---


async def test_get_report_raises_when_not_found(bus: Bus, make_user: UserFactory) -> None:
    user = await make_user()

    with pytest.raises(ExpenseReportNotFoundError):
        await bus.query(GetExpenseReport(report_id=uuid4(), viewer_id=user.id))


# --- SaveExpenseReportLines ---


async def test_save_lines_creates_updates_and_deletes_in_one_batch(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user, project = await _member_project(bus, make_project, make_user)
    purchasing_id = await _purchasing_item_id(bus, project.id)
    other_id = await _other_expenses_item_id(bus, project.id)
    report = await bus.execute(
        CreateExpenseReport(user_id=user.id, project_id=project.id, year=YEAR, month=MONTH)
    )

    created = await bus.execute(
        SaveExpenseReportLines(
            report_id=report.id,
            actor_id=user.id,
            lines=(
                ExpenseLineChange(
                    line_id=None,
                    billing_item_id=purchasing_id,
                    expense_date=date(2026, 9, 5),
                    amount=Decimal("42.50"),
                    description="Taxi",
                    vendor="City Cabs",
                    document_no="INV-1",
                ),
                ExpenseLineChange(
                    line_id=None,
                    billing_item_id=other_id,
                    expense_date=date(2026, 9, 6),
                    amount=Decimal("10.00"),
                    description="Parking",
                ),
            ),
        )
    )
    assert len(created.lines) == 2
    assert created.total == Decimal("52.50")
    taxi_line = next(line for line in created.lines if line.description == "Taxi")
    assert taxi_line.amount == Decimal("42.50")
    assert taxi_line.vendor == "City Cabs"
    assert taxi_line.document_no == "INV-1"

    updated = await bus.execute(
        SaveExpenseReportLines(
            report_id=report.id,
            actor_id=user.id,
            lines=(
                ExpenseLineChange(
                    line_id=taxi_line.id,
                    billing_item_id=purchasing_id,
                    expense_date=date(2026, 9, 5),
                    amount=Decimal("50.00"),
                    description="Taxi (updated)",
                ),
            ),
        )
    )
    updated_taxi = next(line for line in updated.lines if line.id == taxi_line.id)
    assert updated_taxi.amount == Decimal("50.00")
    assert updated_taxi.description == "Taxi (updated)"
    assert updated_taxi.vendor is None
    assert len(updated.lines) == 2

    parking_line = next(line for line in updated.lines if line.description == "Parking")
    final = await bus.execute(
        SaveExpenseReportLines(
            report_id=report.id,
            actor_id=user.id,
            lines=(),
            delete_line_ids=frozenset({parking_line.id}),
        )
    )
    assert len(final.lines) == 1
    assert final.total == Decimal("50.00")


async def test_save_lines_rejects_billing_item_not_open(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user, project = await _member_project(bus, make_project, make_user)
    report = await bus.execute(
        CreateExpenseReport(user_id=user.id, project_id=project.id, year=YEAR, month=MONTH)
    )

    with pytest.raises(ExpenseBillingItemNotFoundError):
        await bus.execute(
            SaveExpenseReportLines(
                report_id=report.id,
                actor_id=user.id,
                lines=(
                    ExpenseLineChange(
                        line_id=None,
                        billing_item_id=uuid4(),
                        expense_date=date(2026, 9, 5),
                        amount=Decimal("10"),
                        description="Unknown item",
                    ),
                ),
            )
        )


async def test_save_lines_rejects_hour_item(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user, project = await _member_project(bus, make_project, make_user)
    hour_items = await bus.query(ListProjectBillingItems(project_id=project.id))
    hour_item_id = next(item.id for item in hour_items if item.unit.value == "hour")
    report = await bus.execute(
        CreateExpenseReport(user_id=user.id, project_id=project.id, year=YEAR, month=MONTH)
    )

    with pytest.raises(ExpenseBillingItemNotFoundError):
        await bus.execute(
            SaveExpenseReportLines(
                report_id=report.id,
                actor_id=user.id,
                lines=(
                    ExpenseLineChange(
                        line_id=None,
                        billing_item_id=hour_item_id,
                        expense_date=date(2026, 9, 5),
                        amount=Decimal("10"),
                        description="Wrong unit",
                    ),
                ),
            )
        )


async def test_save_lines_rejects_date_outside_period(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user, project = await _member_project(bus, make_project, make_user)
    purchasing_id = await _purchasing_item_id(bus, project.id)
    report = await bus.execute(
        CreateExpenseReport(user_id=user.id, project_id=project.id, year=YEAR, month=MONTH)
    )

    with pytest.raises(ExpenseDateOutsidePeriodError):
        await bus.execute(
            SaveExpenseReportLines(
                report_id=report.id,
                actor_id=user.id,
                lines=(
                    ExpenseLineChange(
                        line_id=None,
                        billing_item_id=purchasing_id,
                        expense_date=date(2026, 10, 1),
                        amount=Decimal("10"),
                        description="Next month",
                    ),
                ),
            )
        )


async def test_save_lines_rejects_unknown_line_id(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user, project = await _member_project(bus, make_project, make_user)
    purchasing_id = await _purchasing_item_id(bus, project.id)
    report = await bus.execute(
        CreateExpenseReport(user_id=user.id, project_id=project.id, year=YEAR, month=MONTH)
    )

    with pytest.raises(ExpenseLineNotFoundError):
        await bus.execute(
            SaveExpenseReportLines(
                report_id=report.id,
                actor_id=user.id,
                lines=(
                    ExpenseLineChange(
                        line_id=uuid4(),
                        billing_item_id=purchasing_id,
                        expense_date=date(2026, 9, 5),
                        amount=Decimal("10"),
                        description="Ghost line",
                    ),
                ),
            )
        )


async def test_save_lines_batch_failing_midway_changes_nothing(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user, project = await _member_project(bus, make_project, make_user)
    purchasing_id = await _purchasing_item_id(bus, project.id)
    report = await bus.execute(
        CreateExpenseReport(user_id=user.id, project_id=project.id, year=YEAR, month=MONTH)
    )

    with pytest.raises(ExpenseDateOutsidePeriodError):
        await bus.execute(
            SaveExpenseReportLines(
                report_id=report.id,
                actor_id=user.id,
                lines=(
                    ExpenseLineChange(
                        line_id=None,
                        billing_item_id=purchasing_id,
                        expense_date=date(2026, 9, 5),
                        amount=Decimal("10"),
                        description="Valid one",
                    ),
                    ExpenseLineChange(
                        line_id=None,
                        billing_item_id=purchasing_id,
                        expense_date=date(2026, 10, 1),
                        amount=Decimal("10"),
                        description="Invalid one",
                    ),
                ),
            )
        )

    reread = await bus.query(GetExpenseReport(report_id=report.id, viewer_id=user.id))
    assert reread.lines == ()


async def test_save_lines_rejects_when_report_not_editable(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user, project = await _member_project(bus, make_project, make_user)
    report = await bus.execute(
        CreateExpenseReport(user_id=user.id, project_id=project.id, year=YEAR, month=MONTH)
    )
    await bus.execute(DeleteExpenseReport(report_id=report.id, actor_id=user.id))

    with pytest.raises(ExpenseReportNotFoundError):
        await bus.execute(SaveExpenseReportLines(report_id=report.id, actor_id=user.id, lines=()))


# --- DeleteExpenseReport ---


async def test_delete_report_removes_a_draft(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user, project = await _member_project(bus, make_project, make_user)
    report = await bus.execute(
        CreateExpenseReport(user_id=user.id, project_id=project.id, year=YEAR, month=MONTH)
    )

    await bus.execute(DeleteExpenseReport(report_id=report.id, actor_id=user.id))

    with pytest.raises(ExpenseReportNotFoundError):
        await bus.query(GetExpenseReport(report_id=report.id, viewer_id=user.id))


async def test_delete_report_raises_on_unknown_id(bus: Bus, make_user: UserFactory) -> None:
    user = await make_user()

    with pytest.raises(ExpenseReportNotFoundError):
        await bus.execute(DeleteExpenseReport(report_id=uuid4(), actor_id=user.id))


# --- Read-only once membership or the project is closed ---


async def test_report_stays_readable_after_project_archived(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user, project = await _member_project(bus, make_project, make_user)
    purchasing_id = await _purchasing_item_id(bus, project.id)
    report = await bus.execute(
        CreateExpenseReport(user_id=user.id, project_id=project.id, year=YEAR, month=MONTH)
    )
    await bus.execute(
        SaveExpenseReportLines(
            report_id=report.id,
            actor_id=user.id,
            lines=(
                ExpenseLineChange(
                    line_id=None,
                    billing_item_id=purchasing_id,
                    expense_date=date(2026, 9, 5),
                    amount=Decimal("10"),
                    description="Before archiving",
                ),
            ),
        )
    )

    await bus.execute(UpdateProject(project_id=project.id, is_active=False))

    reread = await bus.query(GetExpenseReport(report_id=report.id, viewer_id=user.id))
    assert len(reread.lines) == 1
    assert reread.can_edit is True  # status/lock based; archiving the project doesn't itself lock


async def test_report_stays_readable_after_membership_removed(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user, project = await _member_project(bus, make_project, make_user)
    report = await bus.execute(
        CreateExpenseReport(user_id=user.id, project_id=project.id, year=YEAR, month=MONTH)
    )
    await bus.execute(RemoveProjectMember(project_id=project.id, user_id=user.id))

    reread = await bus.query(GetExpenseReport(report_id=report.id, viewer_id=user.id))
    assert reread.id == report.id

    with pytest.raises(ExpenseBillingItemNotFoundError):
        await bus.execute(
            SaveExpenseReportLines(
                report_id=report.id,
                actor_id=user.id,
                lines=(
                    ExpenseLineChange(
                        line_id=None,
                        billing_item_id=await _purchasing_item_id(bus, project.id),
                        expense_date=date(2026, 9, 5),
                        amount=Decimal("10"),
                        description="No longer a member",
                    ),
                ),
            )
        )
