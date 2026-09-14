"""Tests pour le centre de notifications (in-app) et l'enregistrement d'appareil push.

Régression sécurité (anti-IDOR) : `mark_notification_read` filtre par
`user_id` en plus de l'ID de la notification — sans ce filtre, un artisan
pourrait marquer comme lue (ou sonder l'existence de) la notification d'un
autre compte simplement en devinant son UUID.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import get_db
from app.main import app
from app.middleware.auth import create_access_token
from app.models.notification import Notification
from app.models.user import User
from tests.conftest import mock_get_db


@pytest.fixture
def sample_notification():
    return Notification(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        channel="in_app",
        title="Pass expirant",
        body="Votre Pass Mensuel Pro expire dans 2 jours.",
        read_at=None,
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )


@pytest.mark.asyncio
async def test_list_notifications_authentifie(sample_notification):
    """GET /api/notifications retourne les notifications de l'utilisateur connecté."""
    user_id = sample_notification.user_id

    async def custom_mock_db():
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(
                        all=MagicMock(return_value=[sample_notification])
                    )
                )
            )
        )
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    token = create_access_token(data={"sub": str(user_id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get(
                "/api/notifications", headers={"Authorization": f"Bearer {token}"}
            )
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["title"] == "Pass expirant"
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_list_notifications_sans_token_refuse():
    """GET /api/notifications sans JWT doit retourner 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/notifications")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_mark_read_notification_dautrui_retourne_404():
    """Un artisan ne peut pas marquer comme lue la notification d'un autre compte (anti-IDOR)."""

    async def custom_mock_db():
        session = MagicMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = None  # Pas trouvée pour CE user_id
        session.execute = AsyncMock(return_value=mock_res)
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    token = create_access_token(data={"sub": str(uuid.uuid4())})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.patch(
                f"/api/notifications/{uuid.uuid4()}/read",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert res.status_code == 404
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_register_device_token():
    """POST /api/notifications/register-device enregistre le jeton FCM de l'utilisateur."""
    user = User(id=uuid.uuid4(), email="device@prosartisan.ci", is_admin=False)

    async def custom_mock_db():
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=user))
        )
        session.commit = AsyncMock()
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    token = create_access_token(data={"sub": str(user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/api/notifications/register-device",
                headers={"Authorization": f"Bearer {token}"},
                json={"fcm_token": "fcm-device-token-abcdef123456"},
            )
        assert res.status_code == 204
        assert user.fcm_device_token == "fcm-device-token-abcdef123456"
    finally:
        app.dependency_overrides[get_db] = mock_get_db
