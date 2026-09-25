"""Tests pour le WebSocket /api/chat/ws : authentification et décompte de quota."""

import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.middleware.auth import create_access_token
from app.services.audio_service import audio_service
from app.services.chat_history_service import chat_history_service
from app.services.quota_service import quota_service


def _recevoir_jusqu_a(websocket, type_attendu: str) -> list[dict]:
    """Collecte les messages jusqu'au premier de type `type_attendu` (inclus)."""
    messages = []
    while True:
        msg = websocket.receive_json()
        messages.append(msg)
        if msg["type"] == type_attendu:
            return messages


def test_websocket_avec_token_valide_recoit_une_reponse():
    """Un JWT valide envoyé dans le premier message authentifie la connexion."""
    token = create_access_token(data={"sub": str(uuid.uuid4())})
    with TestClient(app).websocket_connect("/api/chat/ws") as websocket:
        websocket.send_json({"action": "auth", "token": token})
        websocket.send_text("Comment poser du carrelage ?")
        messages = _recevoir_jusqu_a(websocket, "stream_end")

    assert messages[-1]["type"] == "stream_end"


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

    async def _refuse(db, user_id, client_ip=None):
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
        messages = _recevoir_jusqu_a(websocket, "stream_end")

    chunks = [m["chunk"] for m in messages if m["type"] == "stream"]
    end_msg = messages[-1]
    # Vrai streaming : plusieurs fragments, dont la concaténation est la réponse.
    assert len(chunks) > 1
    assert "".join(chunks).strip() == end_msg["message"]
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

        # 2-3. Fragments streamés puis stream_end
        messages = _recevoir_jusqu_a(websocket, "stream_end")
        assert messages[0]["type"] == "stream"
        assert len(messages[-1]["message"]) > 0

        # 4. Événement audio_response TTS
        audio_msg = websocket.receive_json()
        assert audio_msg["type"] == "audio_response"
        assert audio_msg["audio"] is not None
        assert audio_msg["audio_format"] == "audio/mp3"

        # 5. Signal de fin de tour vocal
        turn_msg = websocket.receive_json()
        assert turn_msg["type"] == "voice_turn_completed"


def test_websocket_quota_epuise_ne_transcrit_pas_l_audio(monkeypatch):
    """Quota épuisé : aucun appel Voxtral STT (facturé) n'est effectué."""
    import base64

    async def _refuse(db, user_id, client_ip=None):
        return False

    appels_stt = []

    async def _stt(**kwargs):
        appels_stt.append(kwargs)
        return "texte"

    monkeypatch.setattr(quota_service, "consume_quota", _refuse)
    monkeypatch.setattr(audio_service, "transcribe_audio", _stt)

    with TestClient(app).websocket_connect("/api/chat/ws") as websocket:
        websocket.send_json(
            {"type": "voice", "audio": base64.b64encode(b"RIFF").decode("ascii")}
        )
        msg = websocket.receive_json()

    assert msg["type"] == "payment_required"
    assert appels_stt == []


def test_websocket_accepte_le_format_audio_chunk_de_chat_web(monkeypatch):
    """Format réellement envoyé par chat_web : action=audio_chunk + audio_format MIME."""
    import base64

    fichiers = []

    async def _stt(file_bytes, filename):
        fichiers.append(filename)
        return "Comment poser du carrelage ?"

    monkeypatch.setattr(audio_service, "transcribe_audio", _stt)

    with TestClient(app).websocket_connect("/api/chat/ws") as websocket:
        websocket.send_json(
            {
                "action": "audio_chunk",
                "audio": base64.b64encode(b"webm-data").decode("ascii"),
                "audio_format": "audio/webm;codecs=opus",
            }
        )
        messages = _recevoir_jusqu_a(websocket, "voice_turn_completed")

    assert fichiers == ["voice.webm"]
    assert messages[0]["type"] == "user_transcription"
    assert any(m["type"] == "stream_end" for m in messages)


def test_websocket_discussion_d_un_tiers_refusee(monkeypatch):
    """Anti-IDOR : une conversation_id qui n'appartient pas à l'appelant est refusée."""

    async def _introuvable(**kwargs):
        return None

    monkeypatch.setattr(
        chat_history_service, "get_conversation_with_messages", _introuvable
    )

    token = create_access_token(data={"sub": str(uuid.uuid4())})
    with TestClient(app).websocket_connect("/api/chat/ws") as websocket:
        websocket.send_json({"action": "auth", "token": token})
        websocket.send_json(
            {"content": "Dosage béton ?", "conversation_id": str(uuid.uuid4())}
        )
        msg = websocket.receive_json()

    assert msg["type"] == "error"
    assert "Discussion" in msg["message"]


def test_websocket_anonyme_ne_peut_pas_rattacher_une_discussion():
    """Sans connexion, aucune discussion n'est chargée ni enregistrée côté serveur."""
    with TestClient(app).websocket_connect("/api/chat/ws") as websocket:
        websocket.send_json(
            {"content": "Dosage béton ?", "conversation_id": str(uuid.uuid4())}
        )
        msg = websocket.receive_json()

    assert msg["type"] == "error"
    assert "Connectez-vous" in msg["message"]


def test_websocket_enregistre_l_historique_de_la_discussion(monkeypatch):
    """Avec une discussion rattachée, question et réponse sont enregistrées."""
    from unittest.mock import MagicMock

    conv_id = uuid.uuid4()
    enregistres = []

    async def _conversation(**kwargs):
        return MagicMock(messages=[])

    async def _ajouter(**kwargs):
        enregistres.append((kwargs["role"], kwargs["content"]))

    monkeypatch.setattr(
        chat_history_service, "get_conversation_with_messages", _conversation
    )
    monkeypatch.setattr(chat_history_service, "add_message_to_conversation", _ajouter)

    token = create_access_token(data={"sub": str(uuid.uuid4())})
    with TestClient(app).websocket_connect("/api/chat/ws") as websocket:
        websocket.send_json(
            {"action": "auth", "token": token, "conversation_id": str(conv_id)}
        )
        websocket.send_text("Dosage béton ?")
        _recevoir_jusqu_a(websocket, "stream_end")

    assert [role for role, _ in enregistres] == ["user", "assistant"]
    assert enregistres[0][1] == "Dosage béton ?"


def test_websocket_erreur_du_fournisseur_ia_ne_ferme_pas_la_session(monkeypatch):
    """Ex. quota Mistral dépassé (429) : message d'erreur, puis la session reste utilisable."""
    from app.services.rag_service import rag_service

    appels = {"n": 0}
    original = rag_service.generate_response_stream

    async def _stream(**kwargs):
        appels["n"] += 1
        if appels["n"] == 1:
            raise RuntimeError("Status 429 Rate limit exceeded")
        return await original(**kwargs)

    monkeypatch.setattr(rag_service, "generate_response_stream", _stream)

    with TestClient(app).websocket_connect("/api/chat/ws") as websocket:
        websocket.send_text("Première question ?")
        erreur = websocket.receive_json()
        websocket.send_text("Deuxième question ?")
        messages = _recevoir_jusqu_a(websocket, "stream_end")

    assert erreur["type"] == "error"
    assert "indisponible" in erreur["message"]
    assert messages[-1]["message"]
