"""HTTP API for `/admin/backups`: admin gating and the create/list/download flow. `pg_dump` is
stubbed throughout (`test_backup_service.py` covers `BackupService` itself in depth) and every
test's backup_dir is redirected to a fresh `tmp_path`, so nothing here touches a real filesystem
location or process.
"""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from support import ADMIN, EMPLOYEE, MANAGER, AuthHeaders, UserFactory
from time_reporting.core.config import get_settings
from time_reporting.modules.users.contracts import UserRole


class _FakeProcess:
    def __init__(self, returncode: int, stderr: bytes = b"") -> None:
        self.returncode = returncode
        self._stderr = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return b"", self._stderr

    def kill(self) -> None:
        pass

    async def wait(self) -> int:
        return self.returncode


def _create_lock_file(directory: Path) -> None:
    """A plain (non-async) helper, so tests can set this up without ruff's ASYNC240 flagging a
    blocking `pathlib` call made directly inside an `async def` test."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / ".backup.lock").touch()


def _stub_pg_dump(monkeypatch: pytest.MonkeyPatch, *, returncode: int = 0) -> None:
    async def fake_create_subprocess_exec(*_args: Any, **_kwargs: Any) -> _FakeProcess:
        return _FakeProcess(returncode)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)


@pytest.fixture(autouse=True)
def _isolated_backups(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    patched = get_settings().model_copy(update={"backup_dir": str(tmp_path)})
    monkeypatch.setattr("time_reporting.modules.system.handlers.get_settings", lambda: patched)
    _stub_pg_dump(monkeypatch)


async def test_anonymous_cannot_use_backup_routes(client: AsyncClient) -> None:
    responses = [
        await client.get("/api/v1/admin/backups"),
        await client.post("/api/v1/admin/backups"),
        await client.get("/api/v1/admin/backups/whatever.dump"),
    ]

    assert {r.status_code for r in responses} == {401}


@pytest.mark.parametrize("roles", [MANAGER, EMPLOYEE])
async def test_non_admin_cannot_use_backup_routes(
    client: AsyncClient,
    make_user: UserFactory,
    auth_headers: AuthHeaders,
    roles: frozenset[UserRole],
) -> None:
    headers = auth_headers(await make_user(roles=roles))

    responses = [
        await client.get("/api/v1/admin/backups", headers=headers),
        await client.post("/api/v1/admin/backups", headers=headers),
    ]

    assert {r.status_code for r in responses} == {403}


async def test_admin_can_list_create_and_download_a_backup(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))

    empty = await client.get("/api/v1/admin/backups", headers=headers)
    assert empty.status_code == 200
    assert empty.json() == {"backups": [], "last_backup_at": None}

    created = await client.post("/api/v1/admin/backups", headers=headers)
    assert created.status_code == 201
    body = created.json()
    name = body["name"]
    assert name.startswith("time-reporting-") and name.endswith(".dump")
    assert body["revision"]  # the migrated test database always has a current revision

    listed = await client.get("/api/v1/admin/backups", headers=headers)
    assert listed.status_code == 200
    assert [b["name"] for b in listed.json()["backups"]] == [name]
    assert listed.json()["last_backup_at"] is not None

    download = await client.get(f"/api/v1/admin/backups/{name}", headers=headers)
    assert download.status_code == 200
    assert download.headers["content-disposition"].endswith(f'"{name}"')


async def test_creating_a_backup_while_one_is_in_progress_conflicts(
    client: AsyncClient,
    make_user: UserFactory,
    auth_headers: AuthHeaders,
    tmp_path: Path,
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))
    _create_lock_file(tmp_path)

    response = await client.post("/api/v1/admin/backups", headers=headers)

    assert response.status_code == 409


async def test_a_failed_backup_returns_500(
    client: AsyncClient,
    make_user: UserFactory,
    auth_headers: AuthHeaders,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_pg_dump(monkeypatch, returncode=1)
    headers = auth_headers(await make_user(roles=ADMIN))

    response = await client.post("/api/v1/admin/backups", headers=headers)

    assert response.status_code == 500


async def test_downloading_an_unknown_backup_is_not_found(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))

    response = await client.get("/api/v1/admin/backups/not-a-real-backup.dump", headers=headers)

    assert response.status_code == 404
