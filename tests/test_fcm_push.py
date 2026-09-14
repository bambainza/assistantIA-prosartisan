"""Tests pour le provider FCM (API HTTP v1, authentification par compte de service)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.services.notification_service import FcmPushProvider


@pytest.mark.asyncio
async def test_fcm_send_no_op_sans_compte_de_service():
    """Sans FCM_SERVICE_ACCOUNT_PATH configuré, l'envoi est un no-op silencieux (pas d'exception)."""
    original = settings.fcm_service_account_path
    settings.fcm_service_account_path = ""
    try:
        provider = FcmPushProvider()
        result = await provider.send(
            target="device-token-abc", title="Titre", body="Corps"
        )
        assert result is False
    finally:
        settings.fcm_service_account_path = original


@pytest.mark.asyncio
async def test_fcm_send_no_op_sans_device_token():
    """Sans device token cible, l'envoi est un no-op (rien à appeler)."""
    provider = FcmPushProvider()
    result = await provider.send(target="", title="Titre", body="Corps")
    assert result is False


@pytest.mark.asyncio
async def test_fcm_send_appelle_lapi_v1_avec_le_bon_projet():
    """Avec des credentials valides, l'envoi cible l'endpoint v1 du bon projet Firebase."""
    provider = FcmPushProvider()

    fake_credentials = MagicMock()
    fake_credentials.valid = True
    fake_credentials.token = "fake-oauth2-token"
    provider._credentials = fake_credentials
    provider._project_id = "assistantia-app"
    provider._load_attempted = True

    mock_response = MagicMock(status_code=200)
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await provider.send(
            target="device-token-xyz", title="Titre", body="Corps"
        )

    assert result is True
    call_args = mock_client.post.call_args
    assert "assistantia-app" in call_args.args[0]
    assert call_args.kwargs["headers"]["Authorization"] == "Bearer fake-oauth2-token"
    assert call_args.kwargs["json"]["message"]["token"] == "device-token-xyz"
