"""
Router Chat : Assistant IA Multimodal (Texte, Photo via la vision Mistral, Voix Voxtral, WebSocket).

Intercepte les requêtes avec le Rate Limiter & Gestionnaire de Quota (HTTP 402 si épuisé).
"""

from __future__ import annotations

import base64
import json
import logging
import uuid
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.middleware.auth import get_optional_user_id, get_user_id_from_token
from app.middleware.client_ip import get_client_ip
from app.middleware.rate_limiter import RATE_LIMIT_MESSAGE, is_rate_limited
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
from app.services.media_service import PreparedImage, media_service
from app.services.quota_service import QuotaIndisponibleError, quota_service
from app.services.rag_service import rag_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Chat IA Multimodal"])

# Aucun historique n'est conservé côté serveur pour un visiteur non connecté
# (il le garde dans son navigateur) ; son quota est compté par IP cliente.
CONNEXION_REQUISE_DISCUSSION = (
    "Connectez-vous pour enregistrer ou reprendre une discussion."
)

# Limites d'entrée : chaque appel Mistral (LLM, vision, STT, TTS) est facturé,
# une entrée non bornée permettrait de faire exploser les coûts en une requête.
MAX_QUESTION_CHARS = 4000
MAX_IMAGE_URL_CHARS = 10_000_000  # ~7 Mo d'image encodée en Base64
MAX_AUDIO_BYTES = 10 * 1024 * 1024
MAX_TTS_CHARS = 2000

# Message affiché quand le fournisseur IA échoue en cours de réponse (quota
# Mistral dépassé, coupure réseau...) : la connexion reste ouverte et exploitable.
ASSISTANT_INDISPONIBLE_MESSAGE = (
    "⚠️ L'assistant est momentanément indisponible. Réessayez dans un instant."
)


class TranscribeResponse(BaseModel):
    text: str


@router.post("/chat/transcribe", response_model=TranscribeResponse)
async def transcribe_audio_endpoint(
    file: UploadFile = File(...),
    current_user_id: uuid.UUID | None = Depends(get_optional_user_id),
) -> TranscribeResponse:
    """Transcrit une note vocale enregistrée sur le chantier via Mistral Voxtral (STT)."""
    audio_bytes = await file.read(MAX_AUDIO_BYTES + 1)
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Note vocale trop volumineuse (10 Mo maximum).",
        )
    filename = file.filename or "audio.wav"
    text = await audio_service.transcribe_audio(
        file_bytes=audio_bytes, filename=filename
    )
    return TranscribeResponse(text=text)


class SynthesizeRequest(BaseModel):
    text: str = Field(..., max_length=MAX_TTS_CHARS)
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
    question: str = Field(..., min_length=1, max_length=MAX_QUESTION_CHARS)
    metier_id: int | None = None
    # Photo de chantier (URL ou Base64)
    image_url: str | None = Field(default=None, max_length=MAX_IMAGE_URL_CHARS)


async def _historique_de_la_discussion(
    db: AsyncSession,
    current_user_id: uuid.UUID | None,
    conversation_id: uuid.UUID | None,
) -> list[dict[str, str]]:
    """Charge les 10 derniers messages d'une discussion de l'appelant.

    - visiteur non connecté + `conversation_id` → 401 : aucune discussion
      n'est conservée côté serveur pour les anonymes ;
    - discussion d'un autre utilisateur ou inexistante → 404 (anti-IDOR, en
      lecture comme en écriture).
    """
    if conversation_id is None:
        return []
    if current_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=CONNEXION_REQUISE_DISCUSSION,
        )
    conv = await chat_history_service.get_conversation_with_messages(
        db=db, conversation_id=conversation_id, user_id=current_user_id
    )
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Discussion non trouvée."
        )
    sorted_msgs = sorted(conv.messages or [], key=lambda m: m.created_at)
    return [{"role": m.role, "content": m.content} for m in sorted_msgs[-10:]]


async def _ouvrir_discussion(
    db: AsyncSession,
    current_user_id: uuid.UUID | None,
    conversation_id: uuid.UUID | None,
    question: str,
) -> uuid.UUID | None:
    """Discussion où enregistrer l'échange : None pour un visiteur anonyme."""
    if current_user_id is None:
        return None
    if conversation_id is not None:
        return conversation_id  # propriété déjà vérifiée
    titre = question[:30] + "..." if len(question) > 30 else question
    conv = await chat_history_service.create_conversation(
        db=db, user_id=current_user_id, title=titre
    )
    return conv.id


async def _enregistrer_echange(
    db: AsyncSession,
    conversation_id: uuid.UUID | None,
    question: str,
    image: PreparedImage | None,
    reponse: str,
) -> None:
    """Enregistre la question (photo en référence `media:`) puis la réponse.

    Une erreur n'interrompt pas la réponse déjà servie, mais reste visible
    dans les logs.
    """
    if conversation_id is None:
        return
    try:
        await chat_history_service.add_message_to_conversation(
            db=db,
            conversation_id=conversation_id,
            role="user",
            content=question,
            # Référence courte `media:<nom>` : jamais le Base64 en base.
            image_url=media_service.store(image),
        )
        await chat_history_service.add_message_to_conversation(
            db=db, conversation_id=conversation_id, role="assistant", content=reponse
        )
    except Exception:
        logger.exception(
            "Échec d'enregistrement de l'historique (conversation %s).",
            conversation_id,
        )


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    payload: ExtendedChatRequest,
    request: Request,
    current_user_id: uuid.UUID | None = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """Pose une question technique à l'assistant RAG (avec photo optionnelle).

    Connecté : la discussion est créée ou enrichie côté serveur. Non connecté :
    rien n'est enregistré (`conversation_id` à null), l'historique reste chez
    le client.
    """
    client_ip = get_client_ip(request)

    # 0. Contrôles gratuits avant tout décompte : photo (422), discussion (401/404)
    image = media_service.prepare_chat_image(payload.image_url)
    history_messages = await _historique_de_la_discussion(
        db, current_user_id, payload.conversation_id
    )

    # 1. Vérification et décrémentation des quotas
    allowed = await quota_service.consume_quota(
        db=db, user_id=current_user_id, client_ip=client_ip
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=QuotaEpuiseResponse().model_dump(),
        )

    # 2. Génération RAG / Vision via Mistral avec historique
    rag_result = await rag_service.generate_response(
        question=payload.question,
        metier_id=payload.metier_id,
        image_url=payload.image_url,
        history=history_messages,
    )

    # 3. Enregistrement (utilisateurs connectés uniquement)
    try:
        conversation_id = await _ouvrir_discussion(
            db, current_user_id, payload.conversation_id, payload.question
        )
    except Exception:
        logger.exception("Création de la discussion impossible.")
        conversation_id = None
    await _enregistrer_echange(
        db, conversation_id, payload.question, image, rag_result["reponse"]
    )

    quota_info = await quota_service.get_user_quota_info(
        db=db, user_id=current_user_id, client_ip=client_ip
    )
    return ChatResponse(
        reponse=rag_result["reponse"],
        quota_info=quota_info,
        conversation_id=conversation_id,
        sources=rag_result["sources"],
    )


@router.post("/chat/stream")
async def chat_stream_endpoint(
    payload: ExtendedChatRequest,
    request: Request,
    current_user_id: uuid.UUID | None = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Pose une question technique et retourne la réponse en streaming SSE.

    Mêmes règles que `/api/chat` : discussion vérifiée (401/404) avant tout
    décompte, rien n'est enregistré pour un visiteur anonyme.
    """
    # 0. Contrôles gratuits avant tout décompte : photo (422), discussion (401/404)
    image = media_service.prepare_chat_image(payload.image_url)
    history_messages = await _historique_de_la_discussion(
        db, current_user_id, payload.conversation_id
    )

    # 1. Vérification et décrémentation des quotas
    allowed = await quota_service.consume_quota(
        db=db, user_id=current_user_id, client_ip=get_client_ip(request)
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Quota insuffisant.",
        )

    # 2. Discussion où enregistrer l'échange (None pour un anonyme)
    conversation_id = await _ouvrir_discussion(
        db, current_user_id, payload.conversation_id, payload.question
    )

    # 3. Sources et générateur du RAG
    sources, stream_generator = await rag_service.generate_response_stream(
        question=payload.question,
        metier_id=payload.metier_id,
        image_url=payload.image_url,
        history=history_messages,
    )

    async def event_generator():
        info_data = {
            "conversation_id": str(conversation_id) if conversation_id else None,
            "sources": sources,
        }
        yield f"event: info\ndata: {json.dumps(info_data)}\n\n"

        full_response = ""
        try:
            async for chunk in stream_generator:
                full_response += chunk
                yield f"event: chunk\ndata: {json.dumps(chunk)}\n\n"
        except Exception:
            # Sans ce garde-fou, une erreur du fournisseur IA coupe le flux HTTP
            # sans explication. Le message est envoyé comme un fragment texte
            # (compatible chat_web et Flutter) et rien n'est enregistré.
            logger.exception("Échec de génération en streaming SSE.")
            yield f"event: error\ndata: {json.dumps(ASSISTANT_INDISPONIBLE_MESSAGE)}\n\n"
            yield "event: end\ndata: [DONE]\n\n"
            return

        await _enregistrer_echange(
            db, conversation_id, payload.question, image, full_response
        )
        yield "event: end\ndata: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# Formats audio transmis à Voxtral (extension du fichier), déduits de `format`
# ("wav") ou d'un type MIME `audio_format` ("audio/webm;codecs=opus").
_AUDIO_EXTENSIONS = {"wav", "mp3", "webm", "ogg", "m4a", "aac", "flac"}
_AUDIO_ALIASES = {
    "mpeg": "mp3",
    "x-wav": "wav",
    "wave": "wav",
    "mp4": "m4a",
    "x-m4a": "m4a",
}
_MAX_AUDIO_B64_CHARS = MAX_AUDIO_BYTES * 4 // 3 + 4
_SERVICE_INDISPONIBLE = "Service momentanément indisponible. Réessayez dans un instant."


def _audio_extension(raw: str | None) -> str:
    value = (raw or "wav").lower().split(";")[0].strip().split("/")[-1]
    ext = _AUDIO_ALIASES.get(value, value)
    return ext if ext in _AUDIO_EXTENSIONS else "wav"


class _WsTurn(BaseModel):
    """Une question reçue sur le WebSocket (texte ou note vocale), après analyse."""

    question: str = ""
    audio_b64: str | None = None
    audio_ext: str = "wav"
    metier_id: int | None = None
    conversation_id: uuid.UUID | None = None
    voice_output: bool = False


def _parse_ws_turn(parsed: dict[str, Any]) -> _WsTurn:
    """Normalise un message JSON métier (texte, `type: voice` ou `action: audio_chunk`)."""
    raw_conv = parsed.get("conversation_id")
    try:
        conversation_id = uuid.UUID(str(raw_conv)) if raw_conv else None
    except ValueError:
        conversation_id = None
    metier_id = parsed.get("metier_id")
    metier_id = metier_id if isinstance(metier_id, int) else None

    is_voice = parsed.get("type") in ("voice", "audio") or parsed.get("action") in (
        "audio_chunk",
        "voice",
    )
    if is_voice:
        return _WsTurn(
            audio_b64=parsed.get("audio") or parsed.get("data") or "",
            audio_ext=_audio_extension(
                parsed.get("format") or parsed.get("audio_format")
            ),
            metier_id=metier_id,
            conversation_id=conversation_id,
            voice_output=True,
        )
    question = parsed.get("content") or parsed.get("text") or parsed.get("question")
    return _WsTurn(
        question=str(question or ""),
        metier_id=metier_id,
        conversation_id=conversation_id,
        voice_output=bool(parsed.get("voice_output", False)),
    )


async def _ws_send(websocket: WebSocket, **fields: Any) -> None:
    await websocket.send_text(WebSocketMessage(**fields).model_dump_json())


@router.websocket("/chat/ws")
async def chat_websocket_endpoint(
    websocket: WebSocket,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Connexion WebSocket bidirectionnelle temps réel pour mode texte et vocal mains-libres.

    Messages acceptés :
    - `{"action": "auth", "token": "...", "conversation_id": "..."}` (optionnel,
      en premier) : authentifie la session et rattache les échanges suivants à
      une discussion existante de l'utilisateur (historique chargé et enrichi).
    - Texte brut, ou JSON `{"type": "text", "content": "...", "metier_id": 1}`.
    - Note vocale `{"type": "voice", "audio": "<base64>", "format": "wav"}` ou
      `{"action": "audio_chunk", "audio": "<base64>", "audio_format": "audio/webm"}`.
    - `{"type": "ping"}` → `pong`.

    Réponses : `user_transcription`, puis des `stream` (fragments réels du
    LLM), `stream_end` (réponse complète + sources), et pour la voix
    `audio_response` + `voice_turn_completed`. Taille, débit et quota sont
    vérifiés **avant** toute transcription (appel Voxtral facturé).
    """
    # Utilisateur authentifié via `{"action": "auth"}` ; None = anonyme, dont le
    # quota est compté par IP cliente.
    user_id: uuid.UUID | None = None
    session_conversation_id: uuid.UUID | None = None
    client_ip = get_client_ip(websocket)
    await websocket.accept()
    try:
        while True:
            raw_data = await websocket.receive_text()

            try:
                parsed: Any = json.loads(raw_data)
            except (json.JSONDecodeError, TypeError):
                parsed = raw_data
            if not isinstance(parsed, dict):
                parsed = {"content": str(parsed)}

            if parsed.get("action") == "auth":
                token = parsed.get("token")
                if token:
                    try:
                        user_id = get_user_id_from_token(str(token))
                    except (HTTPException, ValueError):
                        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                        return
                else:
                    user_id = None
                session_conversation_id = _parse_ws_turn(parsed).conversation_id
                continue

            if parsed.get("type") == "ping":
                await _ws_send(websocket, type="pong")
                continue

            turn = _parse_ws_turn(parsed)
            conversation_id = turn.conversation_id or session_conversation_id

            # 1. Contrôles gratuits d'abord : contenu, taille, propriété.
            if turn.audio_b64 is not None:
                if not turn.audio_b64:
                    await _ws_send(
                        websocket, type="error", message="Données audio manquantes."
                    )
                    continue
                if len(turn.audio_b64) > _MAX_AUDIO_B64_CHARS:
                    await _ws_send(
                        websocket,
                        type="error",
                        message="Note vocale trop volumineuse (10 Mo maximum).",
                    )
                    continue
            elif not turn.question.strip():
                continue
            elif len(turn.question) > MAX_QUESTION_CHARS:
                await _ws_send(
                    websocket,
                    type="error",
                    message=f"Question trop longue ({MAX_QUESTION_CHARS} caractères maximum).",
                )
                continue

            # Discussion : réservée aux utilisateurs connectés, et à son
            # propriétaire (mêmes règles que les routes HTTP).
            try:
                history = await _historique_de_la_discussion(
                    db, user_id, conversation_id
                )
            except HTTPException as exc:
                await _ws_send(websocket, type="error", message=str(exc.detail))
                continue

            # 2. Débit puis quota (le middleware HTTP ne voit pas les WebSockets).
            if await is_rate_limited(client_ip):
                await _ws_send(websocket, type="error", message=RATE_LIMIT_MESSAGE)
                continue
            try:
                allowed = await quota_service.consume_quota(
                    db=db, user_id=user_id, client_ip=client_ip
                )
            except QuotaIndisponibleError:
                await _ws_send(websocket, type="error", message=_SERVICE_INDISPONIBLE)
                continue
            if not allowed:
                await _ws_send(
                    websocket,
                    type="payment_required",
                    message=QuotaEpuiseResponse().message,
                )
                continue

            # 3. Transcription (seulement une fois les droits vérifiés).
            question_text = turn.question.strip()
            if turn.audio_b64 is not None:
                try:
                    transcription = await audio_service.transcribe_audio(
                        file_bytes=base64.b64decode(turn.audio_b64),
                        filename=f"voice.{turn.audio_ext}",
                    )
                except Exception as exc:
                    await _ws_send(
                        websocket,
                        type="error",
                        message=f"Échec de transcription vocale: {exc!s}",
                    )
                    continue
                question_text = transcription.strip()
                if not question_text:
                    await _ws_send(
                        websocket,
                        type="error",
                        message="Aucune parole détectée dans la note vocale.",
                    )
                    continue
                await _ws_send(websocket, type="user_transcription", text=question_text)

            # 4. Réponse réellement streamée depuis le LLM.
            parts: list[str] = []
            try:
                sources, stream_generator = await rag_service.generate_response_stream(
                    question=question_text,
                    metier_id=turn.metier_id,
                    history=history,
                )
                async for chunk in stream_generator:
                    parts.append(chunk)
                    await _ws_send(websocket, type="stream", chunk=chunk)
            except WebSocketDisconnect:
                raise
            except Exception:
                # Une erreur du fournisseur IA ne doit pas fermer la session.
                logger.exception("Échec de génération en streaming WebSocket.")
                await _ws_send(
                    websocket, type="error", message=ASSISTANT_INDISPONIBLE_MESSAGE
                )
                continue
            answer_text = "".join(parts).strip()
            await _ws_send(
                websocket, type="stream_end", message=answer_text, sources=sources
            )

            if conversation_id is not None:
                try:
                    await chat_history_service.add_message_to_conversation(
                        db=db,
                        conversation_id=conversation_id,
                        role="user",
                        content=question_text,
                    )
                    await chat_history_service.add_message_to_conversation(
                        db=db,
                        conversation_id=conversation_id,
                        role="assistant",
                        content=answer_text,
                    )
                except Exception:
                    logger.exception(
                        "Échec d'enregistrement de l'historique (conversation %s).",
                        conversation_id,
                    )

            # 5. Lecture vocale pour le mode mains-libres.
            if turn.voice_output and answer_text:
                try:
                    tts_bytes = await audio_service.synthesize_speech(
                        text=answer_text[:500]
                    )
                    await _ws_send(
                        websocket,
                        type="audio_response",
                        audio=base64.b64encode(tts_bytes).decode("ascii"),
                        audio_format="audio/mp3",
                        is_final=True,
                    )
                except Exception:
                    logger.exception("Échec de la synthèse vocale WebSocket.")
                await _ws_send(websocket, type="voice_turn_completed")
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

    # Anti-IDOR : on ne note qu'une discussion qui appartient à l'appelant ;
    # un visiteur anonyme n'a aucune discussion enregistrée côté serveur.
    if payload.conversation_id is not None:
        conv = (
            await chat_history_service.get_conversation_with_messages(
                db=db, conversation_id=payload.conversation_id, user_id=user_id
            )
            if user_id is not None
            else None
        )
        if conv is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Discussion non trouvée.",
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
