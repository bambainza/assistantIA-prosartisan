"""
Service de Transcription Audio (Speech-to-Text) via OpenAI Whisper.

Permet aux artisans d'enregistrer vocalement leurs questions sur le chantier
dans les langues locales ou français, et de les convertir en texte pour le RAG.
"""

from __future__ import annotations

import io
import logging
import os
from typing import Any

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
    """Service de transcription audio s'appuyant sur l'API Whisper."""

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
                detail=f"Échec de la transcription audio : {str(e)}",
            )


audio_service = AudioService()
