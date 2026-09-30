"""Purchase inbox: upload, list, download, discard, idempotent import, pruning, access."""

from pathlib import Path
from uuid import uuid4

import pytest
from httpx import AsyncClient

from support import ACCOUNTANT, ADMIN, EMPLOYEE, AuthHeaders, UserFactory
from time_reporting.core.config import get_settings
from time_reporting.core.cqrs import Bus
from time_reporting.modules.expenses.storage import ExpenseAttachmentStorage
from time_reporting.modules.purchases.contracts import (
    AddPurchaseDocument,
    DiscardPurchaseDocument,
    GetPurchaseFilePath,
    ListPurchaseStorageKeys,
    PurchaseDocumentNotFoundError,
    PurchaseDocumentStateError,
    PurchaseFileTooLargeError,
    PurchaseFileTypeNotAllowedError,
    PurchaseSource,
    PurchaseStage,
)
from time_reporting.modules.purchases.storage import PurchaseFileStorage

_PDF = b"%PDF-1.4 not a real pdf"
_MAX_BYTES = 1024


@pytest.fixture(autouse=True)
def _isolated_storage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    patched = get_settings().model_copy(
        update={"attachment_dir": str(tmp_path), "attachment_max_bytes": _MAX_BYTES}
    )
    monkeypatch.setattr("time_reporting.modules.purchases.service.get_settings", lambda: patched)
    monkeypatch.setattr("time_reporting.modules.purchases.router.get_settings", lambda: patched)
    return tmp_path


def _pdf_part(name: str) -> tuple[str, tuple[str, bytes, str]]:
    return ("files", (name, _PDF, "application/pdf"))


def _add(**overrides: object) -> AddPurchaseDocument:
    fields: dict[str, object] = {
        "actor_id": None,
        "file_name": "scan.pdf",
        "content_type": "application/pdf",
        "content": _PDF,
    }
    return AddPurchaseDocument(**{**fields, **overrides})  # type: ignore[arg-type]


async def test_add_stores_an_inbox_document_whose_file_reads_back(bus: Bus) -> None:
    document = await bus.execute(_add(source=PurchaseSource.EMAIL, email_from="a@b.se"))

    assert document.stage is PurchaseStage.INBOX
    assert document.kind is None
    assert document.size_bytes == len(_PDF)
    assert document.source is PurchaseSource.EMAIL
    file = await bus.query(GetPurchaseFilePath(document_id=document.id))
    assert file.path.read_bytes() == _PDF
    assert file.file_name == "scan.pdf"


async def test_add_rejects_bad_type_and_oversize_without_writing(
    bus: Bus, _isolated_storage: Path
) -> None:
    with pytest.raises(PurchaseFileTypeNotAllowedError):
        await bus.execute(_add(content_type="text/plain"))
    with pytest.raises(PurchaseFileTooLargeError):
        await bus.execute(_add(content=b"x" * (_MAX_BYTES + 1)))

    assert not (_isolated_storage / "purchases").exists()


async def test_same_external_ref_returns_the_existing_document(
    bus: Bus, _isolated_storage: Path
) -> None:
    first = await bus.execute(_add(external_ref="msg-1/att-1"))
    second = await bus.execute(_add(external_ref="msg-1/att-1"))

    assert second.id == first.id
    assert len(list((_isolated_storage / "purchases").glob("*/*"))) == 1


async def test_discard_then_discard_again_is_a_state_error(
    bus: Bus, make_user: UserFactory
) -> None:
    document = await bus.execute(_add())
    user = (await make_user(roles=ACCOUNTANT)).id

    discarded = await bus.execute(DiscardPurchaseDocument(document_id=document.id, actor_id=user))

    assert discarded.stage is PurchaseStage.DISCARDED
    with pytest.raises(PurchaseDocumentStateError):
        await bus.execute(DiscardPurchaseDocument(document_id=document.id, actor_id=user))


async def test_unknown_document_is_not_found(bus: Bus) -> None:
    with pytest.raises(PurchaseDocumentNotFoundError):
        await bus.query(GetPurchaseFilePath(document_id=uuid4()))


async def test_prune_keeps_referenced_purchase_files_and_expense_pruning_ignores_them(
    bus: Bus, _isolated_storage: Path
) -> None:
    document = await bus.execute(_add())
    settings = get_settings().model_copy(update={"attachment_dir": str(_isolated_storage)})
    purchases = PurchaseFileStorage(settings)
    orphan_key = purchases.save(content=_PDF, content_type="application/pdf")
    referenced = await bus.query(ListPurchaseStorageKeys())

    # The expense pass sees neither purchase file.
    assert (
        ExpenseAttachmentStorage(settings).prune_orphans(referenced_keys=frozenset(), dry_run=True)
        == ()
    )
    removed = purchases.prune_orphans(referenced_keys=referenced, dry_run=False)

    assert removed == (orphan_key,)
    assert (await bus.query(GetPurchaseFilePath(document_id=document.id))).path.is_file()


# --- HTTP ---


async def test_upload_list_download_discard_round_trip(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers(await make_user(roles=ACCOUNTANT))

    uploaded = await client.post(
        "/api/v1/purchases/documents",
        headers=headers,
        files=[
            ("files", ("a.pdf", _PDF, "application/pdf")),
            ("files", ("b.png", b"\x89PNG fake", "image/png")),
        ],
    )
    assert uploaded.status_code == 201
    first, second = uploaded.json()
    assert (first["file_name"], second["file_name"]) == ("a.pdf", "b.png")

    listed = await client.get(
        "/api/v1/purchases/documents", headers=headers, params={"stage": "inbox"}
    )
    assert {first["id"], second["id"]} <= {item["id"] for item in listed.json()}

    download = await client.get(f"/api/v1/purchases/documents/{first['id']}/file", headers=headers)
    assert download.status_code == 200
    assert download.content == _PDF

    discarded = await client.post(
        f"/api/v1/purchases/documents/{first['id']}/discard", headers=headers
    )
    assert discarded.json()["stage"] == "discarded"
    again = await client.post(f"/api/v1/purchases/documents/{first['id']}/discard", headers=headers)
    assert again.status_code == 409


async def test_upload_limits_reject_the_whole_batch(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders, _isolated_storage: Path
) -> None:
    headers = auth_headers(await make_user(roles=ACCOUNTANT))
    url = "/api/v1/purchases/documents"

    wrong_type = await client.post(
        url,
        headers=headers,
        files=[
            ("files", ("a.pdf", _PDF, "application/pdf")),
            ("files", ("x.txt", b"x", "text/plain")),
        ],
    )
    too_big = await client.post(
        url,
        headers=headers,
        files=[
            ("files", ("a.pdf", _PDF, "application/pdf")),
            ("files", ("big.pdf", b"x" * 2000, "application/pdf")),
        ],
    )

    assert wrong_type.status_code == 415
    assert too_big.status_code == 413
    assert not (_isolated_storage / "purchases").exists()


async def test_only_accountants_can_use_the_register(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    accountant = auth_headers(await make_user(roles=ACCOUNTANT))
    created = await client.post(
        "/api/v1/purchases/documents",
        headers=accountant,
        files=[("files", ("a.pdf", _PDF, "application/pdf"))],
    )
    document_id = created.json()[0]["id"]

    for roles in (EMPLOYEE, ADMIN):
        headers = auth_headers(await make_user(roles=roles))
        assert (await client.get("/api/v1/purchases/documents", headers=headers)).status_code == 403
        assert (
            await client.get(f"/api/v1/purchases/documents/{document_id}/file", headers=headers)
        ).status_code == 403
        assert (
            await client.post(
                "/api/v1/purchases/documents",
                headers=headers,
                files=[("files", ("a.pdf", _PDF, "application/pdf"))],
            )
        ).status_code == 403
