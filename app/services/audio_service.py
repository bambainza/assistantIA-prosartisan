"""
Service de Transcription Audio (Speech-to-Text) et de synthèse vocale (TTS)
via Mistral Voxtral.

Permet aux artisans d'enregistrer vocalement leurs questions sur le chantier
dans les langues locales ou français, et de les convertir en texte pour le RAG.
"""

from __future__ import annotations

import base64
import logging
import os
import re

from fastapi import HTTPException, status
from mistralai.client import Mistral
from mistralai.client.models import File

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

_DEFAULT_VOCABULAIRE_CHANTIER = (
    "Vocabulaire BTP chantier ivoirien nouchi maçonnerie plomberie électricité"
)


class AudioService:
    """Service audio pour la transcription (Voxtral STT) et la synthèse vocale (Voxtral TTS)."""

    def __init__(self) -> None:
        self.mistral_client = Mistral(api_key=settings.mistral_api_key)

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
        """Transcrit un flux audio binaire en texte via Mistral Voxtral (STT)."""
        self.validate_audio_file(filename)

        if not file_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Le fichier audio fourni est vide.",
            )

        # Mode mock en environnement de développement ou test sans clé réelle
        if (
            settings.mistral_api_key.startswith("sk-placeholder")
            or settings.mistral_api_key == "sk-placeholder"
        ):
            return (
                "Bonjour l'expert, j'ai une fissure importante sur un mur porteur "
                "en parpaing sur mon chantier. Quel dosage de mortier dois-je appliquer ?"
            )

        try:
            transcription = (
                await self.mistral_client.audio.transcriptions.complete_async(
                    model=settings.stt_model,
                    file=File(file_name=filename, content=file_bytes),
                    # Voxtral n'a pas de paramètre "prompt" libre comme Whisper :
                    # le vocabulaire attendu se fournit en indices contextuels —
                    # chaque élément doit être un seul mot, sans espace ni virgule
                    # (rejeté en 400 sinon), d'où l'éclatement en mots individuels.
                    context_bias=(prompt or _DEFAULT_VOCABULAIRE_CHANTIER)
                    .replace(",", " ")
                    .split(),
                )
            )
            return transcription.text.strip()
        except Exception as e:
            logger.error("Erreur lors de la transcription audio Voxtral : %s", e)
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
        """Génère un flux audio MP3 à partir d'un texte via Mistral Voxtral TTS.

        `voice` doit être le `voice_id` d'une voix Voxtral — soit l'un des
        préréglages fournis par Mistral (`GET /v1/audio/voices?type=preset`,
        dont plusieurs voix françaises "fr_marie_*"), soit une voix clonée via
        leur console. `settings.tts_voice_id` (préréglage français par défaut)
        s'applique si non fourni à l'appel. Sans voice_id configuré, la
        synthèse échoue explicitement plutôt que d'utiliser une voix
        arbitraire.
        """
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
            settings.mistral_api_key.startswith("sk-placeholder")
            or settings.mistral_api_key == "sk-placeholder"
        ):
            # Octets audio MP3 simulés
            return b"\xff\xfb\x90d\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00ProsArtisanAudioMock"

        voice_id = voice or settings.tts_voice_id
        if not voice_id:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "Synthèse vocale indisponible : aucune voix Voxtral TTS "
                    "configurée (TTS_VOICE_ID). Créez une voix via la console "
                    "Mistral puis renseignez son identifiant."
                ),
            )

        try:
            response = await self.mistral_client.audio.speech.complete_async(
                model=model or settings.tts_model,
                voice_id=voice_id,
                input=cleaned_text[:4096],
                response_format="mp3",
            )
            return base64.b64decode(response.audio_data)
        except Exception as e:
            logger.error("Erreur lors de la synthèse vocale TTS : %s", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Échec de la synthèse vocale : {e!s}",
            )


audio_service = AudioService()
