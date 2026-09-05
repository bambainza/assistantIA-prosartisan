"""Tests pour le WebSocket /api/chat/ws : authentification et décompte de quota."""

import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.middleware.auth import create_access_token
from app.services.quota_service import quota_service


def test_websocket_avec_token_valide_recoit_une_reponse():
    """Un JWT valide passé en query param authentifie la connexion."""
    token = create_access_token(data={"sub": str(uuid.uuid4())})
    with TestClient(app).websocket_connect(f"/api/chat/ws?token={token}") as websocket:
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
        TestClient(app).websocket_connect("/api/chat/ws?token=invalide") as websocket,
    ):
        websocket.receive_json()

    assert exc_info.value.code == 1008


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
