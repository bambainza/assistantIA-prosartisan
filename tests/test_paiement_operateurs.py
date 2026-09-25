"""Tests des parcours Wave Checkout / Orange Money WebPay (simulateur et clients réels)."""

import json
import time
import uuid
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import urlparse

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.db.session import get_db
from app.main import app
from app.middleware.auth import create_access_token
from app.models.quota import QuotaUtilisateur
from app.models.transaction import TransactionMobileMoney
from app.routers import payment as payment_router
from app.services.payment_providers import demo, orange_money, wave
from app.services.payment_providers.base import CheckoutRequest, StatutOperateur
from app.services.payment_service import (
    WebhookNonAuthentifieError,
    payment_service,
)


class FakeDB:
    """Session simulée : chaque `execute` renvoie le résultat suivant de la file."""

    def __init__(self, *resultats):
        self._resultats = list(resultats)
        self.ajouts = []
        self.commit = AsyncMock()

    def add(self, obj):
        self.ajouts.append(obj)

    async def execute(self, stmt):
        valeur = self._resultats.pop(0) if self._resultats else None
        liste = valeur if isinstance(valeur, list) else [valeur]
        return MagicMock(
            scalar_one_or_none=MagicMock(return_value=valeur),
            scalars=MagicMock(return_value=MagicMock(all=lambda: liste)),
        )


def _quota_cree(db: FakeDB) -> QuotaUtilisateur | None:
    return next((o for o in db.ajouts if isinstance(o, QuotaUtilisateur)), None)


async def _initier(operateur: str, type_pass: str = "pass_mois"):
    db = FakeDB()
    res = await payment_service.initialize_payment(
        db, uuid.uuid4(), type_pass, operateur
    )
    txn = next(o for o in db.ajouts if isinstance(o, TransactionMobileMoney))
    return res, txn


# ── Signature Wave ──


def _signer(body: bytes, secret: str | None = None, t: int | None = None) -> str:
    t = t or int(time.time())
    return f"t={t},v1={wave.sign_wave_payload(secret or settings.wave_webhook_secret, t, body)}"


def test_signature_wave_valide_et_falsifications():
    body = b'{"type":"checkout.session.completed"}'
    secret, tol = settings.wave_webhook_secret, 300

    assert wave.verify_wave_signature(_signer(body), body, secret, tol)
    assert not wave.verify_wave_signature(_signer(body), body + b" ", secret, tol)
    assert not wave.verify_wave_signature(_signer(body, "autre"), body, secret, tol)
    assert not wave.verify_wave_signature(None, body, secret, tol)
    assert not wave.verify_wave_signature("t=abc,v1=00", body, secret, tol)
    # Rejeu : horodatage hors fenêtre
    ancien = _signer(body, t=int(time.time()) - 3600)
    assert not wave.verify_wave_signature(ancien, body, secret, tol)
    # Rotation de secret : plusieurs v1, un seul valide suffit
    t = int(time.time())
    double = f"t={t},v1={'0' * 64},v1={wave.sign_wave_payload(secret, t, body)}"
    assert wave.verify_wave_signature(double, body, secret, tol)


# ── Parcours démo Wave ──


@pytest.mark.asyncio
async def test_demo_wave_parcours_complet_credite_le_pass():
    res, txn = await _initier("WAVE")
    assert res["mode"] == "demo"
    assert txn.provider_session_id.startswith("cos-")
    assert res["payment_url"].endswith(txn.provider_session_id)

    notification = await demo.decision_du_payeur(txn.provider_session_id, True)
    evenement = json.loads(notification.body)
    assert evenement["type"] == "checkout.session.completed"
    assert evenement["data"]["client_reference"] == txn.reference_externe
    assert "paiement=succes" in notification.redirect_url

    db = FakeDB(txn, None)
    resultat = await payment_service.handle_wave_webhook(
        db, notification.body, notification.headers["Wave-Signature"]
    )

    assert resultat["status"] == "success"
    assert txn.statut_paiement == "ACCEPTED"
    assert txn.provider_transaction_id.startswith("T_")
    assert _quota_cree(db).date_fin_premium is not None

    # Rejeu du même webhook : aucun second crédit
    db2 = FakeDB(txn)
    rejeu = await payment_service.handle_wave_webhook(
        db2, notification.body, notification.headers["Wave-Signature"]
    )
    assert "idempotent" in rejeu["message"]
    assert _quota_cree(db2) is None


@pytest.mark.asyncio
async def test_demo_wave_annulation_cloture_sans_credit():
    _, txn = await _initier("WAVE")
    notification = await demo.decision_du_payeur(txn.provider_session_id, False)

    db = FakeDB(txn)
    resultat = await payment_service.handle_wave_webhook(
        db, notification.body, notification.headers["Wave-Signature"]
    )

    assert json.loads(notification.body)["type"] == "checkout.session.payment_failed"
    assert resultat["status"] == "declined"
    assert txn.statut_paiement == "FAILED"
    assert _quota_cree(db) is None
    # Double clic : pas de seconde notification
    assert await demo.decision_du_payeur(txn.provider_session_id, True) is None


@pytest.mark.asyncio
async def test_wave_montant_altere_non_credite():
    """Un événement correctement signé mais d'un montant différent n'est pas crédité."""
    _, txn = await _initier("WAVE")
    body = json.dumps(
        {
            "id": "EV_x",
            "type": "checkout.session.completed",
            "data": {
                "id": txn.provider_session_id,
                "amount": "100",
                "currency": "XOF",
                "client_reference": txn.reference_externe,
                "payment_status": "succeeded",
            },
        }
    ).encode()

    db = FakeDB(txn)
    resultat = await payment_service.handle_wave_webhook(db, body, _signer(body))

    assert resultat["status"] == "montant_invalide"
    assert txn.statut_paiement == "PENDING"


@pytest.mark.asyncio
async def test_route_webhook_wave_sans_signature_401():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/payment/webhooks/wave", content=b"{}")

    assert response.status_code == 401


# ── Parcours démo Orange Money ──


@pytest.mark.asyncio
async def test_demo_orange_money_parcours_complet_credite_le_pack():
    _, txn = await _initier("ORANGE", "pack_50_requetes")
    assert txn.provider_session_id.startswith("v1")
    assert txn.provider_notif_token

    notification = await demo.decision_du_payeur(txn.provider_session_id, True)
    corps = json.loads(notification.body)
    assert corps == {
        "status": "SUCCESS",
        "notif_token": txn.provider_notif_token,
        "txnid": corps["txnid"],
    }

    db = FakeDB(txn, None)
    resultat = await payment_service.handle_orange_money_notification(
        db, notification.body
    )

    assert resultat["status"] == "success"
    assert txn.statut_paiement == "ACCEPTED"
    assert _quota_cree(db).credits_requetes == 50


@pytest.mark.asyncio
async def test_orange_money_notif_token_inconnu_rejete():
    body = json.dumps({"status": "SUCCESS", "notif_token": "faux", "txnid": "MP1"})
    with pytest.raises(WebhookNonAuthentifieError):
        await payment_service.handle_orange_money_notification(
            FakeDB(None), body.encode()
        )


@pytest.mark.asyncio
async def test_orange_money_notification_forgee_non_confirmee_non_creditee():
    """Bon notif_token mais aucun paiement réel : l'opérateur confirme PENDING → pas de crédit."""
    _, txn = await _initier("ORANGE")
    body = json.dumps(
        {"status": "SUCCESS", "notif_token": txn.provider_notif_token, "txnid": "MP1"}
    ).encode()

    db = FakeDB(txn)
    resultat = await payment_service.handle_orange_money_notification(db, body)

    assert resultat["status"] == "pending"
    assert txn.statut_paiement == "PENDING"
    assert _quota_cree(db) is None


# ── Routes du simulateur ──


@pytest.mark.asyncio
async def test_page_demo_et_decision_redirigent_et_notifient(monkeypatch):
    _, txn = await _initier("ORANGE")
    livrees = []

    async def _capturer(notification):
        livrees.append(notification)

    monkeypatch.setattr(payment_router, "_livrer_notification", _capturer)
    chemin = urlparse(txn.payment_url).path

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        page = await client.get(chemin)
        invalide = await client.post(
            chemin, data={"decision": "payer", "telephone": "0100000000", "code": "1"}
        )
        ok = await client.post(
            chemin,
            data={"decision": "payer", "telephone": "07 00 00 00 00", "code": "1234"},
        )

    assert page.status_code == 200
    assert "Simulateur de paiement ProsArtisan" in page.text
    assert "3000 F CFA" in page.text  # Pass Mensuel
    assert invalide.status_code == 422
    assert ok.status_code == 303
    assert "paiement=succes" in ok.headers["location"]
    assert len(livrees) == 1 and livrees[0].operateur == "ORANGE"


@pytest.mark.asyncio
async def test_demo_desactivee_en_production(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "payment_demo_in_production", False)

    assert payment_service.paiement_disponible() is False
    token = create_access_token(data={"sub": str(uuid.uuid4())})
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        init = await client.post(
            "/api/payment/init",
            json={"type_pass": "pass_24h"},
            headers={"Authorization": f"Bearer {token}"},
        )
        page = await client.get("/api/payment/demo/checkout/cos-inexistant")

    assert init.status_code == 503
    assert page.status_code == 404


# ── Clients API réels (requêtes vérifiées via un transport simulé) ──


def _transport_simule(monkeypatch, module, handler):
    reel = httpx.AsyncClient

    def _client(**kwargs):
        return reel(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(module.httpx, "AsyncClient", _client)


@pytest.mark.asyncio
async def test_client_wave_live_format_officiel(monkeypatch):
    monkeypatch.setattr(settings, "wave_api_key", "wave_ci_test_key")
    requetes = []

    def handler(request: httpx.Request) -> httpx.Response:
        requetes.append(request)
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "id": "cos-abc",
                    "wave_launch_url": "https://pay.wave.com/c/cos-abc",
                },
            )
        return httpx.Response(
            200,
            json={
                "id": "cos-abc",
                "amount": "500",
                "payment_status": "succeeded",
                "checkout_status": "complete",
                "transaction_id": "T_1",
            },
        )

    _transport_simule(monkeypatch, wave, handler)
    provider = wave.WaveLiveProvider()
    session = await provider.create_checkout(
        CheckoutRequest("REF-1", 500, "https://s", "https://e", "https://n")
    )
    txn = TransactionMobileMoney(provider_session_id="cos-abc", montant=500)
    etat = await provider.fetch_status(txn)

    post = requetes[0]
    assert str(post.url) == "https://api.wave.com/v1/checkout/sessions"
    assert post.headers["Authorization"] == "Bearer wave_ci_test_key"
    assert post.headers["Idempotency-Key"] == "REF-1"
    assert json.loads(post.content) == {
        "amount": "500",
        "currency": "XOF",
        "success_url": "https://s",
        "error_url": "https://e",
        "client_reference": "REF-1",
    }
    assert session.payment_url == "https://pay.wave.com/c/cos-abc"
    assert str(requetes[1].url).endswith("/v1/checkout/sessions/cos-abc")
    assert etat.statut is StatutOperateur.SUCCES and etat.montant == 500


@pytest.mark.asyncio
async def test_client_orange_money_live_format_officiel(monkeypatch):
    monkeypatch.setattr(settings, "orange_client_id", "cid")
    monkeypatch.setattr(settings, "orange_client_secret", "csecret")
    monkeypatch.setattr(settings, "orange_merchant_key", "mkey")
    requetes = []

    def handler(request: httpx.Request) -> httpx.Response:
        requetes.append(request)
        if request.url.path == "/oauth/v3/token":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        if request.url.path.endswith("/webpayment"):
            return httpx.Response(
                201,
                json={
                    "status": 201,
                    "pay_token": "v1pt",
                    "notif_token": "nt",
                    "payment_url": "https://webpayment.orange-money.com/pay/v1pt",
                },
            )
        return httpx.Response(200, json={"status": "SUCCESS", "txnid": "MP42"})

    _transport_simule(monkeypatch, orange_money, handler)
    provider = orange_money.OrangeMoneyLiveProvider()
    session = await provider.create_checkout(
        CheckoutRequest("REF-2", 1500, "https://s", "https://e", "https://n")
    )
    txn = TransactionMobileMoney(
        provider_session_id="v1pt", reference_externe="REF-2", montant=1500
    )
    etat = await provider.fetch_status(txn)

    token_req, pay_req, status_req = requetes
    assert token_req.headers["Authorization"] == "Basic Y2lkOmNzZWNyZXQ="
    assert b"grant_type=client_credentials" in token_req.content
    assert pay_req.url.path == "/orange-money-webpay/dev/v1/webpayment"
    assert pay_req.headers["Authorization"] == "Bearer tok"
    assert json.loads(pay_req.content) == {
        "merchant_key": "mkey",
        "currency": "OUV",
        "order_id": "REF-2",
        "amount": 1500,
        "return_url": "https://s",
        "cancel_url": "https://e",
        "notif_url": "https://n",
        "lang": "fr",
        "reference": "ProsArtisan",
    }
    assert (session.session_id, session.notif_token) == ("v1pt", "nt")
    assert json.loads(status_req.content) == {
        "order_id": "REF-2",
        "amount": 1500,
        "pay_token": "v1pt",
    }
    assert etat.statut is StatutOperateur.SUCCES and etat.transaction_id == "MP42"


# ── Réconciliation, suivi, configuration ──


@pytest.mark.asyncio
async def test_reconciliation_credite_un_paiement_dont_la_notification_est_perdue():
    _, txn = await _initier("WAVE", "pass_24h")
    await demo.decision_du_payeur(txn.provider_session_id, True)  # notification perdue

    db = FakeDB([txn], None)
    stats = await payment_service.reconcile_pending(db, older_than_minutes=0)

    assert stats == {"verifiees": 1, "creditees": 1, "cloturees": 0, "erreurs": 0}
    assert txn.statut_paiement == "ACCEPTED"


@pytest.mark.asyncio
async def test_suivi_transaction_filtre_par_proprietaire():
    async def _db_vide():
        yield FakeDB(None)

    from tests.conftest import mock_get_db

    app.dependency_overrides[get_db] = _db_vide
    try:
        token = create_access_token(data={"sub": str(uuid.uuid4())})
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/payment/transactions/{uuid.uuid4()}",
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        app.dependency_overrides[get_db] = mock_get_db

    assert response.status_code == 404


def test_production_live_exige_les_identifiants_operateurs():
    from app.config import Settings

    with pytest.raises(ValueError) as exc:
        Settings(
            app_env="production",
            app_debug=False,
            app_secret_key="s" * 32,
            jwt_secret_key="j" * 32,
            mobile_money_secret_key="m" * 32,
            db_password="p" * 16,
            vapid_private_key="v" * 32,
            cors_allowed_origins="https://prosartisan.ci",
            payment_mode="live",
            public_base_url="http://prosartisan.ci",
        )

    message = str(exc.value)
    for variable in (
        "WAVE_API_KEY",
        "WAVE_WEBHOOK_SECRET",
        "ORANGE_CLIENT_ID",
        "ORANGE_MERCHANT_KEY",
        "PUBLIC_BASE_URL",
    ):
        assert variable in message
