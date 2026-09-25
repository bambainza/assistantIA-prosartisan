"""Schémas Pydantic : Conversations & Messages."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, field_serializer

from app.services.media_service import media_service


class MessageResponse(BaseModel):
    """Schéma de retour pour un message."""

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    image_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("image_url")
    def _url_signee(self, image_url: str | None) -> str | None:
        """Référence `media:<nom>` → URL signée temporaire (voir media_service)."""
        return media_service.public_url(image_url)


class ConversationResponse(BaseModel):
    """Schéma de retour pour les métadonnées d'une discussion."""

    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetailResponse(ConversationResponse):
    """Schéma complet incluant les messages triés d'une discussion."""

    messages: list[MessageResponse] = []


class ConversationCreate(BaseModel):
    """Corps de requête pour initialiser une discussion."""

    title: str | None = None


class ConversationUpdate(BaseModel):
    """Corps de requête pour modifier le titre d'une discussion."""

    title: str
