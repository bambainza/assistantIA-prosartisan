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

    monkeypatch.setattr(admin_router, "run_ingestion", _ingestion)

    admin = User(id=uuid.uuid4(), email="admin@test.ci", is_admin=True)

    async def _db():
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=admin))
        )
        session.commit = AsyncMock()
        yield session

    from tests.conftest import mock_get_db

    app.dependency_overrides[get_db] = _db
    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(admin.id)})}"}
    yield headers, tmp_path, ingestions
    app.dependency_overrides[get_db] = mock_get_db


async def _upload(headers, filename, content=b"# Guide\nContenu."):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(
            "/api/admin/upload-pdf",
            files={"file": (filename, content, "text/markdown")},
            headers=headers,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "filename",
    ["../../app/main.md", "..\\..\\evil.md", ".cache.md", "a/b/../c.md"],
)
async def test_upload_nom_avec_chemin_neutralise(client_admin, filename):
    """Aucun fichier n'est écrit hors du dossier d'upload, quel que soit le nom reçu."""
    headers, tmp_path, _ = client_admin
    response = await _upload(headers, filename)

    ecrits = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert all(p.parent == tmp_path / "admin_docs" for p in ecrits)
    if response.status_code == 202:
        assert ecrits[0].name == filename.replace("\\", "/").rsplit("/", 1)[-1]
    else:
        assert response.status_code == 400
        assert ecrits == []


@pytest.mark.asyncio
async def test_upload_extension_non_autorisee_refusee(client_admin):
    headers, _, ingestions = client_admin
    response = await _upload(headers, "script.sh")

    assert response.status_code == 400
    assert ingestions == []


@pytest.mark.asyncio
async def test_upload_trop_volumineux_refuse(client_admin):
    headers, tmp_path, _ = client_admin
    response = await _upload(
        headers, "gros.md", b"x" * (admin_router.MAX_ADMIN_UPLOAD_BYTES + 1)
    )

    assert response.status_code == 413
    assert not any(p.is_file() for p in tmp_path.rglob("*"))


@pytest.mark.asyncio
async def test_upload_valide_lance_l_ingestion(client_admin):
    headers, tmp_path, ingestions = client_admin
    response = await _upload(headers, "guide_maconnerie v2.md")

    assert response.status_code == 202
    assert (tmp_path / "admin_docs" / "guide_maconnerie v2.md").is_file()
    assert len(ingestions) == 1
