"""Tests pour le routeur conversations et l'historique de chat."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import get_db
from app.main import app
from app.models.conversation import Conversation


@pytest.mark.asyncio
async def test_create_conversation():
    """POST /api/conversations crée une nouvelle discussion."""
    payload = {"title": "Test Discussion"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/conversations", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["title"] == "Test Discussion"


@pytest.mark.asyncio
async def test_list_conversations():
    """GET /api/conversations renvoie la liste des discussions."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/conversations")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_get_conversation_not_found():
    """GET /api/conversations/{id} renvoie 404 si elle n'existe pas."""
    random_id = str(uuid.uuid4())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/conversations/{random_id}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_conversation_success():
    """GET /api/conversations/{id} renvoie 200 quand la conversation existe."""
    mock_conv = Conversation(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        title="Mocked Conv",
        messages=[],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    async def custom_mock_db():
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value=mock_conv)
            )
        )
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/conversations/{mock_conv.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Mocked Conv"
    finally:
        # Reset override
        from tests.conftest import mock_get_db

        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_delete_conversation_not_found():
    """DELETE /api/conversations/{id} renvoie 404 si elle n'existe pas."""
    random_id = str(uuid.uuid4())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete(f"/api/conversations/{random_id}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_conversation_success():
    """DELETE /api/conversations/{id} renvoie 200 quand la suppression réussit."""
    mock_conv = Conversation(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        title="Mocked Conv",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    async def custom_mock_db():
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value=mock_conv)
            )
        )
        session.commit = AsyncMock()
        session.delete = MagicMock()
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(f"/api/conversations/{mock_conv.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
    finally:
        from tests.conftest import mock_get_db

        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_chat_endpoint_creates_conversation():
    """POST /api/chat sans conversation_id doit créer une conversation et la renvoyer."""
    payload = {
        "user_id": str(uuid.uuid4()),
        "question": "Quel dosage de ciment ?",
        "metier_id": 1,
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/chat", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert "conversation_id" in data
    assert data["conversation_id"] is not None


@pytest.mark.asyncio
async def test_patch_rename_conversation():
    """PATCH /api/conversations/{id} modifie le titre d'une discussion."""
    mock_conv = Conversation(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        title="Original Title",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    async def custom_mock_db():
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value=mock_conv)
            )
        )
        session.commit = AsyncMock()
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            patch_res = await client.patch(f"/api/conversations/{mock_conv.id}", json={"title": "New Title"})
            assert patch_res.status_code == 200
            data = patch_res.json()
            assert data["title"] == "New Title"
    finally:
        from tests.conftest import mock_get_db
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_search_conversations():
    """GET /api/conversations?q= query filtre les résultats."""
    conv1 = Conversation(
        id=uuid.uuid4(),
        user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        title="Renovation Plomberie",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    async def custom_mock_db():
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(
                        all=MagicMock(return_value=[conv1])
                    )
                )
            )
        )
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            search_res = await client.get("/api/conversations", params={"q": "Plomb"})
            assert search_res.status_code == 200
            data = search_res.json()
            assert len(data) == 1
            assert "Plomberie" in data[0]["title"]
    finally:
        from tests.conftest import mock_get_db
        app.dependency_overrides[get_db] = mock_get_db
