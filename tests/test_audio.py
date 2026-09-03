"""Tests pour le service audio Whisper et l'endpoint /api/chat/transcribe."""

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.audio_service import AudioService, audio_service


def test_audio_service_validation():
    """Valide la détection des extensions de fichiers audio supportés."""
    service = AudioService()

    # Formats autorisés
    assert service.validate_audio_file("vocal.wav") == "wav"
    assert service.validate_audio_file("note.mp3") == "mp3"
    assert service.validate_audio_file("chantier.m4a") == "m4a"
    assert service.validate_audio_file("enregistrement.webm") == "webm"
    assert service.validate_audio_file("audio.ogg") == "ogg"

    # Formats non autorisés
    with pytest.raises(HTTPException) as exc:
        service.validate_audio_file("document.pdf")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_audio_service_empty_bytes():
    """Vérifie qu'un fichier audio vide lève une erreur 400."""
    service = AudioService()
    with pytest.raises(HTTPException) as exc:
        await service.transcribe_audio(file_bytes=b"", filename="test.wav")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_audio_service_mock_transcription():
    """Vérifie le retour mock en environnement de dev/test."""
    text = await audio_service.transcribe_audio(
        file_bytes=b"RIFFdummywavdata", filename="note.wav"
    )
    assert isinstance(text, str)
    assert len(text) > 0


@pytest.mark.asyncio
async def test_transcribe_endpoint_success():
    """POST /api/chat/transcribe accepte un fichier audio et retourne la transcription."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        files = {"file": ("chantier_voice.wav", b"RIFFmockwavheaderdata", "audio/wav")}
        response = await client.post("/api/chat/transcribe", files=files)

    assert response.status_code == 200
    data = response.json()
    assert "text" in data
    assert len(data["text"]) > 0


@pytest.mark.asyncio
async def test_transcribe_endpoint_invalid_format():
    """POST /api/chat/transcribe rejette un fichier non audio avec HTTP 400."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        files = {"file": ("devis.pdf", b"%PDF-1.4 dummy", "application/pdf")}
        response = await client.post("/api/chat/transcribe", files=files)

    assert response.status_code == 400
