"""`BackupService` against a stubbed `asyncio.create_subprocess_exec`, so these tests never touch
a real `pg_dump`/`pg_restore`; one test at the bottom runs a real `pg_dump` and is skipped when the
binary isn't on `PATH`.
"""

import asyncio
import shutil
import tarfile
from pathlib import Path
from typing import Any

import pytest

from time_reporting.core.config import Settings, get_settings
from time_reporting.modules.system.backup_service import BackupService
from time_reporting.modules.system.contracts import (
    BackupFailedError,
    BackupInProgressError,
    BackupNotFoundError,
)

_REVISION = "0123456789ab"


def _settings(
    tmp_path: Path,
    *,
    retention: int = 2,
    timeout: int = 5,
    attachment_dir: Path | None = None,
) -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://time_reporting:s3cret@localhost:5432/time_reporting",
        backup_dir=str(tmp_path),
        backup_retention_count=retention,
        backup_timeout_seconds=timeout,
        # A guaranteed-nonexistent default, distinct from `backup_dir`, so a test that doesn't
        # care about attachments never accidentally touches a real directory.
        attachment_dir=str(attachment_dir) if attachment_dir else str(tmp_path / "no-attachments"),
    )


def _touch_backup(directory: Path, *, timestamp: str, revision: str = _REVISION) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"time-reporting-{timestamp}-{revision}.dump"
    path.write_bytes(b"not a real dump, just needs a nonzero size")
    return path


def _names_in(directory: Path) -> set[str]:
    """A plain (non-async) helper, so tests can inspect the filesystem without ruff's ASYNC240
    flagging blocking `pathlib` calls made directly inside an `async def` test."""
    return {p.name for p in directory.iterdir()}


def _file_size(path: Path) -> int:
    return path.stat().st_size


def _create_lock_file(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / ".backup.lock").touch()


class _FakeProcess:
    def __init__(self, returncode: int, stderr: bytes = b"", *, hang: bool = False) -> None:
        self.returncode = returncode
        self._stderr = stderr
        self._hang = hang
        self.killed = False

    async def communicate(self) -> tuple[bytes, bytes]:
        if self._hang:
            await asyncio.sleep(10)
        return b"", self._stderr

    def kill(self) -> None:
        self.killed = True

    async def wait(self) -> int:
        return self.returncode


def _stub_subprocess(
    monkeypatch: pytest.MonkeyPatch, process: _FakeProcess
) -> list[tuple[Any, ...]]:
    calls: list[tuple[Any, ...]] = []

    async def fake_create_subprocess_exec(*args: Any, **_kwargs: Any) -> _FakeProcess:
        calls.append(args)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    return calls


# --- create(): success, failure cleanup, timeout, the concurrency lock ---


async def test_create_writes_a_dump_named_with_timestamp_and_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _stub_subprocess(monkeypatch, _FakeProcess(returncode=0))
    service = BackupService(_settings(tmp_path))

    backup = await service.create(revision=_REVISION)

    assert backup.revision == _REVISION
    assert backup.name.endswith(f"-{_REVISION}.dump")
    assert backup.size_bytes == _file_size(tmp_path / backup.name)
    assert calls[0][0] == "pg_dump"
    assert _names_in(tmp_path) == {backup.name}


async def test_create_cleans_up_and_raises_on_a_nonzero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_subprocess(
        monkeypatch, _FakeProcess(returncode=1, stderr=b"pg_dump: error: could not connect")
    )
    service = BackupService(_settings(tmp_path))

    with pytest.raises(BackupFailedError):
        await service.create(revision=_REVISION)

    assert _names_in(tmp_path) == set()


async def test_create_kills_the_process_and_raises_on_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    process = _FakeProcess(returncode=0, hang=True)
    _stub_subprocess(monkeypatch, process)
    service = BackupService(_settings(tmp_path, timeout=1))

    with pytest.raises(BackupFailedError):
        await service.create(revision=_REVISION)

    assert process.killed
    assert _names_in(tmp_path) == set()


async def test_create_raises_when_a_backup_is_already_in_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_subprocess(monkeypatch, _FakeProcess(returncode=0))
    service = BackupService(_settings(tmp_path))
    _create_lock_file(tmp_path)

    with pytest.raises(BackupInProgressError):
        await service.create(revision=_REVISION)


async def test_create_archives_attachments_when_the_directory_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_subprocess(monkeypatch, _FakeProcess(returncode=0))
    attachment_dir = tmp_path / "attachments"
    (attachment_dir / "ab").mkdir(parents=True)
    (attachment_dir / "ab" / "receipt.pdf").write_bytes(b"a fake pdf")
    service = BackupService(_settings(tmp_path, attachment_dir=attachment_dir))

    backup = await service.create(revision=_REVISION)

    assert backup.attachments_size_bytes is not None
    assert backup.attachments_size_bytes > 0
    archive_path = tmp_path / f"{backup.name.removesuffix('.dump')}-attachments.tar.gz"
    assert archive_path.is_file()
    assert archive_path.stat().st_size == backup.attachments_size_bytes


async def test_create_has_no_archive_when_the_attachment_directory_does_not_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_subprocess(monkeypatch, _FakeProcess(returncode=0))
    service = BackupService(_settings(tmp_path))

    backup = await service.create(revision=_REVISION)

    assert backup.attachments_size_bytes is None
    assert _names_in(tmp_path) == {backup.name}


# --- list() / last_backup_at() / prune() ---


def test_list_is_sorted_newest_first(tmp_path: Path) -> None:
    service = BackupService(_settings(tmp_path))
    _touch_backup(tmp_path, timestamp="20260101T000000Z")
    _touch_backup(tmp_path, timestamp="20260103T000000Z")
    _touch_backup(tmp_path, timestamp="20260102T000000Z")

    names = [backup.name for backup in service.list()]

    assert names == [
        f"time-reporting-20260103T000000Z-{_REVISION}.dump",
        f"time-reporting-20260102T000000Z-{_REVISION}.dump",
        f"time-reporting-20260101T000000Z-{_REVISION}.dump",
    ]


def test_last_backup_at_is_the_newest_backups_timestamp(tmp_path: Path) -> None:
    service = BackupService(_settings(tmp_path))
    _touch_backup(tmp_path, timestamp="20260101T000000Z")
    _touch_backup(tmp_path, timestamp="20260103T000000Z")

    assert service.last_backup_at() == service.list()[0].created_at


def test_list_and_last_backup_at_are_empty_without_a_backup_dir(tmp_path: Path) -> None:
    service = BackupService(_settings(tmp_path / "does-not-exist"))

    assert service.list() == ()
    assert service.last_backup_at() is None


def test_prune_keeps_only_the_newest_retention_count(tmp_path: Path) -> None:
    service = BackupService(_settings(tmp_path, retention=2))
    _touch_backup(tmp_path, timestamp="20260101T000000Z")
    _touch_backup(tmp_path, timestamp="20260102T000000Z")
    _touch_backup(tmp_path, timestamp="20260103T000000Z")

    service.prune()

    assert {backup.name for backup in service.list()} == {
        f"time-reporting-20260103T000000Z-{_REVISION}.dump",
        f"time-reporting-20260102T000000Z-{_REVISION}.dump",
    }


def test_prune_deletes_a_stale_backups_attachments_archive_too(tmp_path: Path) -> None:
    service = BackupService(_settings(tmp_path, retention=1))
    stale = _touch_backup(tmp_path, timestamp="20260101T000000Z")
    stale_archive = tmp_path / f"{stale.name.removesuffix('.dump')}-attachments.tar.gz"
    stale_archive.write_bytes(b"a fake archive")
    _touch_backup(tmp_path, timestamp="20260102T000000Z")

    service.prune()

    assert not stale_archive.exists()


# --- path_for(): the only way a name from a URL becomes a filesystem path ---


def test_path_for_resolves_an_existing_backup(tmp_path: Path) -> None:
    service = BackupService(_settings(tmp_path))
    backup_path = _touch_backup(tmp_path, timestamp="20260101T000000Z")

    assert service.path_for(backup_path.name) == backup_path


def test_path_for_rejects_a_path_traversal_attempt(tmp_path: Path) -> None:
    service = BackupService(_settings(tmp_path))

    with pytest.raises(BackupNotFoundError):
        service.path_for("../../../etc/passwd")


def test_path_for_rejects_a_well_formed_name_that_does_not_exist(tmp_path: Path) -> None:
    service = BackupService(_settings(tmp_path))

    with pytest.raises(BackupNotFoundError):
        service.path_for(f"time-reporting-20260101T000000Z-{_REVISION}.dump")


def test_path_for_resolves_an_attachments_archive(tmp_path: Path) -> None:
    service = BackupService(_settings(tmp_path))
    archive_path = tmp_path / f"time-reporting-20260101T000000Z-{_REVISION}-attachments.tar.gz"
    archive_path.write_bytes(b"a fake archive")

    assert service.path_for(archive_path.name) == archive_path


# --- restore() ---


async def test_restore_raises_on_a_nonzero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_subprocess(monkeypatch, _FakeProcess(returncode=1, stderr=b"pg_restore: error"))
    service = BackupService(_settings(tmp_path))

    with pytest.raises(BackupFailedError):
        await service.restore(tmp_path / "some-backup.dump")


async def test_restore_extracts_a_matching_attachments_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_subprocess(monkeypatch, _FakeProcess(returncode=0))
    dump_name = f"time-reporting-20260101T000000Z-{_REVISION}.dump"
    dump_path = tmp_path / dump_name
    dump_path.write_bytes(b"not a real dump")
    archive_path = tmp_path / f"{dump_name.removesuffix('.dump')}-attachments.tar.gz"
    source_dir = tmp_path / "archive-source"
    (source_dir / "ab").mkdir(parents=True)
    (source_dir / "ab" / "receipt.pdf").write_bytes(b"a fake pdf")
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(source_dir, arcname=".")
    # A stale file from before the restore, to confirm the attachment directory is replaced
    # rather than merged into.
    attachment_dir = tmp_path / "attachments"
    attachment_dir.mkdir()
    (attachment_dir / "stale.pdf").write_bytes(b"should be gone after restore")
    service = BackupService(_settings(tmp_path, attachment_dir=attachment_dir))

    await service.restore(dump_path)

    assert not (attachment_dir / "stale.pdf").exists()
    assert (attachment_dir / "ab" / "receipt.pdf").read_bytes() == b"a fake pdf"


async def test_restore_warns_but_does_not_raise_without_a_matching_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _stub_subprocess(monkeypatch, _FakeProcess(returncode=0))
    dump_path = tmp_path / f"time-reporting-20260101T000000Z-{_REVISION}.dump"
    dump_path.write_bytes(b"not a real dump")
    service = BackupService(_settings(tmp_path))

    await service.restore(dump_path)

    assert "No attachments archive found" in caplog.text


# --- a real pg_dump, when available ---


@pytest.mark.skipif(shutil.which("pg_dump") is None, reason="pg_dump is not on PATH")
async def test_create_runs_a_real_pg_dump(tmp_path: Path) -> None:
    service = BackupService(
        Settings(database_url=get_settings().database_url, backup_dir=str(tmp_path))
    )

    backup = await service.create(revision=_REVISION)

    assert (tmp_path / backup.name).stat().st_size > 0
