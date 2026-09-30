"""`core.file_storage.FileStorage` against a real temp directory."""

from pathlib import Path

import pytest

from time_reporting.core.file_storage import FileStorage, FileTooLargeError, FileTypeNotAllowedError

_EXTENSIONS = {"application/pdf": "pdf"}


def _storage(root: Path, *, max_bytes: int = 16) -> FileStorage:
    return FileStorage(root, max_bytes=max_bytes, extensions=_EXTENSIONS)


def test_save_and_path_for_round_trip(tmp_path: Path) -> None:
    storage = _storage(tmp_path)

    key = storage.save(content=b"%PDF-1", content_type="application/pdf")

    path = storage.path_for(key)
    assert path is not None and path.read_bytes() == b"%PDF-1"
    assert key.endswith(".pdf")


def test_save_rejects_unknown_type_and_oversize(tmp_path: Path) -> None:
    storage = _storage(tmp_path)

    with pytest.raises(FileTypeNotAllowedError):
        storage.save(content=b"x", content_type="text/plain")
    with pytest.raises(FileTooLargeError):
        storage.save(content=b"x" * 17, content_type="application/pdf")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("key", ["../etc/passwd", "/abs/path.pdf", "ab/not-a-key.pdf", ""])
def test_path_for_rejects_malformed_keys(tmp_path: Path, key: str) -> None:
    assert _storage(tmp_path).path_for(key) is None
