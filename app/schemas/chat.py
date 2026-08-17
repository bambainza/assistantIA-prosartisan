"""Schémas Pydantic : Chat IA."""

from pydantic import BaseModel


class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    reponse: str
    quota_info: dict | None = None


class WebSocketMessage(BaseModel):
    """Message transitant via WebSocket."""

    type: str  # "stream", "stream_end", "payment_required", "payment_success", "error"
    chunk: str | None = None
    message: str | None = None
    action: str | None = None
