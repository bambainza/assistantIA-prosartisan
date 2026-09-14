"""Tests pour le Web Push (abonnement navigateur, protocole VAPID).

Régression sécurité (anti-IDOR) : la désinscription filtre par `user_id` en
plus de l'`endpoint` — sans ce filtre, un artisan pourrait désabonner
l'appareil d'un autre compte en devinant/rejouant son endpoint.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.db.session import get_db
from app.main import app
from app.middleware.auth import create_access_token
from app.models.push_subscription import PushSubscription
from app.services.notification_service import WebPushProvider
from tests.conftest import mock_get_db


@pytest.mark.asyncio
async def test_vapid_public_key_accessible_sans_authentification():
    """GET /api/notifications/vapid-public-key est public (nécessaire avant login)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/notifications/vapid-public-key")
    assert res.status_code == 200
    assert res.json()["public_key"] == settings.vapid_public_key


@pytest.mark.asyncio
async def test_subscribe_web_push_cree_un_abonnement():
    """POST /api/notifications/web-push/subscribe enregistre un nouvel abonnement."""
    user_id = uuid.uuid4()

    async def custom_mock_db():
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )
        session.commit = AsyncMock()
        session.add = MagicMock()
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    token = create_access_token(data={"sub": str(user_id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/api/notifications/web-push/subscribe",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "endpoint": "https://fcm.googleapis.com/fcm/send/abc123",
                    "keys": {"p256dh": "p256dh-key-value", "auth": "auth-key-value"},
                },
            )
        assert res.status_code == 204
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_unsubscribe_web_push_filtre_par_proprietaire():
    """POST /api/notifications/web-push/unsubscribe filtre par user_id (anti-IDOR)."""
    user_id = uuid.uuid4()
    executed_statements = []

    async def custom_mock_db():
        session = MagicMock()

        async def mock_execute(stmt):
            executed_statements.append(stmt)
            return MagicMock()

        session.execute = mock_execute
        session.commit = AsyncMock()
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    token = create_access_token(data={"sub": str(user_id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/api/notifications/web-push/unsubscribe",
                headers={"Authorization": f"Bearer {token}"},
                json={"endpoint": "https://fcm.googleapis.com/fcm/send/abc123"},
            )
        assert res.status_code == 204
        # La requête DELETE doit filtrer sur user_id, pas seulement sur endpoint
        # (vérification structurelle : la valeur liée n'apparaît pas en clair
        # dans le SQL compilé, seul le nom de colonne y figure).
        assert any(
            "push_subscriptions.user_id" in str(stmt) for stmt in executed_statements
        )
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_web_push_provider_appelle_pywebpush_avec_les_bonnes_cles():
    """WebPushProvider transmet endpoint/clés/VAPID à pywebpush.webpush()."""
    subscription = PushSubscription(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        endpoint="https://fcm.googleapis.com/fcm/send/xyz",
        p256dh_key="p256dh-value",
        auth_key="auth-value",
    )
    provider = WebPushProvider()

    with patch("pywebpush.webpush") as mock_webpush:
        result = await provider.send_to_subscription(subscription, "Titre", "Corps")

    assert result is True
    assert mock_webpush.called
    _, kwargs = mock_webpush.call_args
    assert kwargs["subscription_info"]["endpoint"] == subscription.endpoint
    assert kwargs["subscription_info"]["keys"]["p256dh"] == "p256dh-value"
    assert kwargs["vapid_private_key"] == settings.vapid_private_key
