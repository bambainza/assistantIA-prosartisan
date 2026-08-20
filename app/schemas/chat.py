"""Schémas Pydantic : Chat IA."""

import uuid

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
    """Message transitant via WebSocket."""

    type: str  # "stream", "stream_end", "payment_required", "payment_success", "error"
    chunk: str | None = None
    message: str | None = None
    action: str | None = None
