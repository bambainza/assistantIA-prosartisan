"""Tests pour l'activation/désactivation des documents et des métiers depuis le Back-Office."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import get_db
from app.main import app
from app.middleware.auth import create_access_token
from app.models.metier import Metier
from app.models.user import User
from app.services.rag_service import rag_service


@pytest.fixture
def admin_user():
    return User(
        id=uuid.uuid4(),
        email="admin_toggle@prosartisan.ci",
        nom="Admin Toggle",
        is_admin=True,
    )


@pytest.fixture
def mock_db_with_admin(admin_user):
    async def custom_mock_db():
        session = MagicMock()

        async def mock_execute(stmt):
            stmt_str = str(stmt)
            mock_res = MagicMock()
            if "users" in stmt_str:
                mock_res.scalar_one_or_none.return_value = admin_user
            elif "document_configs" in stmt_str:
                mock_res.scalar_one_or_none.return_value = None
            else:
                mock_res.scalar_one_or_none.return_value = None
            mock_res.scalar.return_value = 1
            mock_res.scalars.return_value.all.return_value = []
            mock_res.scalars.return_value.first.return_value = None
            mock_res.all.return_value = []
            return mock_res

        session.execute = mock_execute
        session.commit = AsyncMock()
        session.add = MagicMock()
        session.refresh = AsyncMock()
        yield session

    return custom_mock_db


@pytest.mark.asyncio
async def test_admin_get_documents_with_active_status(mock_db_with_admin, admin_user):
    """GET /api/admin/documents doit retourner is_active pour chaque document."""
    app.dependency_overrides[get_db] = mock_db_with_admin
    token = create_access_token(data={"sub": str(admin_user.id)})
    headers = {"Authorization": f"Bearer {token}"}

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get("/api/admin/documents", headers=headers)

        assert res.status_code == 200
        data = res.json()
        assert "documents" in data
        assert len(data["documents"]) > 0
        assert "is_active" in data["documents"][0]
        assert data["documents"][0]["is_active"] is True
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_admin_toggle_document_status(mock_db_with_admin, admin_user):
    """PATCH /api/admin/documents/{doc_name}/toggle bascule l'activation d'un document."""
    app.dependency_overrides[get_db] = mock_db_with_admin
    token = create_access_token(data={"sub": str(admin_user.id)})
    headers = {"Authorization": f"Bearer {token}"}

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.patch(
                "/api/admin/documents/guide_maconnerie_dtu_20_1_ci.md/toggle",
                headers=headers,
            )

        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert "is_active" in data
        assert "guide_maconnerie_dtu_20_1_ci.md" in data["filename"]
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_admin_get_and_toggle_metier_status(admin_user):
    """Vérifie l'API GET et PATCH /api/admin/metiers/{id}/toggle."""
    test_metier = Metier(
        id=99,
        nom="Métier Test",
        slug="metier-test",
        is_active=True,
    )

    async def mock_db():
        session = MagicMock()
        admin_result = MagicMock(scalar_one_or_none=MagicMock(return_value=admin_user))
        metiers_result = MagicMock(
            scalar_one_or_none=MagicMock(return_value=test_metier),
            scalars=MagicMock(
                return_value=MagicMock(all=MagicMock(return_value=[test_metier]))
            ),
        )
        session.execute = AsyncMock(
            side_effect=[
                admin_result,
                metiers_result,
                admin_result,
                MagicMock(
                    scalar_one_or_none=MagicMock(return_value=test_metier),
                ),
            ]
        )
        session.commit = AsyncMock()
        yield session

    app.dependency_overrides[get_db] = mock_db
    token = create_access_token(data={"sub": str(admin_user.id)})
    headers = {"Authorization": f"Bearer {token}"}

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Lister les métiers
            res_list = await client.get("/api/admin/metiers", headers=headers)
            assert res_list.status_code == 200
            data_list = res_list.json()
            assert "metiers" in data_list
            assert len(data_list["metiers"]) > 0

            # 2. Basculer le statut du métier
            res_toggle = await client.patch(
                "/api/admin/metiers/99/toggle", headers=headers
            )
            assert res_toggle.status_code == 200
            data_toggle = res_toggle.json()
            assert data_toggle["status"] == "ok"
            assert data_toggle["is_active"] is False
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_rag_search_context_excludes_inactive_document(monkeypatch):
    """Vérifie que les extraits de documents désactivés sont exclus de search_context."""
    mock_hits = [
        MagicMock(
            score=0.92,
            payload={
                "text": "Extrait actif de maçonnerie.",
                "document_name": "guide_actif.md",
                "metier_id": 1,
            },
        ),
        MagicMock(
            score=0.95,
            payload={
                "text": "Extrait désactivé.",
                "document_name": "guide_desactive.md",
                "metier_id": 1,
            },
        ),
    ]

    async def mock_qdrant_query_points(*args, **kwargs):
        return MagicMock(points=mock_hits)

    async def mock_inactive_docs(*args, **kwargs):
        return {"guide_desactive.md"}

    monkeypatch.setattr(
        rag_service.qdrant_client, "query_points", mock_qdrant_query_points
    )
    monkeypatch.setattr(rag_service, "get_inactive_document_names", mock_inactive_docs)
    monkeypatch.setattr(
        rag_service, "get_embedding", AsyncMock(return_value=[0.1] * 1536)
    )

    results = await rag_service.search_context(query="test", metier_id=1)

    # Seul le document actif doit subsister
    assert len(results) == 1
    assert results[0]["metadata"]["document_name"] == "guide_actif.md"


@pytest.mark.asyncio
async def test_rag_generate_response_intercepts_inactive_metier(monkeypatch):
    """Vérifie que le RAG informe l'artisan si le métier demandé est désactivé."""

    async def mock_inactive_metier(metier_id):
        return False

    monkeypatch.setattr(rag_service, "is_metier_active", mock_inactive_metier)

    res = await rag_service.generate_response(
        question="Comment poser un carrelage ?",
        metier_id=1,
    )

    assert "suspendu" in res["reponse"] or "actualisation" in res["reponse"]
    assert res["sources"] == []
