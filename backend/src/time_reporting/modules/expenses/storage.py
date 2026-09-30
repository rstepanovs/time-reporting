"""Storage of expense-report attachment files on disk.

A thin wrapper over the shared ``core.file_storage.FileStorage`` rooted at ``attachment_dir``: it
fixes the allowed content types and translates the storage's rejections into this module's own
domain errors. The ``ExpenseAttachment`` row (via ``ExpenseAttachmentRepository``) is the source of
truth for which files are still referenced; ``time-reporting prune-attachments`` sweeps the rest.
"""

from pathlib import Path

from time_reporting.core.config import Settings
from time_reporting.core.file_storage import FileStorage, FileTooLargeError, FileTypeNotAllowedError
from time_reporting.modules.expenses.contracts import (
    AttachmentTooLargeError,
    AttachmentTypeNotAllowedError,
)

_EXTENSION_BY_CONTENT_TYPE: dict[str, str] = {
    "application/pdf": "pdf",
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "heic",
}


class ExpenseAttachmentStorage:
    def __init__(self, settings: Settings) -> None:
        self._storage = FileStorage(
            Path(settings.attachment_dir),
            max_bytes=settings.attachment_max_bytes,
            extensions=_EXTENSION_BY_CONTENT_TYPE,
        )

    def ensure_allowed(self, *, content_type: str, size_bytes: int) -> None:
        """Raise as early as possible for a request that's already known to be rejected."""
        try:
            self._storage.ensure_allowed(content_type=content_type, size_bytes=size_bytes)
        except FileTypeNotAllowedError as exc:
            raise AttachmentTypeNotAllowedError(exc.content_type) from exc
        except FileTooLargeError as exc:
            raise AttachmentTooLargeError(exc.size_bytes, exc.max_bytes) from exc

    def save(self, *, content: bytes, content_type: str) -> str:
        """Validate and write ``content``, returning its storage key. Raises
        ``AttachmentTypeNotAllowedError``/``AttachmentTooLargeError``."""
        self.ensure_allowed(content_type=content_type, size_bytes=len(content))
        return self._storage.save(content=content, content_type=content_type)

    def path_for(self, key: str) -> Path | None:
        return self._storage.path_for(key)

    def delete(self, key: str) -> None:
        self._storage.delete(key)

    def prune_orphans(self, *, referenced_keys: frozenset[str], dry_run: bool) -> tuple[str, ...]:
        return self._storage.prune_orphans(referenced_keys=referenced_keys, dry_run=dry_run)
