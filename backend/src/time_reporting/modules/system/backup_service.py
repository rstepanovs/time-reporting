"""`pg_dump`/`pg_restore` orchestration, plus a matching tar archive of expense-report attachments
taken alongside each dump. No ORM/session use — backups run as a subprocess against the same
database the app's `DATABASE_URL` points at, entirely independent of the CQRS bus's request-scoped
session.
"""

import asyncio
import logging
import os
import re
import tarfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.engine import make_url

from time_reporting.core.config import Settings
from time_reporting.modules.system.contracts import (
    BackupFailedError,
    BackupInfoDTO,
    BackupInProgressError,
    BackupNotFoundError,
)

logger = logging.getLogger(__name__)

_TIMESTAMP_FORMAT = "%Y%m%dT%H%M%SZ"
_DUMP_PATTERN = re.compile(
    r"^time-reporting-(?P<timestamp>\d{8}T\d{6}Z)-(?P<revision>[0-9a-f]{12}|unknown)\.dump$"
)
_ATTACHMENTS_SUFFIX = "-attachments.tar.gz"
_ARCHIVE_PATTERN = re.compile(
    r"^time-reporting-(?P<timestamp>\d{8}T\d{6}Z)-(?P<revision>[0-9a-f]{12}|unknown)"
    r"-attachments\.tar\.gz$"
)
_LOCK_FILE_NAME = ".backup.lock"
# Kept out of the raised exception (which the API returns to the client) but logged in full up to
# this many trailing characters, since pg_dump/pg_restore stderr can be long-winded.
_STDERR_TAIL_CHARS = 4000


def parse_backup_filename(name: str) -> tuple[datetime, str | None] | None:
    """The dump's creation time and recorded revision, or `None` if `name` isn't a `.dump` file
    name this service produced — also doubles as the name-validation check against path
    traversal, since a valid match can only ever resolve inside `backup_dir`. Does not match the
    attachments archive; see `_parse_any_backup_filename` for a download/delete path that accepts
    either."""
    match = _DUMP_PATTERN.fullmatch(name)
    if match is None:
        return None
    created_at = datetime.strptime(match.group("timestamp"), _TIMESTAMP_FORMAT).replace(tzinfo=UTC)
    revision = match.group("revision")
    return created_at, None if revision == "unknown" else revision


def _parse_any_backup_filename(name: str) -> bool:
    """Whether `name` is a `.dump` or `-attachments.tar.gz` file name this service produced — the
    validation `path_for` uses, since either half of a backup pair may be requested on its own."""
    return _DUMP_PATTERN.fullmatch(name) is not None or _ARCHIVE_PATTERN.fullmatch(name) is not None


def _build_filename(created_at: datetime, revision: str | None) -> str:
    timestamp = created_at.strftime(_TIMESTAMP_FORMAT)
    return f"time-reporting-{timestamp}-{revision or 'unknown'}.dump"


def _archive_name_for(dump_name: str) -> str:
    return dump_name.removesuffix(".dump") + _ATTACHMENTS_SUFFIX


def _libpq_connection(database_url: str) -> tuple[str, str | None]:
    """A DSN with no password (for the command line) and the password separately (for
    `PGPASSWORD`, which `ps`/shell history never see)."""
    url = make_url(database_url)
    password = url.password
    dsn = url.set(drivername="postgresql", password=None).render_as_string(hide_password=False)
    return dsn, password


class BackupService:
    def __init__(self, settings: Settings) -> None:
        self._backup_dir = Path(settings.backup_dir)
        self._attachment_dir = Path(settings.attachment_dir)
        self._retention_count = settings.backup_retention_count
        self._timeout_seconds = settings.backup_timeout_seconds
        self._dsn, self._password = _libpq_connection(settings.database_url)

    async def create(self, *, revision: str | None) -> BackupInfoDTO:
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self._backup_dir / _LOCK_FILE_NAME
        try:
            os.close(os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        except FileExistsError:
            raise BackupInProgressError() from None
        try:
            return await self._dump(revision=revision)
        finally:
            lock_path.unlink(missing_ok=True)

    async def _dump(self, *, revision: str | None) -> BackupInfoDTO:
        created_at = datetime.now(UTC)
        name = _build_filename(created_at, revision)
        final_path = self._backup_dir / name
        # Written under a dotfile name so a crash mid-dump never leaves something `list()`/prune
        # mistakes for a finished backup; renamed into place only once pg_dump exits 0.
        tmp_path = self._backup_dir / f".{name}.tmp"
        tmp_path.touch()
        try:
            await self._run("pg_dump", "--format=custom", "--file", str(tmp_path), self._dsn)
        except BackupFailedError:
            tmp_path.unlink(missing_ok=True)
            raise
        tmp_path.rename(final_path)
        attachments_size_bytes = self._archive_attachments(name)
        self.prune()
        return BackupInfoDTO(
            name=name,
            created_at=created_at,
            revision=revision,
            size_bytes=final_path.stat().st_size,
            attachments_size_bytes=attachments_size_bytes,
        )

    def _archive_attachments(self, dump_name: str) -> int | None:
        """Write `<dump_name minus .dump>-attachments.tar.gz` from `attachment_dir`, returning its
        size — or `None` without writing anything if the directory doesn't exist yet (a fresh
        install that has never received an upload)."""
        if not self._attachment_dir.is_dir():
            return None
        archive_path = self._backup_dir / _archive_name_for(dump_name)
        tmp_path = self._backup_dir / f".{archive_path.name}.tmp"
        with tarfile.open(tmp_path, "w:gz") as tar:
            tar.add(self._attachment_dir, arcname=".")
        tmp_path.rename(archive_path)
        return archive_path.stat().st_size

    def list(self) -> tuple[BackupInfoDTO, ...]:
        if not self._backup_dir.is_dir():
            return ()
        backups = []
        for path in self._backup_dir.glob("time-reporting-*.dump"):
            parsed = parse_backup_filename(path.name)
            if parsed is None:
                continue
            created_at, revision = parsed
            archive_path = self._backup_dir / _archive_name_for(path.name)
            backups.append(
                BackupInfoDTO(
                    name=path.name,
                    created_at=created_at,
                    revision=revision,
                    size_bytes=path.stat().st_size,
                    attachments_size_bytes=(
                        archive_path.stat().st_size if archive_path.is_file() else None
                    ),
                )
            )
        backups.sort(key=lambda backup: backup.created_at, reverse=True)
        return tuple(backups)

    def last_backup_at(self) -> datetime | None:
        backups = self.list()
        return backups[0].created_at if backups else None

    def prune(self) -> None:
        for stale in self.list()[self._retention_count :]:
            (self._backup_dir / stale.name).unlink(missing_ok=True)
            (self._backup_dir / _archive_name_for(stale.name)).unlink(missing_ok=True)

    def path_for(self, name: str) -> Path:
        if not _parse_any_backup_filename(name):
            raise BackupNotFoundError(name)
        path = self._backup_dir / name
        if not path.is_file():
            raise BackupNotFoundError(name)
        return path

    async def restore(self, path: Path) -> None:
        await self._run(
            "pg_restore",
            "--clean",
            "--if-exists",
            "--single-transaction",
            "--no-owner",
            "--dbname",
            self._dsn,
            str(path),
        )
        archive_path = self._backup_dir / _archive_name_for(path.name)
        if not archive_path.is_file():
            # Not a hard failure: an `expense_attachments` row whose file is missing already
            # degrades gracefully (`AttachmentNotFoundError`), the same way a manually deleted
            # upload would — see `expenses.CLAUDE.md`'s "File writes are never transactional".
            logger.warning(
                "No attachments archive found for %s; any expense_attachments rows in the "
                "restored database may reference missing files",
                path.name,
            )
            return
        self._attachment_dir.mkdir(parents=True, exist_ok=True)
        # A restore replaces the whole database, so it replaces the attachment directory too,
        # rather than merging archived files over whatever happened to be on disk beforehand.
        for existing in self._attachment_dir.iterdir():
            if existing.is_dir():
                for child in existing.iterdir():
                    child.unlink()
                existing.rmdir()
            else:
                existing.unlink()
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(self._attachment_dir, filter="data")

    async def _run(self, *args: str) -> None:
        env = dict(os.environ)
        if self._password:
            env["PGPASSWORD"] = self._password
        try:
            process = await asyncio.create_subprocess_exec(
                *args, env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
        except OSError as exc:
            raise BackupFailedError(f"could not run {args[0]}: {exc}") from exc

        try:
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=self._timeout_seconds)
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise BackupFailedError(f"{args[0]} timed out") from exc

        if process.returncode != 0:
            logger.error(
                "%s failed (exit %s): %s",
                args[0],
                process.returncode,
                stderr.decode(errors="replace")[-_STDERR_TAIL_CHARS:],
            )
            raise BackupFailedError()
