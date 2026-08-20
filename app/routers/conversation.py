"""
Router Conversations : API de gestion de l'historique des discussions.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.conversation import (
    ConversationCreate,
    ConversationDetailResponse,
    ConversationResponse,
)
from app.services.chat_history_service import chat_history_service

router = APIRouter(prefix="/api/conversations", tags=["Historique Discussions"])


@router.post(
    "",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation_endpoint(
    payload: ConversationCreate,
    user_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Crée une nouvelle discussion vide pour un artisan."""
    uid = user_id or uuid.UUID("00000000-0000-0000-0000-000000000001")
    return await chat_history_service.create_conversation(
        db=db,
        user_id=uid,
        title=payload.title,
    )


@router.get("", response_model=list[ConversationResponse])
async def list_conversations_endpoint(
    user_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Liste toutes les discussions d'un artisan (triées par la plus récente)."""
    uid = user_id or uuid.UUID("00000000-0000-0000-0000-000000000001")
    return await chat_history_service.list_conversations_for_user(db=db, user_id=uid)


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation_endpoint(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Récupère une discussion spécifique avec sa liste de messages."""
    conversation = await chat_history_service.get_conversation_with_messages(
        db=db,
        conversation_id=conversation_id,
    )
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Discussion non trouvée.",
        )
    return conversation


@router.delete("/{conversation_id}")
async def delete_conversation_endpoint(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Supprime une discussion et son historique de messages associés."""
    deleted = await chat_history_service.delete_conversation(
        db=db,
        conversation_id=conversation_id,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Discussion non trouvée.",
        )
    return {
        "status": "success",
        "message": f"La discussion {conversation_id} a été supprimée.",
    }
