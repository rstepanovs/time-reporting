"""`ExpenseAttachmentStorage` against a real temp directory, plus the bus-level
`AddExpenseAttachment`/`DeleteExpenseAttachment`/`GetAttachmentPath`/`ListAttachmentStorageKeys`
handlers with storage isolated to a temp directory via a patched `get_settings`.
"""

from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from support import MANAGER, ProjectFactory, UserFactory
from time_reporting.core.config import get_settings
from time_reporting.core.cqrs import Bus
from time_reporting.modules.expenses.contracts import (
    AddExpenseAttachment,
    ApproveExpenseReport,
    AttachmentNotFoundError,
    AttachmentTooLargeError,
    AttachmentTypeNotAllowedError,
    CreateExpenseReport,
    DeleteExpenseAttachment,
    DeleteExpenseReport,
    ExpenseLineChange,
    ExpenseLineNotFoundError,
    ExpenseReportDTO,
    ExpenseReportNotEditableError,
    ExpenseReportNotFoundError,
    GetAttachmentPath,
    GetExpenseReport,
    ListAttachmentStorageKeys,
    LockProjectMonthExpenseReports,
    SaveExpenseReportLines,
    SetAttachmentLine,
    SubmitExpenseReport,
)
from time_reporting.modules.expenses.storage import ExpenseAttachmentStorage
from time_reporting.modules.projects.contracts import (
    AddProjectMember,
    BillingItemPreset,
    ListProjectBillingItems,
)
from time_reporting.modules.users.contracts import UserDTO

YEAR = 2026
MONTH = 9

_PDF_BYTES = b"%PDF-1.4 not a real pdf, just needs content"


@pytest.fixture
def _isolated_attachments(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    patched = get_settings().model_copy(
        update={"attachment_dir": str(tmp_path), "attachment_max_bytes": 1024}
    )
    monkeypatch.setattr("time_reporting.modules.expenses.service.get_settings", lambda: patched)
    return tmp_path


def _storage(tmp_path: Path, *, max_bytes: int = 1024) -> ExpenseAttachmentStorage:
    settings = get_settings().model_copy(
        update={"attachment_dir": str(tmp_path), "attachment_max_bytes": max_bytes}
    )
    return ExpenseAttachmentStorage(settings)


# --- ExpenseAttachmentStorage (unit, no bus) ---


def test_save_writes_a_file_that_path_for_resolves(tmp_path: Path) -> None:
    storage = _storage(tmp_path)

    key = storage.save(content=_PDF_BYTES, content_type="application/pdf")

    path = storage.path_for(key)
    assert path is not None
    assert path.read_bytes() == _PDF_BYTES
    assert path.suffix == ".pdf"
    # Sharded one level deep by the key's own first two hex characters.
    assert path.parent.name == key.split("/")[0]


def test_save_rejects_disallowed_content_type(tmp_path: Path) -> None:
    storage = _storage(tmp_path)

    with pytest.raises(AttachmentTypeNotAllowedError):
        storage.save(content=_PDF_BYTES, content_type="application/zip")


def test_save_rejects_oversize_content(tmp_path: Path) -> None:
    storage = _storage(tmp_path, max_bytes=10)

    with pytest.raises(AttachmentTooLargeError):
        storage.save(content=_PDF_BYTES, content_type="application/pdf")


def test_path_for_rejects_traversal_and_malformed_keys(tmp_path: Path) -> None:
    storage = _storage(tmp_path)

    assert storage.path_for("../../etc/passwd") is None
    assert storage.path_for("/etc/passwd") is None
    assert storage.path_for("not-a-valid-key") is None
    assert storage.path_for("ab/" + "f" * 32 + ".exe.pdf") is None


def test_path_for_returns_none_for_a_missing_file(tmp_path: Path) -> None:
    storage = _storage(tmp_path)

    assert storage.path_for("ab/" + "0" * 32 + ".pdf") is None


def test_delete_unlinks_the_file(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    key = storage.save(content=_PDF_BYTES, content_type="application/pdf")

    storage.delete(key)

    assert storage.path_for(key) is None


def test_prune_orphans_removes_only_unreferenced_files(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    kept_key = storage.save(content=_PDF_BYTES, content_type="application/pdf")
    orphan_key = storage.save(content=_PDF_BYTES, content_type="image/png")

    removed_dry_run = storage.prune_orphans(referenced_keys=frozenset({kept_key}), dry_run=True)
    assert removed_dry_run == (orphan_key,)
    # Dry run touches nothing.
    assert storage.path_for(orphan_key) is not None

    removed = storage.prune_orphans(referenced_keys=frozenset({kept_key}), dry_run=False)
    assert removed == (orphan_key,)
    assert storage.path_for(kept_key) is not None
    assert storage.path_for(orphan_key) is None


# --- Bus-level handlers ---


async def _member_project_report(
    bus: Bus, make_project: ProjectFactory, make_user: UserFactory
) -> tuple[UserDTO, ExpenseReportDTO]:
    user = await make_user()
    project = await make_project()
    await bus.execute(AddProjectMember(project_id=project.id, user_id=user.id))
    report = await bus.execute(
        CreateExpenseReport(user_id=user.id, project_id=project.id, year=YEAR, month=MONTH)
    )
    return user, report


async def _add_line(bus: Bus, report: ExpenseReportDTO, actor_id: UUID) -> ExpenseReportDTO:
    """Add one line to ``report`` and return the refreshed report."""
    items = await bus.query(ListProjectBillingItems(project_id=report.project.id))
    item_id = next(
        item.id for item in items if item.preset == BillingItemPreset.PURCHASING_EXPENSES
    )
    return await bus.execute(
        SaveExpenseReportLines(
            report_id=report.id,
            actor_id=actor_id,
            lines=(
                ExpenseLineChange(
                    line_id=None,
                    billing_item_id=item_id,
                    expense_date=report.period_start,
                    amount=Decimal("50.00"),
                    description="Taxi",
                ),
            ),
        )
    )


async def test_add_attachment_stores_the_file_and_returns_metadata(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    _isolated_attachments: Path,
) -> None:
    user, report = await _member_project_report(bus, make_project, make_user)

    attachment = await bus.execute(
        AddExpenseAttachment(
            report_id=report.id,
            actor_id=user.id,
            file_name="receipt.pdf",
            content_type="application/pdf",
            content=_PDF_BYTES,
        )
    )

    assert attachment.file_name == "receipt.pdf"
    assert attachment.size_bytes == len(_PDF_BYTES)
    assert attachment.uploaded_by_name == user.name

    reread = await bus.query(GetExpenseReport(report_id=report.id, viewer_id=user.id))
    assert len(reread.attachments) == 1
    assert reread.attachments[0].id == attachment.id


async def test_add_attachment_rejects_oversize_upload(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    _isolated_attachments: Path,
) -> None:
    user, report = await _member_project_report(bus, make_project, make_user)

    with pytest.raises(AttachmentTooLargeError):
        await bus.execute(
            AddExpenseAttachment(
                report_id=report.id,
                actor_id=user.id,
                file_name="huge.pdf",
                content_type="application/pdf",
                content=b"x" * 2000,
            )
        )


async def test_add_attachment_rejects_disallowed_type(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    _isolated_attachments: Path,
) -> None:
    user, report = await _member_project_report(bus, make_project, make_user)

    with pytest.raises(AttachmentTypeNotAllowedError):
        await bus.execute(
            AddExpenseAttachment(
                report_id=report.id,
                actor_id=user.id,
                file_name="archive.zip",
                content_type="application/zip",
                content=b"PK\x03\x04",
            )
        )


async def test_delete_attachment_removes_row_and_file(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    _isolated_attachments: Path,
) -> None:
    user, report = await _member_project_report(bus, make_project, make_user)
    attachment = await bus.execute(
        AddExpenseAttachment(
            report_id=report.id,
            actor_id=user.id,
            file_name="receipt.pdf",
            content_type="application/pdf",
            content=_PDF_BYTES,
        )
    )

    await bus.execute(DeleteExpenseAttachment(attachment_id=attachment.id, actor_id=user.id))

    with pytest.raises(AttachmentNotFoundError):
        await bus.query(GetAttachmentPath(attachment_id=attachment.id, viewer_id=user.id))
    reread = await bus.query(GetExpenseReport(report_id=report.id, viewer_id=user.id))
    assert reread.attachments == ()


async def test_get_attachment_path_raises_for_unknown_id(
    bus: Bus, make_user: UserFactory, _isolated_attachments: Path
) -> None:
    user = await make_user()

    with pytest.raises(AttachmentNotFoundError):
        await bus.query(GetAttachmentPath(attachment_id=uuid4(), viewer_id=user.id))


async def test_add_attachment_rejects_on_a_deleted_report(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    _isolated_attachments: Path,
) -> None:
    user, report = await _member_project_report(bus, make_project, make_user)
    await bus.execute(DeleteExpenseReport(report_id=report.id, actor_id=user.id))

    with pytest.raises(ExpenseReportNotFoundError):
        await bus.execute(
            AddExpenseAttachment(
                report_id=report.id,
                actor_id=user.id,
                file_name="receipt.pdf",
                content_type="application/pdf",
                content=_PDF_BYTES,
            )
        )


async def test_list_attachment_storage_keys_reflects_saved_attachments(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    _isolated_attachments: Path,
) -> None:
    user, report = await _member_project_report(bus, make_project, make_user)
    assert await bus.query(ListAttachmentStorageKeys()) == frozenset()

    await bus.execute(
        AddExpenseAttachment(
            report_id=report.id,
            actor_id=user.id,
            file_name="receipt.pdf",
            content_type="application/pdf",
            content=_PDF_BYTES,
        )
    )

    keys = await bus.query(ListAttachmentStorageKeys())
    assert len(keys) == 1


# --- SetAttachmentLine / AddExpenseAttachment(line_id) ---


async def test_add_attachment_with_line_id_links_it_immediately(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    _isolated_attachments: Path,
) -> None:
    user, report = await _member_project_report(bus, make_project, make_user)
    report = await _add_line(bus, report, user.id)
    line_id = report.lines[0].id

    attachment = await bus.execute(
        AddExpenseAttachment(
            report_id=report.id,
            actor_id=user.id,
            file_name="receipt.pdf",
            content_type="application/pdf",
            content=_PDF_BYTES,
            line_id=line_id,
        )
    )

    assert attachment.line_id == line_id


async def test_add_attachment_rejects_a_foreign_line(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    _isolated_attachments: Path,
) -> None:
    user, report = await _member_project_report(bus, make_project, make_user)

    with pytest.raises(ExpenseLineNotFoundError):
        await bus.execute(
            AddExpenseAttachment(
                report_id=report.id,
                actor_id=user.id,
                file_name="receipt.pdf",
                content_type="application/pdf",
                content=_PDF_BYTES,
                line_id=uuid4(),
            )
        )


async def test_set_attachment_line_links_and_unlinks(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    _isolated_attachments: Path,
) -> None:
    user, report = await _member_project_report(bus, make_project, make_user)
    report = await _add_line(bus, report, user.id)
    line_id = report.lines[0].id
    attachment = await bus.execute(
        AddExpenseAttachment(
            report_id=report.id,
            actor_id=user.id,
            file_name="receipt.pdf",
            content_type="application/pdf",
            content=_PDF_BYTES,
        )
    )
    assert attachment.line_id is None

    linked = await bus.execute(
        SetAttachmentLine(attachment_id=attachment.id, actor_id=user.id, line_id=line_id)
    )
    assert linked.line_id == line_id

    unlinked = await bus.execute(
        SetAttachmentLine(attachment_id=attachment.id, actor_id=user.id, line_id=None)
    )
    assert unlinked.line_id is None


async def test_set_attachment_line_rejects_a_foreign_line(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    _isolated_attachments: Path,
) -> None:
    user, report = await _member_project_report(bus, make_project, make_user)
    attachment = await bus.execute(
        AddExpenseAttachment(
            report_id=report.id,
            actor_id=user.id,
            file_name="receipt.pdf",
            content_type="application/pdf",
            content=_PDF_BYTES,
        )
    )

    with pytest.raises(ExpenseLineNotFoundError):
        await bus.execute(
            SetAttachmentLine(attachment_id=attachment.id, actor_id=user.id, line_id=uuid4())
        )


async def test_set_attachment_line_rejects_when_report_is_locked(
    bus: Bus,
    make_project: ProjectFactory,
    make_user: UserFactory,
    _isolated_attachments: Path,
) -> None:
    user, report = await _member_project_report(bus, make_project, make_user)
    report = await _add_line(bus, report, user.id)
    line_id = report.lines[0].id
    attachment = await bus.execute(
        AddExpenseAttachment(
            report_id=report.id,
            actor_id=user.id,
            file_name="receipt.pdf",
            content_type="application/pdf",
            content=_PDF_BYTES,
        )
    )
    manager = await make_user(roles=MANAGER)
    await bus.execute(SubmitExpenseReport(report_id=report.id, actor_id=user.id))
    await bus.execute(ApproveExpenseReport(report_id=report.id, reviewer_id=manager.id))
    await bus.execute(
        LockProjectMonthExpenseReports(
            project_id=report.project.id, period_start=report.period_start
        )
    )

    # A locked report is always `approved`, so this surfaces as "not editable" (the status check
    # `_ensure_editable` runs first) rather than `ExpenseReportLockedError` — the same as
    # `SaveExpenseReportLines` on a locked report (see `test_lock_project_month_blocks_editing_
    # and_returning`).
    with pytest.raises(ExpenseReportNotEditableError):
        await bus.execute(
            SetAttachmentLine(attachment_id=attachment.id, actor_id=user.id, line_id=line_id)
        )
