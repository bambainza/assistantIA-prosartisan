"""Tests pour les routes et la validation de paiements Mobile Money."""

import hashlib
import hmac
import uuid
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app


@pytest.mark.asyncio
async def test_get_tarifs():
    """GET /api/payment/tarifs doit retourner la grille tarifaire."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/payment/tarifs")

    assert response.status_code == 200
    data = response.json()
    assert "offres" in data
    assert "pass_24h" in data["offres"]
    assert data["offres"]["pass_24h"]["montant"] == 500


@pytest.mark.asyncio
async def test_init_payment_success():
    """POST /api/payment/init doit créer une transaction et renvoyer l'URL de checkout."""
    test_user_id = str(uuid.uuid4())
    payload = {
        "user_id": test_user_id,
        "type_pass": "pass_24h"
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/payment/init", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "wave.com" in data["payment_url"] or "orange.ci" in data["payment_url"]


@pytest.mark.asyncio
async def test_webhook_hmac_validation():
    """POST /api/payment/webhook valide la signature HMAC SHA-256."""
    payload = {
        "transaction_id": "REF-TEST-123456",
        "status": "ACCEPTED",
        "metadata": {}
    }
    import json
    raw_body = json.dumps(payload).encode("utf-8")
    secret = settings.mobile_money_secret_key.encode("utf-8")
    valid_sig = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Sans signature (devrait passer si facultatif ou tester avec signature)
        response = await client.post("/api/payment/webhook", json=payload, headers={"X-Signature": valid_sig})

    assert response.status_code in [200, 404]  # 404 si la ref n'est pas en DB, mais la signature est valide
