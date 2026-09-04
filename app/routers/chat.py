"""
Router Chat : Assistant IA Multimodal (Texte, Photo GPT-4o Vision, WebSocket).

Intercepte les requêtes avec le Rate Limiter & Gestionnaire de Quota (HTTP 402 si épuisé).
"""

from __future__ import annotations

import json
import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.middleware.auth import get_optional_user_id
from app.schemas.chat import ChatResponse, WebSocketMessage
from app.schemas.quota import QuotaEpuiseResponse
from app.services.audio_service import audio_service
from app.services.chat_history_service import chat_history_service
from app.services.quota_service import quota_service
from app.services.rag_service import rag_service

router = APIRouter(prefix="/api", tags=["Chat IA Multimodal"])

# Identité utilisée quand aucune authentification n'est fournie.
ANONYMOUS_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class TranscribeResponse(BaseModel):
    text: str


@router.post("/chat/transcribe", response_model=TranscribeResponse)
async def transcribe_audio_endpoint(
    file: UploadFile = File(...),
    current_user_id: uuid.UUID | None = Depends(get_optional_user_id),
) -> TranscribeResponse:
    """Transcrit une note vocale enregistrée sur le chantier via OpenAI Whisper."""
    audio_bytes = await file.read()
    filename = file.filename or "audio.wav"
    text = await audio_service.transcribe_audio(
        file_bytes=audio_bytes, filename=filename
    )
    return TranscribeResponse(text=text)


class ExtendedChatRequest(BaseModel):
    # L'utilisateur est déduit du JWT (ou anonyme), jamais transmis par le client.
    conversation_id: uuid.UUID | None = None
    question: str
    metier_id: int | None = None
    image_url: str | None = None  # Photo de chantier (URL ou Base64)


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    payload: ExtendedChatRequest,
    current_user_id: uuid.UUID | None = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """Pose une question technique à l'assistant RAG (avec photo optionnelle)."""
    user_id = current_user_id or ANONYMOUS_USER_ID

    # 1. Vérification et décrémentation des quotas
    allowed = await quota_service.consume_quota(db=db, user_id=user_id)
    if not allowed:
        epuise_detail = QuotaEpuiseResponse().model_dump()
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=epuise_detail,
        )

    # 2. Récupérer l'historique si la discussion existe (et appartient à l'artisan)
    history_messages = []
    if payload.conversation_id:
        conv = await chat_history_service.get_conversation_with_messages(
            db=db, conversation_id=payload.conversation_id, user_id=user_id
        )
        if conv and conv.messages:
            sorted_msgs = sorted(conv.messages, key=lambda m: m.created_at)
            for m in sorted_msgs[-10:]:
                history_messages.append({"role": m.role, "content": m.content})

    # 3. Génération RAG / Vision via OpenAI avec historique
    rag_result = await rag_service.generate_response(
        question=payload.question,
        metier_id=payload.metier_id,
        image_url=payload.image_url,
        history=history_messages,
    )

    # 4. Enregistrement de l'historique (avec fallback gracieux en cas d'erreur DB/autonome)
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
                db=db, conversation_id=active_conv_id, user_id=user_id
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
        sources=rag_result["sources"],
    )


@router.post("/chat/stream")
async def chat_stream_endpoint(
    payload: ExtendedChatRequest,
    current_user_id: uuid.UUID | None = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Pose une question technique et retourne la réponse en streaming SSE."""
    user_id = current_user_id or ANONYMOUS_USER_ID

    # 1. Vérification et décrémentation des quotas
    allowed = await quota_service.consume_quota(db=db, user_id=user_id)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Quota suffisant.",
        )

    # 2. Récupérer l'historique si la discussion existe (et appartient à l'artisan)
    history_messages = []
    if payload.conversation_id:
        conv = await chat_history_service.get_conversation_with_messages(
            db=db, conversation_id=payload.conversation_id, user_id=user_id
        )
        if conv and conv.messages:
            sorted_msgs = sorted(conv.messages, key=lambda m: m.created_at)
            for m in sorted_msgs[-10:]:
                history_messages.append({"role": m.role, "content": m.content})

    # 3. Résoudre/Créer la conversation
    active_conv_id = payload.conversation_id
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

    # 4. Récupérer les sources et le générateur du RAG
    sources, stream_generator = await rag_service.generate_response_stream(
        question=payload.question,
        metier_id=payload.metier_id,
        image_url=payload.image_url,
        history=history_messages,
    )

    async def event_generator():
        # Yield conversation_id and sources first
        info_data = {
            "conversation_id": str(active_conv_id),
            "sources": sources,
        }
        yield f"event: info\ndata: {json.dumps(info_data)}\n\n"

        full_response = ""
        # Récupérer le flux RAG
        async for chunk in stream_generator:
            full_response += chunk
            yield f"event: chunk\ndata: {json.dumps(chunk)}\n\n"

        # Enregistrer dans l'historique une fois terminé
        try:
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
                content=full_response,
            )
        except Exception:
            pass

        yield "event: end\ndata: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


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
