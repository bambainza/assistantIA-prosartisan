"""
Router Chat : Assistant IA Multimodal (Texte, Photo GPT-4o Vision, WebSocket).

Intercepte les requêtes avec le Rate Limiter & Gestionnaire de Quota (HTTP 402 si épuisé).
"""

from __future__ import annotations

import base64
import json
import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.middleware.auth import get_optional_user_id, get_user_id_from_token
from app.models.feedback import Feedback
from app.schemas.calculator import (
    CalculateRequest,
    CalculateResponse,
    CalculatorInfo,
)
from app.schemas.chat import (
    ChatResponse,
    FeedbackCreate,
    FeedbackResponse,
    WebSocketMessage,
)
from app.schemas.quota import QuotaEpuiseResponse
from app.services.audio_service import audio_service
from app.services.cache_service import cache_service
from app.services.calculator_service import calculator_service
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
    """Transcrit une note vocale enregistrée sur le chantier via Mistral Voxtral (STT)."""
    audio_bytes = await file.read()
    filename = file.filename or "audio.wav"
    text = await audio_service.transcribe_audio(
        file_bytes=audio_bytes, filename=filename
    )
    return TranscribeResponse(text=text)


class SynthesizeRequest(BaseModel):
    text: str
    voice: str | None = None


@router.post("/chat/synthesize")
async def synthesize_speech_endpoint(
    payload: SynthesizeRequest,
    current_user_id: uuid.UUID | None = Depends(get_optional_user_id),
) -> Response:
    """Génère la lecture vocale (TTS) d'un texte et renvoie le flux audio MP3."""
    audio_bytes = await audio_service.synthesize_speech(
        text=payload.text, voice=payload.voice
    )
    return Response(content=audio_bytes, media_type="audio/mpeg")


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

    # 3. Génération RAG / Vision via Mistral avec historique
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
            detail="Quota insuffisant.",
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
async def chat_websocket_endpoint(
    websocket: WebSocket,
    db: AsyncSession = Depends(get_db),
    token: str | None = Query(default=None),
) -> None:
    """Connexion WebSocket bidirectionnelle temps réel pour mode texte et vocal mains-libres.

    Supporte :
    - Messages texte simples ou JSON (`{"type": "text", "content": "...", "metier_id": 1}`)
    - Notes vocales et flux audio (`{"type": "voice", "audio": "<base64>", "format": "wav"}`)
    - Streaming de réponse assistant (`type="stream"`, `type="stream_end"`)
    - Synthèse vocale automatique (`type="audio_response"`) pour usage mains-libres
    - Ping/Pong (`type="ping"` -> `type="pong"`)
    """
    user_id = ANONYMOUS_USER_ID
    if token:
        try:
            user_id = get_user_id_from_token(token)
        except HTTPException:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    await websocket.accept()
    try:
        while True:
            raw_data = await websocket.receive_text()

            question_text = ""
            metier_id = None
            is_voice_request = False

            try:
                parsed = json.loads(raw_data)
                if isinstance(parsed, dict):
                    msg_type = parsed.get("type", "text")

                    if msg_type == "ping":
                        await websocket.send_text(
                            WebSocketMessage(type="pong").model_dump_json()
                        )
                        continue

                    if msg_type in ("voice", "audio"):
                        is_voice_request = True
                        audio_b64 = parsed.get("audio") or parsed.get("data")
                        audio_format = parsed.get("format", "wav")
                        metier_id = parsed.get("metier_id")

                        if not audio_b64:
                            err_msg = WebSocketMessage(
                                type="error", message="Données audio manquantes."
                            )
                            await websocket.send_text(err_msg.model_dump_json())
                            continue

                        try:
                            audio_bytes = base64.b64decode(audio_b64)
                            transcription = await audio_service.transcribe_audio(
                                file_bytes=audio_bytes,
                                filename=f"voice.{audio_format}",
                            )
                            question_text = transcription.strip()
                            await websocket.send_text(
                                WebSocketMessage(
                                    type="user_transcription",
                                    text=question_text,
                                ).model_dump_json()
                            )
                        except Exception as e:
                            err_msg = WebSocketMessage(
                                type="error",
                                message=f"Échec de transcription vocale: {e!s}",
                            )
                            await websocket.send_text(err_msg.model_dump_json())
                            continue
                    else:
                        question_text = (
                            parsed.get("content")
                            or parsed.get("text")
                            or parsed.get("question")
                            or ""
                        )
                        metier_id = parsed.get("metier_id")
                        is_voice_request = bool(parsed.get("voice_output", False))
                else:
                    question_text = str(parsed)
            except (json.JSONDecodeError, TypeError):
                question_text = raw_data

            if not question_text:
                continue

            allowed = await quota_service.consume_quota(db=db, user_id=user_id)
            if not allowed:
                epuise_msg = WebSocketMessage(
                    type="payment_required",
                    message=QuotaEpuiseResponse().message,
                )
                await websocket.send_text(epuise_msg.model_dump_json())
                continue

            rag_res = await rag_service.generate_response(
                question=question_text, metier_id=metier_id
            )
            answer_text = rag_res.get("reponse", "")

            res_chunk = WebSocketMessage(
                type="stream",
                chunk="Voici les instructions pour votre chantier : ",
            )
            await websocket.send_text(res_chunk.model_dump_json())

            end_msg = WebSocketMessage(
                type="stream_end",
                message=answer_text,
                sources=rag_res.get("sources"),
            )
            await websocket.send_text(end_msg.model_dump_json())

            if is_voice_request and answer_text:
                try:
                    tts_bytes = await audio_service.synthesize_speech(
                        text=answer_text[:500]
                    )
                    audio_b64_res = base64.b64encode(tts_bytes).decode("ascii")
                    await websocket.send_text(
                        WebSocketMessage(
                            type="audio_response",
                            audio=audio_b64_res,
                            audio_format="audio/mp3",
                            is_final=True,
                        ).model_dump_json()
                    )
                except Exception:
                    pass

                await websocket.send_text(
                    WebSocketMessage(type="voice_turn_completed").model_dump_json()
                )
    except WebSocketDisconnect:
        pass


@router.post(
    "/chat/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enregistrer l'évaluation d'une réponse de l'assistant (pouce haut / pouce bas)",
)
async def submit_feedback(
    payload: FeedbackCreate,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_optional_user_id),
) -> FeedbackResponse:
    """Enregistre le feedback de l'artisan sur une réponse (+1 pour pouce haut, -1 pour bas)."""
    if payload.rating not in (1, -1):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Le rating doit être égal à 1 (positif) ou -1 (négatif).",
        )

    feedback = Feedback(
        id=uuid.uuid4(),
        user_id=user_id,
        conversation_id=payload.conversation_id,
        message_id=payload.message_id,
        rating=payload.rating,
        comment=payload.comment,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)

    return FeedbackResponse(
        id=feedback.id,
        status="ok",
        rating=feedback.rating,
        message_id=feedback.message_id,
        conversation_id=feedback.conversation_id,
    )


@router.get(
    "/chat/calculators",
    response_model=list[CalculatorInfo],
    summary="Lister les calculateurs et outils métiers disponibles",
)
async def list_calculators() -> list[CalculatorInfo]:
    """Retourne la liste des outils de calcul technique certifiés (béton, câbles, évacuations, revêtements, clim)."""
    tools = calculator_service.get_tool_definitions()
    return [
        CalculatorInfo(
            name=t["function"]["name"],
            description=t["function"]["description"],
            parameters=t["function"]["parameters"],
        )
        for t in tools
    ]


@router.post(
    "/chat/calculate",
    response_model=CalculateResponse,
    summary="Exécuter un calcul technique certifié",
)
async def execute_calculation(payload: CalculateRequest) -> CalculateResponse:
    """Exécute un calculateur métier (béton, électricité, plomberie, carrelage, clim)."""
    try:
        result = calculator_service.execute_tool(
            tool_name=payload.tool_name,
            arguments=payload.arguments,
        )
        try:
            await cache_service.increment(
                f"prosartisan:calculator:{payload.tool_name}:count"
            )
        except Exception:
            pass  # Ne bloque pas le calcul si le cache est indisponible

        return CalculateResponse(
            tool_name=payload.tool_name,
            status="success",
            result=result,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors du calcul : {exc!s}",
        )
