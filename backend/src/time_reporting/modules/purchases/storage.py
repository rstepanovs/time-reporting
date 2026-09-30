"""Storage of purchase-document files on disk, under ``<attachment_dir>/purchases/``.

A wrapper over the shared ``core.file_storage.FileStorage``; living below ``attachment_dir`` keeps
the files inside the backup's existing attachment archive, while ``expenses``' pruning (which only
matches ``<hex>/<file>`` keys) never touches them.
"""

from pathlib import Path

from time_reporting.core.config import Settings
from time_reporting.core.file_storage import FileStorage, FileTooLargeError, FileTypeNotAllowedError
from time_reporting.modules.purchases.contracts import (
    PurchaseFileTooLargeError,
    PurchaseFileTypeNotAllowedError,
)

PURCHASES_SUBDIRECTORY = "purchases"

_EXTENSION_BY_CONTENT_TYPE: dict[str, str] = {
    "application/pdf": "pdf",
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "heic",
}


class PurchaseFileStorage:
    def __init__(self, settings: Settings) -> None:
        self._storage = FileStorage(
            Path(settings.attachment_dir) / PURCHASES_SUBDIRECTORY,
            max_bytes=settings.attachment_max_bytes,
            extensions=_EXTENSION_BY_CONTENT_TYPE,
        )

    def ensure_allowed(self, *, content_type: str, size_bytes: int) -> None:
        try:
            self._storage.ensure_allowed(content_type=content_type, size_bytes=size_bytes)
        except FileTypeNotAllowedError as exc:
            raise PurchaseFileTypeNotAllowedError(exc.content_type) from exc
        except FileTooLargeError as exc:
            raise PurchaseFileTooLargeError(exc.size_bytes, exc.max_bytes) from exc

    def save(self, *, content: bytes, content_type: str) -> str:
        self.ensure_allowed(content_type=content_type, size_bytes=len(content))
        return self._storage.save(content=content, content_type=content_type)

    def path_for(self, key: str) -> Path | None:
        return self._storage.path_for(key)

    def delete(self, key: str) -> None:
        self._storage.delete(key)

    def prune_orphans(self, *, referenced_keys: frozenset[str], dry_run: bool) -> tuple[str, ...]:
        return self._storage.prune_orphans(referenced_keys=referenced_keys, dry_run=dry_run)
