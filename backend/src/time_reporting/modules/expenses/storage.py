"""Storage of expense-report attachment files on disk.

No ORM/session use — files are addressed by a random storage key, independent of the CQRS bus's
request-scoped session. The ``ExpenseAttachment`` row (via ``ExpenseAttachmentRepository``) is the
source of truth for which files are still referenced; ``time-reporting prune-attachments`` sweeps
files this service wrote whose row a rolled-back command never committed — the write order is
always file first, then row, so an interrupted write can only ever orphan a file, never a row with
no file behind it. Modelled on ``system.backup_service.BackupService``.
"""

import re
import secrets
from pathlib import Path

from time_reporting.core.config import Settings
from time_reporting.modules.expenses.contracts import (
    ALLOWED_ATTACHMENT_CONTENT_TYPES,
    AttachmentTooLargeError,
    AttachmentTypeNotAllowedError,
)

# `<hex[:2]>/<hex><ext>`: the first two hex characters double as a subdirectory, so no single
# directory ends up with thousands of files. Also doubles as the key-validation check against path
# traversal, since a valid match can only ever resolve inside `attachment_dir` — the same trick
# `system.backup_service.parse_backup_filename` uses for backup file names.
_KEY_PATTERN = re.compile(r"^[0-9a-f]{2}/[0-9a-f]{32}\.[a-z0-9]{1,8}$")

_EXTENSION_BY_CONTENT_TYPE: dict[str, str] = {
    "application/pdf": "pdf",
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "heic",
}


class ExpenseAttachmentStorage:
    def __init__(self, settings: Settings) -> None:
        self._dir = Path(settings.attachment_dir)
        self._max_bytes = settings.attachment_max_bytes

    def ensure_allowed(self, *, content_type: str, size_bytes: int) -> None:
        """Raise as early as possible — before or while reading the upload body — for a request
        that's already known to be rejected. ``save`` re-checks the same rules against the bytes
        it actually received."""
        if content_type not in ALLOWED_ATTACHMENT_CONTENT_TYPES:
            raise AttachmentTypeNotAllowedError(content_type)
        if size_bytes > self._max_bytes:
            raise AttachmentTooLargeError(size_bytes, self._max_bytes)

    def save(self, *, content: bytes, content_type: str) -> str:
        """Validate and write ``content``, returning its storage key. Raises
        ``AttachmentTypeNotAllowedError``/``AttachmentTooLargeError``."""
        self.ensure_allowed(content_type=content_type, size_bytes=len(content))
        extension = _EXTENSION_BY_CONTENT_TYPE[content_type]
        # A random key, not the content hash: two different lines can attach byte-identical scans
        # (the same receipt, uploaded twice), and each upload gets its own row and file.
        token = secrets.token_hex(16)
        key = f"{token[:2]}/{token}.{extension}"
        path = self._dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        # Written under a dotfile name so a crash mid-write never leaves a half-written file at
        # its final, referenceable path — the same pattern `BackupService._dump` uses.
        tmp_path = path.with_name(f".{path.name}.tmp")
        tmp_path.write_bytes(content)
        tmp_path.rename(path)
        return key

    def path_for(self, key: str) -> Path | None:
        """The file's path, or ``None`` if ``key`` is malformed or the file doesn't exist —
        callers map that to their own "not found" domain error."""
        if _KEY_PATTERN.fullmatch(key) is None:
            return None
        path = self._dir / key
        return path if path.is_file() else None

    def delete(self, key: str) -> None:
        path = self.path_for(key)
        if path is not None:
            path.unlink(missing_ok=True)

    def prune_orphans(self, *, referenced_keys: frozenset[str], dry_run: bool) -> tuple[str, ...]:
        """Delete (or, if ``dry_run``, just report) every file under ``attachment_dir`` whose key
        isn't in ``referenced_keys``, for ``time-reporting prune-attachments``. Returns the keys
        removed (or that would be)."""
        if not self._dir.is_dir():
            return ()
        orphans: list[str] = []
        for path in sorted(self._dir.glob("*/*")):
            if not path.is_file():
                continue
            key = f"{path.parent.name}/{path.name}"
            if _KEY_PATTERN.fullmatch(key) is None or key in referenced_keys:
                continue
            orphans.append(key)
            if not dry_run:
                path.unlink(missing_ok=True)
        return tuple(orphans)
