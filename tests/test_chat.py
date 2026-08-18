"""Tests pour la route POST /api/chat et multimodalité."""

import uuid
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_chat_endpoint_success():
    """POST /api/chat répond correctement avec un quota disponible."""
    payload = {
        "user_id": str(uuid.uuid4()),
        "question": "Comment vérifier l'égalisation d'un sol avant pose de dalles ?",
        "metier_id": 1
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/chat", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert "reponse" in data
    assert len(data["reponse"]) > 0


@pytest.mark.asyncio
async def test_chat_endpoint_with_image():
    """POST /api/chat supporte l'envoi d'une photo de chantier."""
    payload = {
        "user_id": str(uuid.uuid4()),
        "question": "Est-ce que la fissure sur ce poteau en béton est dangereuse ?",
        "metier_id": 1,
        "image_url": "https://example.com/fissure_chantier.jpg"
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/chat", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert "reponse" in data
