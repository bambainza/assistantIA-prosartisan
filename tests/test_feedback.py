"""Tests pour l'enregistrement des feedbacks utilisateurs (pouce haut / bas)."""

import uuid

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
async def test_feedback_pouce_bas_avec_conversation():
    """Vérifie l'enregistrement d'un pouce bas (-1) avec conversation_id."""
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
