"""Tests de l'upload de documents admin : noms de fichiers sûrs et taille bornée."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.db.session import get_db
from app.main import app
from app.middleware.auth import create_access_token
from app.models.user import User
from app.routers.admin import contenus as admin_router


@pytest.fixture
def client_admin(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    ingestions = []

    async def _ingestion(**kwargs):
        ingestions.append(kwargs)

    monkeypatch.setattr(admin_router, "_run_admin_ingestion_task", _ingestion)

    admin = User(id=uuid.uuid4(), email="admin@test.ci", is_admin=True)
    session = MagicMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=admin))
    )
    session.commit = AsyncMock()
    session.add = MagicMock()

    async def _db():
        yield session

    from tests.conftest import mock_get_db

    app.dependency_overrides[get_db] = _db
    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(admin.id)})}"}
    yield headers, tmp_path, ingestions, session
    app.dependency_overrides[get_db] = mock_get_db


async def _upload(headers, filename, content=b"# Guide\nContenu.", data=None):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(
            "/api/admin/upload-pdf",
            files={"file": (filename, content, "text/markdown")},
            data=data
            if data is not None
            else {
                "metier_id": "1",
                "secteur_id": "1",
                "type_document": "guide_technique",
                "niveau_expertise": "intermediaire",
            },
            headers=headers,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "filename",
    ["../../app/main.md", "..\\..\\evil.md", ".cache.md", "a/b/../c.md"],
)
async def test_upload_nom_avec_chemin_neutralise(client_admin, filename):
    """Aucun fichier n'est écrit hors du dossier d'upload, quel que soit le nom reçu."""
    headers, tmp_path, _, _session = client_admin
    response = await _upload(headers, filename)

    ecrits = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert all(p.parent.parent == tmp_path / "admin_docs" for p in ecrits)
    if response.status_code == 202:
        assert ecrits[0].name == filename.replace("\\", "/").rsplit("/", 1)[-1]
    else:
        assert response.status_code == 400
        assert ecrits == []


@pytest.mark.asyncio
async def test_upload_extension_non_autorisee_refusee(client_admin):
    headers, _, ingestions, _session = client_admin
    response = await _upload(headers, "script.sh")

    assert response.status_code == 400
    assert ingestions == []


@pytest.mark.asyncio
async def test_upload_trop_volumineux_refuse(client_admin):
    headers, tmp_path, _, _session = client_admin
    response = await _upload(
        headers, "gros.md", b"x" * (admin_router.MAX_ADMIN_UPLOAD_BYTES + 1)
    )

    assert response.status_code == 413
    assert not any(p.is_file() for p in tmp_path.rglob("*"))


@pytest.mark.asyncio
async def test_upload_valide_lance_l_ingestion(client_admin):
    headers, tmp_path, ingestions, session = client_admin
    response = await _upload(headers, "guide_maconnerie v2.md")

    assert response.status_code == 202
    uploaded = list((tmp_path / "admin_docs").glob("*/guide_maconnerie v2.md"))
    assert len(uploaded) == 1
    assert len(ingestions) == 1
    assert ingestions[0]["file_path"] == str(uploaded[0])
    session.commit.assert_awaited_once()
    audit_entry = session.add.call_args.args[0]
    assert audit_entry.action == "document.ingestion.requested"
    assert audit_entry.after_json["sha256"] == response.json()["sha256"]


@pytest.mark.asyncio
async def test_upload_exige_toutes_les_metadonnees(client_admin):
    headers, tmp_path, ingestions, _session = client_admin
    response = await _upload(headers, "guide.md", data={})

    assert response.status_code == 422
    assert ingestions == []
    assert not any(p.is_file() for p in tmp_path.rglob("*"))


@pytest.mark.asyncio
async def test_upload_refuse_metadonnees_semantiques_inconnues(client_admin):
    headers, tmp_path, ingestions, _session = client_admin
    response = await _upload(
        headers,
        "guide.md",
        data={
            "metier_id": "1",
            "secteur_id": "1",
            "type_document": "script_executable",
            "niveau_expertise": "expert_magique",
        },
    )

    assert response.status_code == 422
    assert ingestions == []
    assert not any(p.is_file() for p in tmp_path.rglob("*"))


@pytest.mark.asyncio
async def test_tache_ingestion_echouee_nettoie_et_trace(tmp_path, monkeypatch):
    upload_dir = tmp_path / "job"
    upload_dir.mkdir()
    upload = upload_dir / "guide.md"
    upload.write_text("contenu", encoding="utf-8")

    async def _failed_ingestion(**_kwargs):
        return {"processed_files": 0, "ingested_chunks": 0, "erreurs": ["échec"]}

    audit = AsyncMock()
    session = MagicMock()
    session.commit = AsyncMock()

    class _SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(admin_router, "run_ingestion", _failed_ingestion)
    monkeypatch.setattr(admin_router.audit_service, "log_action", audit)
    monkeypatch.setattr(admin_router, "async_session", _SessionContext)

    job_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    await admin_router._run_admin_ingestion_task(
        job_id=job_id,
        actor_id=actor_id,
        file_path=str(upload),
        docs_dir=str(upload_dir),
        metier_id=1,
        secteur_id=1,
        type_document="guide_technique",
        niveau_expertise="intermediaire",
    )

    assert not upload.exists()
    assert not upload_dir.exists()
    assert audit.await_args.kwargs["action"] == "document.ingestion.failed"
    assert audit.await_args.kwargs["resource_id"] == str(job_id)
    session.commit.assert_awaited_once()
