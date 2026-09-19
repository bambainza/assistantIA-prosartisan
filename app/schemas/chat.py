"""Schémas Pydantic : Chat IA."""

import uuid
from typing import Any

from pydantic import BaseModel


class ChatRequest(BaseModel):
    question: str


class SourceInfo(BaseModel):
    document_name: str
    relevance_score: float | None = None
    metier_id: int | None = None


class ChatResponse(BaseModel):
    reponse: str
    quota_info: dict | None = None
    conversation_id: uuid.UUID | None = None
    sources: list[SourceInfo] | None = None


class WebSocketMessage(BaseModel):
    """Message transitant via WebSocket (texte, streaming, audio Voxtral, contrôles de session)."""

    type: str  # "stream", "stream_end", "user_transcription", "audio_response", "voice_turn_completed", "payment_required", "error", "pong"
    chunk: str | None = None
    text: str | None = None
    message: str | None = None
    action: str | None = None
    audio: str | None = None  # Base64 encoded audio
    audio_format: str | None = None  # "audio/mp3", "audio/wav"
    sources: list[dict[str, Any]] | None = None
    is_final: bool | None = None


class FeedbackCreate(BaseModel):
    """Schéma de création d'un feedback utilisateur (pouce haut/bas)."""

    rating: int  # 1 ou -1
    message_id: str | None = None
    conversation_id: uuid.UUID | None = None
    comment: str | None = None


class FeedbackResponse(BaseModel):
    """Schéma de réponse après enregistrement d'un feedback."""

    id: uuid.UUID
    status: str = "ok"
    rating: int
    message_id: str | None = None
    conversation_id: uuid.UUID | None = None
