from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

from support import MANAGER, ProjectFactory, UserFactory
from time_reporting.core.cqrs import Bus
from time_reporting.modules.audit.contracts import AuditAction, ListAuditEvents
from time_reporting.modules.company.contracts import CompanyAddressDTO, UpdateCompanySettings
from time_reporting.modules.expenses.contracts import (
    ApproveExpenseReport,
    CreateExpenseReport,
    ExpenseLineChange,
    ExpenseReportLockedError,
    ExpenseReportNotEditableError,
    ExpenseReportStatus,
    ExpenseReturnCommentRequiredError,
    ExpenseSelfReviewError,
    GetExpenseReport,
    InvalidExpenseStatusTransitionError,
    ListProjectMonthExpenseReports,
    ListSubmittedExpenseReports,
    LockProjectMonthExpenseReports,
    ReturnExpenseReport,
    SaveExpenseReportLines,
    SubmitExpenseReport,
    UnlockProjectMonthExpenseReports,
)
from time_reporting.modules.projects.contracts import (
    AddProjectMember,
    BillingItemPreset,
    ListProjectBillingItems,
    ProjectDTO,
)
from time_reporting.modules.users.contracts import UserDTO

YEAR = 2026
MONTH = 9
PERIOD_START = date(2026, 9, 1)


async def _enable_self_review(bus: Bus, actor_id: UUID) -> None:
    await bus.execute(
        UpdateCompanySettings(
            actor_id=actor_id,
            legal_name="",
            org_number="",
            vat_number="",
            address=CompanyAddressDTO(street="", street2=None, postal_code="", city="", country=""),
            email="",
            phone="",
            registered_office="",
            bankgiro="",
            iban="",
            bic="",
            f_tax_approved=False,
            default_invoice_locale="sv",
            late_interest="",
            invoice_number_prefix="",
            next_invoice_number=1,
            customer_number_prefix="",
            next_customer_number=1,
            allow_self_review=True,
        )
    )


async def _purchasing_item_id(bus: Bus, project_id: UUID) -> UUID:
    items = await bus.query(ListProjectBillingItems(project_id=project_id))
    return next(item.id for item in items if item.preset == BillingItemPreset.PURCHASING_EXPENSES)


async def _member_project(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    *,
    manager_id: UUID | None = None,
    is_internal: bool = False,
) -> tuple[UserDTO, ProjectDTO]:
    user = await make_user()
    project = await make_project(manager_id=manager_id, is_internal=is_internal)
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))
    return user, project


async def test_report_on_an_internal_project_works_end_to_end(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    """`expenses` doesn't look at `Project.is_internal` at all — the workflow, and the eventual
    lock from a billing handoff, are entirely unaffected since an internal project's month can
    never be sent to billing in the first place (see `timesheets.ProjectIsInternalError`)."""
    manager = await make_user(roles=MANAGER)
    user, project = await _member_project(
        bus, make_project, make_user, manager_id=manager.id, is_internal=True
    )
    item_id = await _purchasing_item_id(bus, project.id)
    report = await bus.execute(
        CreateExpenseReport(user_id=user.id, project_id=project.id, year=YEAR, month=MONTH)
    )
    report = await bus.execute(
        SaveExpenseReportLines(
            report_id=report.id,
            actor_id=user.id,
            lines=(
                ExpenseLineChange(
                    line_id=None,
                    billing_item_id=item_id,
                    expense_date=date(2026, 9, 10),
                    amount=Decimal("42.00"),
                    description="Taxi",
                    vendor=None,
                    document_no=None,
                ),
            ),
        )
    )
    assert report.total == Decimal("42.00")

    submitted = await bus.execute(SubmitExpenseReport(report_id=report.id, actor_id=user.id))
    assert submitted.status is ExpenseReportStatus.SUBMITTED

    approved = await bus.execute(ApproveExpenseReport(report_id=report.id, reviewer_id=manager.id))
    assert approved.status is ExpenseReportStatus.APPROVED
    assert approved.is_locked is False


# --- SubmitExpenseReport ---


async def test_submit_report_moves_draft_to_submitted(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user, project = await _member_project(bus, make_project, make_user)
    report = await bus.execute(
        CreateExpenseReport(user_id=user.id, project_id=project.id, year=YEAR, month=MONTH)
    )

    submitted = await bus.execute(SubmitExpenseReport(report_id=report.id, actor_id=user.id))

    assert submitted.status is ExpenseReportStatus.SUBMITTED
    assert submitted.submitted_at is not None
    assert submitted.can_edit is False


async def test_submit_report_rejects_already_submitted(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user, project = await _member_project(bus, make_project, make_user)
    report = await bus.execute(
        CreateExpenseReport(user_id=user.id, project_id=project.id, year=YEAR, month=MONTH)
    )
    await bus.execute(SubmitExpenseReport(report_id=report.id, actor_id=user.id))

    with pytest.raises(InvalidExpenseStatusTransitionError):
        await bus.execute(SubmitExpenseReport(report_id=report.id, actor_id=user.id))


# --- ApproveExpenseReport ---


async def test_approve_report_moves_submitted_to_approved_and_records_audit_event(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user, project = await _member_project(bus, make_project, make_user)
    manager = await make_user(roles=MANAGER)
    report = await bus.execute(
        CreateExpenseReport(user_id=user.id, project_id=project.id, year=YEAR, month=MONTH)
    )
    await bus.execute(SubmitExpenseReport(report_id=report.id, actor_id=user.id))

    approved = await bus.execute(ApproveExpenseReport(report_id=report.id, reviewer_id=manager.id))

    assert approved.status is ExpenseReportStatus.APPROVED
    assert approved.reviewed_by_name == manager.name

    events = await bus.query(
        ListAuditEvents(
            limit=10,
            offset=0,
            action=AuditAction.EXPENSE_REPORT_APPROVED,
            entity_type="expense_report",
            entity_id=str(report.id),
        )
    )
    assert len(events.items) == 1
    assert events.items[0].actor_id == manager.id


async def test_approve_report_rejects_self_review(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user, project = await _member_project(bus, make_project, make_user)
    report = await bus.execute(
        CreateExpenseReport(user_id=user.id, project_id=project.id, year=YEAR, month=MONTH)
    )
    await bus.execute(SubmitExpenseReport(report_id=report.id, actor_id=user.id))

    with pytest.raises(ExpenseSelfReviewError):
        await bus.execute(ApproveExpenseReport(report_id=report.id, reviewer_id=user.id))


async def test_approve_report_self_review_allowed_when_setting_is_on(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    manager = await make_user(roles=MANAGER)
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=manager.id))
    await _enable_self_review(bus, manager.id)
    report = await bus.execute(
        CreateExpenseReport(user_id=manager.id, project_id=project.id, year=YEAR, month=MONTH)
    )
    await bus.execute(SubmitExpenseReport(report_id=report.id, actor_id=manager.id))

    approved = await bus.execute(ApproveExpenseReport(report_id=report.id, reviewer_id=manager.id))

    assert approved.status is ExpenseReportStatus.APPROVED

    events = await bus.query(
        ListAuditEvents(
            limit=10,
            offset=0,
            action=AuditAction.EXPENSE_REPORT_APPROVED,
            entity_type="expense_report",
            entity_id=str(report.id),
        )
    )
    assert events.items[0].details == {"self_review": True}


async def test_approve_report_self_review_still_refused_for_a_non_manager_owner(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user, project = await _member_project(bus, make_project, make_user)
    await _enable_self_review(bus, user.id)
    report = await bus.execute(
        CreateExpenseReport(user_id=user.id, project_id=project.id, year=YEAR, month=MONTH)
    )
    await bus.execute(SubmitExpenseReport(report_id=report.id, actor_id=user.id))

    with pytest.raises(ExpenseSelfReviewError):
        await bus.execute(ApproveExpenseReport(report_id=report.id, reviewer_id=user.id))


async def test_approve_report_rejects_draft(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user, project = await _member_project(bus, make_project, make_user)
    manager = await make_user(roles=MANAGER)
    report = await bus.execute(
        CreateExpenseReport(user_id=user.id, project_id=project.id, year=YEAR, month=MONTH)
    )

    with pytest.raises(InvalidExpenseStatusTransitionError):
        await bus.execute(ApproveExpenseReport(report_id=report.id, reviewer_id=manager.id))


# --- ReturnExpenseReport ---


async def test_return_report_moves_submitted_to_returned_and_records_audit_event(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user, project = await _member_project(bus, make_project, make_user)
    manager = await make_user(roles=MANAGER)
    report = await bus.execute(
        CreateExpenseReport(user_id=user.id, project_id=project.id, year=YEAR, month=MONTH)
    )
    await bus.execute(SubmitExpenseReport(report_id=report.id, actor_id=user.id))

    returned = await bus.execute(
        ReturnExpenseReport(report_id=report.id, reviewer_id=manager.id, comment="Missing receipt")
    )

    assert returned.status is ExpenseReportStatus.RETURNED
    assert returned.return_comment == "Missing receipt"

    # The DTO reflects the reviewer's own view (they just acted as viewer); the owner's can_edit
    # is confirmed separately by re-reading as the owner.
    reread_by_owner = await bus.query(GetExpenseReport(report_id=report.id, viewer_id=user.id))
    assert reread_by_owner.can_edit is True

    events = await bus.query(
        ListAuditEvents(
            limit=10,
            offset=0,
            action=AuditAction.EXPENSE_REPORT_RETURNED,
            entity_type="expense_report",
            entity_id=str(report.id),
        )
    )
    assert len(events.items) == 1
    assert events.items[0].actor_id == manager.id


async def test_return_report_requires_a_comment(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user, project = await _member_project(bus, make_project, make_user)
    manager = await make_user(roles=MANAGER)
    report = await bus.execute(
        CreateExpenseReport(user_id=user.id, project_id=project.id, year=YEAR, month=MONTH)
    )
    await bus.execute(SubmitExpenseReport(report_id=report.id, actor_id=user.id))

    with pytest.raises(ExpenseReturnCommentRequiredError):
        await bus.execute(
            ReturnExpenseReport(report_id=report.id, reviewer_id=manager.id, comment="   ")
        )


async def test_return_report_rejects_self_review(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user, project = await _member_project(bus, make_project, make_user)
    report = await bus.execute(
        CreateExpenseReport(user_id=user.id, project_id=project.id, year=YEAR, month=MONTH)
    )
    await bus.execute(SubmitExpenseReport(report_id=report.id, actor_id=user.id))

    with pytest.raises(ExpenseSelfReviewError):
        await bus.execute(
            ReturnExpenseReport(report_id=report.id, reviewer_id=user.id, comment="Nope")
        )


async def test_return_report_self_review_allowed_when_setting_is_on(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    manager = await make_user(roles=MANAGER)
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=manager.id))
    await _enable_self_review(bus, manager.id)
    report = await bus.execute(
        CreateExpenseReport(user_id=manager.id, project_id=project.id, year=YEAR, month=MONTH)
    )
    await bus.execute(SubmitExpenseReport(report_id=report.id, actor_id=manager.id))

    returned = await bus.execute(
        ReturnExpenseReport(report_id=report.id, reviewer_id=manager.id, comment="Fix this")
    )

    assert returned.status is ExpenseReportStatus.RETURNED

    events = await bus.query(
        ListAuditEvents(
            limit=10,
            offset=0,
            action=AuditAction.EXPENSE_REPORT_RETURNED,
            entity_type="expense_report",
            entity_id=str(report.id),
        )
    )
    assert events.items[0].details == {"comment": "Fix this", "self_review": True}


async def test_return_report_self_review_still_refused_for_a_non_manager_owner(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user, project = await _member_project(bus, make_project, make_user)
    await _enable_self_review(bus, user.id)
    report = await bus.execute(
        CreateExpenseReport(user_id=user.id, project_id=project.id, year=YEAR, month=MONTH)
    )
    await bus.execute(SubmitExpenseReport(report_id=report.id, actor_id=user.id))

    with pytest.raises(ExpenseSelfReviewError):
        await bus.execute(
            ReturnExpenseReport(report_id=report.id, reviewer_id=user.id, comment="Nope")
        )


async def test_can_review_reflects_self_review_setting(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    manager = await make_user(roles=MANAGER)
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=manager.id))
    report = await bus.execute(
        CreateExpenseReport(user_id=manager.id, project_id=project.id, year=YEAR, month=MONTH)
    )
    await bus.execute(SubmitExpenseReport(report_id=report.id, actor_id=manager.id))

    off_view = await bus.query(GetExpenseReport(report_id=report.id, viewer_id=manager.id))
    assert off_view.can_review is False

    await _enable_self_review(bus, manager.id)

    on_view = await bus.query(GetExpenseReport(report_id=report.id, viewer_id=manager.id))
    assert on_view.can_review is True


async def test_return_report_also_works_from_approved(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user, project = await _member_project(bus, make_project, make_user)
    manager = await make_user(roles=MANAGER)
    report = await bus.execute(
        CreateExpenseReport(user_id=user.id, project_id=project.id, year=YEAR, month=MONTH)
    )
    await bus.execute(SubmitExpenseReport(report_id=report.id, actor_id=user.id))
    await bus.execute(ApproveExpenseReport(report_id=report.id, reviewer_id=manager.id))

    returned = await bus.execute(
        ReturnExpenseReport(report_id=report.id, reviewer_id=manager.id, comment="On second look")
    )

    assert returned.status is ExpenseReportStatus.RETURNED


# --- Lock / unlock ---


async def test_lock_project_month_blocks_editing_and_returning(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user, project = await _member_project(bus, make_project, make_user)
    manager = await make_user(roles=MANAGER)
    report = await bus.execute(
        CreateExpenseReport(user_id=user.id, project_id=project.id, year=YEAR, month=MONTH)
    )
    await bus.execute(SubmitExpenseReport(report_id=report.id, actor_id=user.id))
    await bus.execute(ApproveExpenseReport(report_id=report.id, reviewer_id=manager.id))

    await bus.execute(
        LockProjectMonthExpenseReports(project_id=project.id, period_start=PERIOD_START)
    )

    locked = await bus.query(GetExpenseReport(report_id=report.id, viewer_id=user.id))
    assert locked.is_locked is True
    assert locked.can_edit is False
    assert locked.can_review is False

    with pytest.raises(ExpenseReportLockedError):
        await bus.execute(
            ReturnExpenseReport(report_id=report.id, reviewer_id=manager.id, comment="Too late")
        )
    with pytest.raises(ExpenseReportNotEditableError):
        await bus.execute(SaveExpenseReportLines(report_id=report.id, actor_id=user.id, lines=()))


async def test_unlock_project_month_restores_editing_and_returning(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    user, project = await _member_project(bus, make_project, make_user)
    manager = await make_user(roles=MANAGER)
    report = await bus.execute(
        CreateExpenseReport(user_id=user.id, project_id=project.id, year=YEAR, month=MONTH)
    )
    await bus.execute(SubmitExpenseReport(report_id=report.id, actor_id=user.id))
    await bus.execute(ApproveExpenseReport(report_id=report.id, reviewer_id=manager.id))
    await bus.execute(
        LockProjectMonthExpenseReports(project_id=project.id, period_start=PERIOD_START)
    )

    await bus.execute(
        UnlockProjectMonthExpenseReports(project_id=project.id, period_start=PERIOD_START)
    )

    unlocked = await bus.query(GetExpenseReport(report_id=report.id, viewer_id=user.id))
    assert unlocked.is_locked is False

    returned = await bus.execute(
        ReturnExpenseReport(report_id=report.id, reviewer_id=manager.id, comment="Now it's fine")
    )
    assert returned.status is ExpenseReportStatus.RETURNED


# --- ListSubmittedExpenseReports ---


async def test_list_submitted_expense_reports_filters_by_manager(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    manager = await make_user(roles=MANAGER)
    other_manager = await make_user(roles=MANAGER)
    user, managed_project = await _member_project(
        bus, make_project, make_user, manager_id=manager.id
    )
    other_user, other_project = await _member_project(
        bus, make_project, make_user, manager_id=other_manager.id
    )

    managed_report = await bus.execute(
        CreateExpenseReport(user_id=user.id, project_id=managed_project.id, year=YEAR, month=MONTH)
    )
    await bus.execute(SubmitExpenseReport(report_id=managed_report.id, actor_id=user.id))
    other_report = await bus.execute(
        CreateExpenseReport(
            user_id=other_user.id, project_id=other_project.id, year=YEAR, month=MONTH
        )
    )
    await bus.execute(SubmitExpenseReport(report_id=other_report.id, actor_id=other_user.id))

    scoped = await bus.query(ListSubmittedExpenseReports(manager_id=manager.id))
    assert [summary.id for summary in scoped] == [managed_report.id]

    unscoped = await bus.query(ListSubmittedExpenseReports())
    assert {summary.id for summary in unscoped} == {managed_report.id, other_report.id}


# --- ListProjectMonthExpenseReports ---


async def test_list_project_month_expense_reports_returns_totals(
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
                    amount=Decimal("15.00"),
                    description="Snacks",
                ),
            ),
        )
    )

    summaries = await bus.query(
        ListProjectMonthExpenseReports(
            project_ids=frozenset({project.id}), period_start=PERIOD_START
        )
    )

    assert len(summaries) == 1
    assert summaries[0].id == report.id
    assert summaries[0].total == Decimal("15.00")
    assert summaries[0].line_count == 1


async def test_list_project_month_expense_reports_empty_for_unknown_month(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> None:
    _, project = await _member_project(bus, make_project, make_user)

    summaries = await bus.query(
        ListProjectMonthExpenseReports(
            project_ids=frozenset({project.id}), period_start=date(2020, 1, 1)
        )
    )

    assert summaries == ()
