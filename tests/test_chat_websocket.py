"""Tests pour le WebSocket /api/chat/ws : authentification et décompte de quota."""

import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.middleware.auth import create_access_token
from app.services.quota_service import quota_service


def test_websocket_avec_token_valide_recoit_une_reponse():
    """Un JWT valide envoyé dans le premier message authentifie la connexion."""
    token = create_access_token(data={"sub": str(uuid.uuid4())})
    with TestClient(app).websocket_connect("/api/chat/ws") as websocket:
        websocket.send_json({"action": "auth", "token": token})
        websocket.send_text("Comment poser du carrelage ?")
        websocket.receive_json()
        end_msg = websocket.receive_json()

    assert end_msg["type"] == "stream_end"


def test_websocket_token_invalide_ferme_la_connexion():
    """Un token invalide ferme la connexion (policy violation) avant tout échange."""
    import pytest
    from starlette.websockets import WebSocketDisconnect

    with (
        pytest.raises(WebSocketDisconnect) as exc_info,
        TestClient(app).websocket_connect("/api/chat/ws") as websocket,
    ):
        websocket.send_json({"action": "auth", "token": "invalide"})
        websocket.receive_json()

    assert exc_info.value.code == 1008


def test_websocket_ignore_un_jeton_dans_url():
    """Un JWT présent dans l'URL n'est plus utilisé par le serveur."""
    with TestClient(app).websocket_connect(
        "/api/chat/ws?token=secret-a-ne-pas-journaliser"
    ) as websocket:
        websocket.send_text('{"type":"ping"}')
        assert websocket.receive_json()["type"] == "pong"


def test_websocket_quota_epuise_renvoie_payment_required(monkeypatch):
    """Quota épuisé : le WebSocket répond `payment_required` au lieu d'appeler le LLM."""

    async def _refuse(db, user_id):
        return False

    monkeypatch.setattr(quota_service, "consume_quota", _refuse)

    with TestClient(app).websocket_connect("/api/chat/ws") as websocket:
        websocket.send_text("Comment poser du carrelage ?")
        msg = websocket.receive_json()

    assert msg["type"] == "payment_required"


def test_websocket_anonyme_recoit_une_reponse():
    """Sans token, le WebSocket répond quand même (compte anonyme partagé)."""
    with TestClient(app).websocket_connect("/api/chat/ws") as websocket:
        websocket.send_text("Comment poser du carrelage ?")
        stream_msg = websocket.receive_json()
        end_msg = websocket.receive_json()

    assert stream_msg["type"] == "stream"
    assert end_msg["type"] == "stream_end"
    assert end_msg["message"]


def test_websocket_ping_pong():
    """Vérifie que l'envoi d'un ping JSON renvoie un pong immédiat."""
    import json

    with TestClient(app).websocket_connect("/api/chat/ws") as websocket:
        websocket.send_text(json.dumps({"type": "ping"}))
        msg = websocket.receive_json()

    assert msg["type"] == "pong"


def test_websocket_voice_turn_mains_libres():
    """Vérifie le tour de parole vocal complet : envoi d'audio base64 -> transcription -> stream -> réponse audio TTS."""
    import base64
    import json

    dummy_wav = b"RIFFmockwavheaderdata"
    audio_b64 = base64.b64encode(dummy_wav).decode("ascii")

    with TestClient(app).websocket_connect("/api/chat/ws") as websocket:
        payload = {
            "type": "voice",
            "audio": audio_b64,
            "format": "wav",
            "metier_id": 1,
        }
        websocket.send_text(json.dumps(payload))

        # 1. Événement transcription utilisateur
        t_msg = websocket.receive_json()
        assert t_msg["type"] == "user_transcription"
        assert len(t_msg["text"]) > 0

        # 2. Événement stream assistant
        s_msg = websocket.receive_json()
        assert s_msg["type"] == "stream"

        # 3. Événement stream_end
        end_msg = websocket.receive_json()
        assert end_msg["type"] == "stream_end"
        assert len(end_msg["message"]) > 0

        # 4. Événement audio_response TTS
        audio_msg = websocket.receive_json()
        assert audio_msg["type"] == "audio_response"
        assert audio_msg["audio"] is not None
        assert audio_msg["audio_format"] == "audio/mp3"

        # 5. Signal de fin de tour vocal
        turn_msg = websocket.receive_json()
        assert turn_msg["type"] == "voice_turn_completed"
