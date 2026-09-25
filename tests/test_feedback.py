"""Tests pour l'enregistrement des feedbacks utilisateurs (pouce haut / bas)."""

import uuid
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_feedback_pouce_haut_success():
    """Vérifie l'enregistrement d'un pouce haut (+1)."""
    payload = {
        "rating": 1,
        "message_id": "msg-12345",
        "comment": "Explication claire pour le dosage du mortier.",
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/chat/feedback", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "ok"
    assert data["rating"] == 1
    assert data["message_id"] == "msg-12345"
    assert "id" in data


@pytest.mark.asyncio
async def test_feedback_pouce_bas_avec_conversation(monkeypatch):
    """Vérifie l'enregistrement d'un pouce bas (-1) sur une discussion de l'appelant."""
    from app.services.chat_history_service import chat_history_service

    async def _conversation_de_l_appelant(**kwargs):
        return MagicMock()

    monkeypatch.setattr(
        chat_history_service,
        "get_conversation_with_messages",
        _conversation_de_l_appelant,
    )
    conv_id = str(uuid.uuid4())
    payload = {
        "rating": -1,
        "conversation_id": conv_id,
        "message_id": "msg-67890",
        "comment": "Manque de précision sur la marque du disjoncteur.",
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/chat/feedback", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "ok"
    assert data["rating"] == -1
    assert data["conversation_id"] == conv_id


@pytest.mark.asyncio
async def test_feedback_rating_invalide_rejete():
    """Un rating différent de 1 ou -1 doit être rejeté (HTTP 422)."""
    payload = {
        "rating": 0,
        "message_id": "msg-invalide",
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/chat/feedback", json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_feedback_sur_discussion_d_un_tiers_refuse(monkeypatch):
    """Anti-IDOR : noter la discussion d'un autre utilisateur renvoie 404."""
    from app.services.chat_history_service import chat_history_service

    async def _introuvable(**kwargs):
        return None

    monkeypatch.setattr(
        chat_history_service, "get_conversation_with_messages", _introuvable
    )
    payload = {"rating": 1, "conversation_id": str(uuid.uuid4())}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/chat/feedback", json=payload)

    assert response.status_code == 404
