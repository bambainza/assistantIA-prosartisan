"""Régressions de fiabilité pour la suppression documentaire admin."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from qdrant_client.http.models import UpdateStatus

from app.db.session import get_db
from app.main import app
from app.middleware.auth import create_access_token
from app.models.document_config import DocumentConfig
from app.models.user import User
from app.routers.admin import contenus
from app.services.document_service import (
    DocumentDeletionResult,
    DocumentVectorStoreError,
    document_service,
)
from app.services.rag_service import rag_service


@pytest.fixture
def deletion_context(monkeypatch):
    admin = User(id=uuid.uuid4(), email="delete-admin@test.ci", is_admin=True)
    config = DocumentConfig(filename="guide-test.md", is_active=True)
    session = MagicMock()
    session.commit = AsyncMock()
    session.delete = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(
        side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=admin)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=config)),
        ]
    )

    async def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    invalidate = AsyncMock()
    monkeypatch.setattr(rag_service, "invalidate_activation_cache", invalidate)
    yield admin, config, session, invalidate
    app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_suppression_confirmee_audite_puis_invalide_cache(
    deletion_context, monkeypatch
):
    admin, config, session, invalidate = deletion_context
    delete_vectors = AsyncMock(
        return_value=DocumentDeletionResult(operation_id=42, status="completed")
    )
    monkeypatch.setattr(contenus.document_service, "delete_vectors", delete_vectors)
    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(admin.id)})}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete(
            "/api/admin/documents/guide-test.md", headers=headers
        )

    assert response.status_code == 200
    assert response.json()["operation_id"] == 42
    delete_vectors.assert_awaited_once_with("guide-test.md")
    session.delete.assert_awaited_once_with(config)
    session.commit.assert_awaited_once()
    assert any(
        getattr(entry, "action", None) == "document.delete"
        and entry.after_json["status"] == "deleted"
        for entry in session.add.call_args.args
    )
    invalidate.assert_awaited_once()


@pytest.mark.asyncio
async def test_echec_qdrant_ne_commit_pas_et_ne_renvoie_pas_succes(
    deletion_context, monkeypatch
):
    admin, _config, session, invalidate = deletion_context
    monkeypatch.setattr(
        contenus.document_service,
        "delete_vectors",
        AsyncMock(side_effect=DocumentVectorStoreError("qdrant indisponible")),
    )
    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(admin.id)})}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete(
            "/api/admin/documents/guide-test.md", headers=headers
        )

    assert response.status_code == 503
    session.delete.assert_not_awaited()
    session.commit.assert_not_awaited()
    session.add.assert_not_called()
    invalidate.assert_not_awaited()


@pytest.mark.asyncio
async def test_suppression_vectorielle_est_idempotente_et_attend_qdrant(monkeypatch):
    qdrant_delete = AsyncMock(
        return_value=MagicMock(status=UpdateStatus.COMPLETED, operation_id=7)
    )
    monkeypatch.setattr(rag_service.qdrant_client, "delete", qdrant_delete)

    first = await document_service.delete_vectors("deja-absent.md")
    second = await document_service.delete_vectors("deja-absent.md")

    assert first.status == second.status == "completed"
    assert qdrant_delete.await_count == 2
    assert all(call.kwargs["wait"] is True for call in qdrant_delete.await_args_list)


@pytest.mark.asyncio
async def test_suppression_non_confirmee_est_une_erreur(monkeypatch):
    monkeypatch.setattr(
        rag_service.qdrant_client,
        "delete",
        AsyncMock(
            return_value=MagicMock(
                status=UpdateStatus.ACKNOWLEDGED,
                operation_id=8,
            )
        ),
    )

    with pytest.raises(DocumentVectorStoreError, match="non confirmée"):
        await document_service.delete_vectors("guide.md")
