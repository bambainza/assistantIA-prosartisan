"""
Router Chat : Assistant IA Multimodal (Texte, Photo GPT-4o Vision, WebSocket).

Intercepte les requêtes avec le Rate Limiter & Gestionnaire de Quota (HTTP 402 si épuisé).
"""

from __future__ import annotations

import uuid

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.chat import ChatResponse, WebSocketMessage
from app.schemas.quota import QuotaEpuiseResponse
from app.services.chat_history_service import chat_history_service
from app.services.quota_service import quota_service
from app.services.rag_service import rag_service

router = APIRouter(prefix="/api", tags=["Chat IA Multimodal"])


class ExtendedChatRequest(BaseModel):
    user_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    question: str
    metier_id: int | None = None
    image_url: str | None = None  # Photo de chantier (URL ou Base64)


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    payload: ExtendedChatRequest,
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """Pose une question technique à l'assistant RAG (avec photo optionnelle)."""
    # Si aucun user_id n'est fourni, on utilise un ID temporaire/demo
    user_id = payload.user_id or uuid.UUID("00000000-0000-0000-0000-000000000001")

    # 1. Vérification et décrémentation des quotas
    allowed = await quota_service.consume_quota(db=db, user_id=user_id)
    if not allowed:
        epuise_detail = QuotaEpuiseResponse().model_dump()
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=epuise_detail,
        )

    # 2. Génération RAG / Vision via OpenAI
    rag_result = await rag_service.generate_response(
        question=payload.question,
        metier_id=payload.metier_id,
        image_url=payload.image_url,
    )

    # 3. Enregistrement de l'historique (avec fallback gracieux en cas d'erreur DB/autonome)
    active_conv_id = payload.conversation_id
    try:
        if not active_conv_id:
            title_preview = (
                payload.question[:30] + "..."
                if len(payload.question) > 30
                else payload.question
            )
            new_conv = await chat_history_service.create_conversation(
                db=db, user_id=user_id, title=title_preview
            )
            active_conv_id = new_conv.id
        else:
            conv = await chat_history_service.get_conversation_with_messages(
                db=db, conversation_id=active_conv_id
            )
            if not conv:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Discussion non trouvée.",
                )

        # Enregistrer le message de l'artisan
        await chat_history_service.add_message_to_conversation(
            db=db,
            conversation_id=active_conv_id,
            role="user",
            content=payload.question,
            image_url=payload.image_url,
        )

        # Enregistrer la réponse de l'assistant
        await chat_history_service.add_message_to_conversation(
            db=db,
            conversation_id=active_conv_id,
            role="assistant",
            content=rag_result["reponse"],
        )
    except HTTPException:
        raise
    except Exception:
        pass

    quota_info = await quota_service.get_user_quota_info(db=db, user_id=user_id)

    return ChatResponse(
        reponse=rag_result["reponse"],
        quota_info=quota_info,
        conversation_id=active_conv_id,
    )


@router.websocket("/chat/ws")
async def chat_websocket_endpoint(websocket: WebSocket) -> None:
    """Connexion WebSocket pour streaming de réponse en temps réel."""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            # Streaming mock message
            res_chunk = WebSocketMessage(
                type="stream",
                chunk="Voici les instructions pour votre chantier : ",
            )
            await websocket.send_text(res_chunk.model_dump_json())

            rag_res = await rag_service.generate_response(question=data)
            end_msg = WebSocketMessage(
                type="stream_end",
                message=rag_res["reponse"],
            )
            await websocket.send_text(end_msg.model_dump_json())
    except WebSocketDisconnect:
        pass
