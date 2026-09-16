"""`pg_dump`/`pg_restore` orchestration. No ORM/session use — backups run as a subprocess against
the same database the app's `DATABASE_URL` points at, entirely independent of the CQRS bus's
request-scoped session.
"""

import asyncio
import logging
import os
import re
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
_FILENAME_PATTERN = re.compile(
    r"^time-reporting-(?P<timestamp>\d{8}T\d{6}Z)-(?P<revision>[0-9a-f]{12}|unknown)\.dump$"
)
_LOCK_FILE_NAME = ".backup.lock"
# Kept out of the raised exception (which the API returns to the client) but logged in full up to
# this many trailing characters, since pg_dump/pg_restore stderr can be long-winded.
_STDERR_TAIL_CHARS = 4000


def parse_backup_filename(name: str) -> tuple[datetime, str | None] | None:
    """The dump's creation time and recorded revision, or `None` if `name` isn't a backup file
    name this service produced — also doubles as the name-validation check against path
    traversal, since a valid match can only ever resolve inside `backup_dir`."""
    match = _FILENAME_PATTERN.fullmatch(name)
    if match is None:
        return None
    created_at = datetime.strptime(match.group("timestamp"), _TIMESTAMP_FORMAT).replace(tzinfo=UTC)
    revision = match.group("revision")
    return created_at, None if revision == "unknown" else revision


def _build_filename(created_at: datetime, revision: str | None) -> str:
    timestamp = created_at.strftime(_TIMESTAMP_FORMAT)
    return f"time-reporting-{timestamp}-{revision or 'unknown'}.dump"


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
        self.prune()
        return BackupInfoDTO(
            name=name,
            created_at=created_at,
            revision=revision,
            size_bytes=final_path.stat().st_size,
        )

    def list(self) -> tuple[BackupInfoDTO, ...]:
        if not self._backup_dir.is_dir():
            return ()
        backups = []
        for path in self._backup_dir.glob("time-reporting-*.dump"):
            parsed = parse_backup_filename(path.name)
            if parsed is None:
                continue
            created_at, revision = parsed
            backups.append(
                BackupInfoDTO(
                    name=path.name,
                    created_at=created_at,
                    revision=revision,
                    size_bytes=path.stat().st_size,
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

    def path_for(self, name: str) -> Path:
        if parse_backup_filename(name) is None:
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
