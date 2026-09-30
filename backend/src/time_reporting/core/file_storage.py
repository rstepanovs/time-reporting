"""Content-addressed-by-random-key file storage on disk, shared by the modules that keep uploaded
documents (``expenses`` attachments, ``purchases`` documents).

No ORM/session use — files are addressed by a random storage key, independent of the CQRS bus's
request-scoped session. A module's own table row is the source of truth for which files are still
referenced; a sweep (``prune_orphans``) removes files a rolled-back command never committed — the
write order is always file first, then row, so an interrupted write can only ever orphan a file,
never leave a row with no file behind it. Modelled on ``system.backup_service.BackupService``.
"""

import re
import secrets
from collections.abc import Mapping
from pathlib import Path

# `<hex[:2]>/<hex><ext>`: the first two hex characters double as a subdirectory, so no single
# directory ends up with thousands of files. Also doubles as the key-validation check against path
# traversal, since a valid match can only ever resolve inside the storage root — the same trick
# `system.backup_service.parse_backup_filename` uses for backup file names.
_KEY_PATTERN = re.compile(r"^[0-9a-f]{2}/[0-9a-f]{32}\.[a-z0-9]{1,8}$")


class FileStorageError(Exception):
    """Base class for rejections a storage raises before writing anything."""


class FileTooLargeError(FileStorageError):
    def __init__(self, size_bytes: int, max_bytes: int) -> None:
        super().__init__(f"File is {size_bytes} bytes, more than the {max_bytes} byte limit")
        self.size_bytes = size_bytes
        self.max_bytes = max_bytes


class FileTypeNotAllowedError(FileStorageError):
    def __init__(self, content_type: str) -> None:
        super().__init__(f"File type {content_type!r} is not allowed")
        self.content_type = content_type


class FileStorage:
    """``extensions`` maps each allowed content type to the extension its files are stored under."""

    def __init__(self, root: Path, *, max_bytes: int, extensions: Mapping[str, str]) -> None:
        self._root = root
        self._max_bytes = max_bytes
        self._extensions = dict(extensions)

    def ensure_allowed(self, *, content_type: str, size_bytes: int) -> None:
        """Raise as early as possible — before or while reading the upload body — for a request
        that's already known to be rejected. ``save`` re-checks the same rules against the bytes
        it actually received."""
        if content_type not in self._extensions:
            raise FileTypeNotAllowedError(content_type)
        if size_bytes > self._max_bytes:
            raise FileTooLargeError(size_bytes, self._max_bytes)

    def save(self, *, content: bytes, content_type: str) -> str:
        """Validate and write ``content``, returning its storage key. Raises
        ``FileTypeNotAllowedError``/``FileTooLargeError``."""
        self.ensure_allowed(content_type=content_type, size_bytes=len(content))
        extension = self._extensions[content_type]
        # A random key, not the content hash: the same scan can legitimately be stored twice, and
        # each upload gets its own row and file.
        token = secrets.token_hex(16)
        key = f"{token[:2]}/{token}.{extension}"
        path = self._root / key
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
        path = self._root / key
        return path if path.is_file() else None

    def delete(self, key: str) -> None:
        path = self.path_for(key)
        if path is not None:
            path.unlink(missing_ok=True)

    def prune_orphans(self, *, referenced_keys: frozenset[str], dry_run: bool) -> tuple[str, ...]:
        """Delete (or, if ``dry_run``, just report) every file directly under this storage's
        ``<hex>/`` subdirectories whose key isn't in ``referenced_keys``. Returns the keys removed
        (or that would be). Anything not shaped like a key — including another storage nested
        under the same root, such as ``purchases/`` beside the expense attachments — is left
        alone."""
        if not self._root.is_dir():
            return ()
        orphans: list[str] = []
        for path in sorted(self._root.glob("*/*")):
            if not path.is_file():
                continue
            key = f"{path.parent.name}/{path.name}"
            if _KEY_PATTERN.fullmatch(key) is None or key in referenced_keys:
                continue
            orphans.append(key)
            if not dry_run:
                path.unlink(missing_ok=True)
        return tuple(orphans)
