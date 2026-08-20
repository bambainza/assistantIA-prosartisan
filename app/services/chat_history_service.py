"""Service de gestion de l'historique des discussions (Conversations et Messages)."""

from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.message import Message


class ChatHistoryService:
    """Service pour gérer l'historique des chats de l'artisan."""

    def __init__(self):
        # Local in-memory fallback database when PostgreSQL is offline
        # Schema: {conversation_id: Conversation}
        self._fallback_db: dict[uuid.UUID, Conversation] = {}

    async def create_conversation(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        title: str | None = None,
    ) -> Conversation:
        """Crée une nouvelle discussion pour un artisan."""
        from datetime import datetime
        title_val = title or "Nouvelle discussion"
        conversation = Conversation(
            id=uuid.uuid4(),
            user_id=user_id,
            title=title_val,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            messages=[],
        )
        try:
            db.add(conversation)
            await db.commit()
            try:
                await db.refresh(conversation)
            except Exception:
                pass
        except Exception:
            # Fallback local in-memory
            self._fallback_db[conversation.id] = conversation
        return conversation

    async def get_conversation_with_messages(
        self,
        db: AsyncSession,
        conversation_id: uuid.UUID,
    ) -> Conversation | None:
        """Récupère une discussion spécifique avec tous ses messages."""
        try:
            stmt = select(Conversation).where(Conversation.id == conversation_id)
            res = await db.execute(stmt)
            conv = res.scalar_one_or_none()
            if conv is not None:
                return conv
        except Exception:
            pass
        return self._fallback_db.get(conversation_id)

    async def list_conversations_for_user(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> Sequence[Conversation]:
        """Récupère toutes les discussions d'un artisan (triées par mise à jour récente)."""
        try:
            stmt = (
                select(Conversation)
                .where(Conversation.user_id == user_id)
                .order_by(Conversation.updated_at.desc())
            )
            res = await db.execute(stmt)
            return res.scalars().all()
        except Exception:
            # Fallback list from in-memory DB
            return sorted(
                [c for c in self._fallback_db.values() if c.user_id == user_id],
                key=lambda x: x.updated_at,
                reverse=True,
            )

    async def delete_conversation(
        self,
        db: AsyncSession,
        conversation_id: uuid.UUID,
    ) -> bool:
        """Supprime une discussion et ses messages."""
        try:
            stmt = select(Conversation).where(Conversation.id == conversation_id)
            res = await db.execute(stmt)
            conversation = res.scalar_one_or_none()
            if conversation:
                db.delete(conversation)
                await db.commit()
                return True
        except Exception:
            pass

        if conversation_id in self._fallback_db:
            del self._fallback_db[conversation_id]
            return True
        return False

    async def add_message_to_conversation(
        self,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        image_url: str | None = None,
    ) -> Message:
        """Ajoute un message (utilisateur ou assistant) à une discussion existante."""
        from datetime import datetime
        message = Message(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            role=role,
            content=content,
            image_url=image_url,
            created_at=datetime.now(),
        )
        try:
            db.add(message)
            # Mettre à jour le timestamp 'updated_at' de la conversation
            select_stmt = select(Conversation).where(Conversation.id == conversation_id)
            res = await db.execute(select_stmt)
            conversation = res.scalar_one_or_none()
            if conversation:
                conversation.updated_at = datetime.now()
            await db.commit()
            try:
                await db.refresh(message)
            except Exception:
                pass
        except Exception:
            # Fallback local in-memory
            if conversation_id in self._fallback_db:
                conv = self._fallback_db[conversation_id]
                if not hasattr(conv, 'messages') or conv.messages is None:
                    conv.messages = []
                conv.messages.append(message)
                conv.updated_at = datetime.now()
        return message


chat_history_service = ChatHistoryService()
