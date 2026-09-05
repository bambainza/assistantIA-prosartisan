"""
Service de Transcription Audio (Speech-to-Text) via OpenAI Whisper.

Permet aux artisans d'enregistrer vocalement leurs questions sur le chantier
dans les langues locales ou français, et de les convertir en texte pour le RAG.
"""

from __future__ import annotations

import io
import logging
import os
import re

from fastapi import HTTPException, status
from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

SUPPORTED_AUDIO_EXTENSIONS = {
    "flac",
    "m4a",
    "mp3",
    "mp4",
    "mpeg",
    "mpga",
    "oga",
    "ogg",
    "wav",
    "webm",
}


class AudioService:
    """Service audio pour la transcription (Whisper) et la synthèse vocale (TTS)."""

    def __init__(self) -> None:
        self.openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

    def validate_audio_file(self, filename: str) -> str:
        """Valide l'extension du fichier audio fourni."""
        ext = os.path.splitext(filename)[1].lower().lstrip(".")
        if ext not in SUPPORTED_AUDIO_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Format audio '{ext}' non supporté. "
                    f"Formats acceptés : {', '.join(sorted(SUPPORTED_AUDIO_EXTENSIONS))}"
                ),
            )
        return ext

    async def transcribe_audio(
        self,
        file_bytes: bytes,
        filename: str = "audio.wav",
        prompt: str | None = None,
    ) -> str:
        """Transcrit un flux audio binaire en texte via OpenAI Whisper."""
        self.validate_audio_file(filename)

        if not file_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Le fichier audio fourni est vide.",
            )

        # Mode mock en environnement de développement ou test sans clé réelle
        if (
            settings.openai_api_key.startswith("sk-placeholder")
            or settings.openai_api_key == "sk-placeholder"
        ):
            return (
                "Bonjour l'expert, j'ai une fissure importante sur un mur porteur "
                "en parpaing sur mon chantier. Quel dosage de mortier dois-je appliquer ?"
            )

        try:
            # Créer un fichier mémoire en mode binaire avec nom pour OpenAI
            audio_buffer = io.BytesIO(file_bytes)
            audio_buffer.name = filename

            transcription = await self.openai_client.audio.transcriptions.create(
                model=settings.whisper_model,
                file=audio_buffer,
                prompt=prompt
                or "Vocabulaire BTP chantier ivoirien nouchi maçonnerie plomberie électricité",
            )
            return transcription.text.strip()
        except Exception as e:
            logger.error("Erreur lors de la transcription audio Whisper : %s", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Échec de la transcription audio : {e!s}",
            )

    async def synthesize_speech(
        self,
        text: str,
        voice: str | None = None,
        model: str | None = None,
    ) -> bytes:
        """Génère un flux audio MP3 à partir d'un texte via OpenAI TTS."""
        cleaned_text = text.strip()
        if not cleaned_text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Le texte à synthétiser ne peut pas être vide.",
            )

        # Nettoyage des balises Markdown basiques pour fluidifier la lecture vocale
        cleaned_text = re.sub(r"[\*#`_]", "", cleaned_text)
        cleaned_text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", cleaned_text)

        # Mode mock en environnement de développement ou test sans clé réelle
        if (
            settings.openai_api_key.startswith("sk-placeholder")
            or settings.openai_api_key == "sk-placeholder"
        ):
            # Octets audio MP3 simulés
            return b"\xff\xfb\x90d\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00ProsArtisanAudioMock"

        try:
            response = await self.openai_client.audio.speech.create(
                model=model or settings.tts_model,
                voice=voice or settings.tts_voice,
                input=cleaned_text[:4096],
            )
            return response.content
        except Exception as e:
            logger.error("Erreur lors de la synthèse vocale TTS : %s", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Échec de la synthèse vocale : {e!s}",
            )


audio_service = AudioService()
