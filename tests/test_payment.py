"""Tests pour les routes et la validation de paiements Mobile Money."""

import hashlib
import hmac
import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.db.session import get_db
from app.main import app
from app.middleware.auth import create_access_token
from app.models.transaction import TransactionMobileMoney


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
    """POST /api/payment/init (authentifié) crée une transaction et renvoie l'URL."""
    token = create_access_token(data={"sub": str(uuid.uuid4())})
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/payment/init",
            json={"type_pass": "pass_24h"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "wave.com" in data["payment_url"] or "orange.ci" in data["payment_url"]


@pytest.mark.asyncio
async def test_init_payment_exige_authentification():
    """POST /api/payment/init sans JWT est refusé (401) — plus de user_id arbitraire."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/payment/init", json={"type_pass": "pass_24h"}
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_webhook_hmac_validation():
    """POST /api/payment/webhook valide la signature HMAC SHA-256."""
    payload = {
        "transaction_id": "REF-TEST-123456",
        "status": "ACCEPTED",
        "metadata": {},
    }
    import json

    raw_body = json.dumps(payload).encode("utf-8")
    secret = settings.mobile_money_secret_key.encode("utf-8")
    valid_sig = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Sans signature (devrait passer si facultatif ou tester avec signature)
        response = await client.post(
            "/api/payment/webhook", json=payload, headers={"X-Signature": valid_sig}
        )

    assert response.status_code in [
        200,
        404,
    ]  # 404 si la ref n'est pas en DB, mais la signature est valide


@pytest.mark.asyncio
async def test_webhook_rejette_sans_signature():
    """POST /api/payment/webhook sans en-tête X-Signature doit être refusé (401)."""
    payload = {
        "transaction_id": "REF-TEST-123456",
        "status": "ACCEPTED",
        "metadata": {},
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/payment/webhook", json=payload)

    assert response.status_code == 401
    assert "Signature HMAC" in response.json()["detail"]


@pytest.mark.asyncio
async def test_webhook_rejette_signature_invalide():
    """POST /api/payment/webhook avec une signature erronée doit être refusé (401)."""
    payload = {
        "transaction_id": "REF-TEST-123456",
        "status": "ACCEPTED",
        "metadata": {},
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/payment/webhook",
            json=payload,
            headers={"X-Signature": "0" * 64},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_webhook_idempotent_sur_transaction_deja_creditee():
    """Un webhook rejoué sur une transaction déjà ACCEPTED ne re-crédite pas le Pass."""
    txn = TransactionMobileMoney(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        montant=3000,
        operateur="WAVE",
        statut_paiement="ACCEPTED",  # déjà traitée
        type_achat="pass_mois",
        reference_externe="REF-DEJA-TRAITEE",
    )

    quota_add = MagicMock()

    async def custom_mock_db():
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=txn))
        )
        session.commit = AsyncMock()
        session.add = quota_add
        yield session

    payload = {
        "transaction_id": "REF-DEJA-TRAITEE",
        "status": "ACCEPTED",
        "metadata": {},
    }
    raw_body = json.dumps(payload).encode("utf-8")
    secret = settings.mobile_money_secret_key.encode("utf-8")
    valid_sig = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()

    app.dependency_overrides[get_db] = custom_mock_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/payment/webhook",
                content=raw_body,
                headers={
                    "X-Signature": valid_sig,
                    "Content-Type": "application/json",
                },
            )

        assert response.status_code == 200
        assert "idempotent" in response.json()["message"]
        # Aucun quota premium ne doit avoir été (re)créé pour cette transaction
        quota_add.assert_not_called()
    finally:
        from tests.conftest import mock_get_db

        app.dependency_overrides[get_db] = mock_get_db
