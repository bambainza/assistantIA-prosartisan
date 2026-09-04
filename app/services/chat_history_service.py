"""Service de gestion de l'historique des discussions (Conversations et Messages)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

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
        from datetime import UTC, datetime

        title_val = title or "Nouvelle discussion"
        conversation = Conversation(
            id=uuid.uuid4(),
            user_id=user_id,
            title=title_val,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
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
        user_id: uuid.UUID | None = None,
    ) -> Conversation | None:
        """Récupère une discussion avec ses messages.

        Si ``user_id`` est fourni, la discussion n'est renvoyée que si elle
        appartient à cet artisan (protection contre l'accès à l'historique
        d'un autre utilisateur).
        """
        try:
            stmt = select(Conversation).where(Conversation.id == conversation_id)
            if user_id is not None:
                stmt = stmt.where(Conversation.user_id == user_id)
            res = await db.execute(stmt)
            conv = res.scalar_one_or_none()
            if conv is not None:
                return conv
        except Exception:
            pass
        conv = self._fallback_db.get(conversation_id)
        if conv is not None and user_id is not None and conv.user_id != user_id:
            return None
        return conv

    async def list_conversations_for_user(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        q: str | None = None,
    ) -> Sequence[Conversation]:
        """Récupère toutes les discussions d'un artisan (triées par mise à jour récente), filtrées si q est fourni."""
        try:
            if q:
                from sqlalchemy import or_

                from app.models.message import Message

                stmt = (
                    select(Conversation)
                    .outerjoin(Message)
                    .where(Conversation.user_id == user_id)
                    .where(
                        or_(
                            Conversation.title.ilike(f"%{q}%"),
                            Message.content.ilike(f"%{q}%"),
                        )
                    )
                    .distinct()
                    .order_by(Conversation.updated_at.desc())
                )
            else:
                stmt = (
                    select(Conversation)
                    .where(Conversation.user_id == user_id)
                    .order_by(Conversation.updated_at.desc())
                )
            res = await db.execute(stmt)
            return res.scalars().all()
        except Exception:
            # Fallback list from in-memory DB
            results = [c for c in self._fallback_db.values() if c.user_id == user_id]
            if q:
                q_lower = q.lower()
                filtered = []
                for c in results:
                    if q_lower in c.title.lower():
                        filtered.append(c)
                        continue
                    has_msg = False
                    if hasattr(c, "messages") and c.messages:
                        for m in c.messages:
                            if q_lower in m.content.lower():
                                has_msg = True
                                break
                    if has_msg:
                        filtered.append(c)
                results = filtered

            return sorted(
                results,
                key=lambda x: x.updated_at,
                reverse=True,
            )

    async def delete_conversation(
        self,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> bool:
        """Supprime une discussion et ses messages (si elle appartient à l'artisan)."""
        try:
            stmt = select(Conversation).where(Conversation.id == conversation_id)
            if user_id is not None:
                stmt = stmt.where(Conversation.user_id == user_id)
            res = await db.execute(stmt)
            conversation = res.scalar_one_or_none()
            if conversation:
                await db.delete(conversation)
                await db.commit()
                return True
        except Exception:
            pass

        fallback = self._fallback_db.get(conversation_id)
        if fallback is not None and (user_id is None or fallback.user_id == user_id):
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
        from datetime import UTC, datetime

        message = Message(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            role=role,
            content=content,
            image_url=image_url,
            created_at=datetime.now(UTC),
        )
        try:
            db.add(message)
            # Mettre à jour le timestamp 'updated_at' de la conversation
            select_stmt = select(Conversation).where(Conversation.id == conversation_id)
            res = await db.execute(select_stmt)
            conversation = res.scalar_one_or_none()
            if conversation:
                conversation.updated_at = datetime.now(UTC)
            await db.commit()
            try:
                await db.refresh(message)
            except Exception:
                pass
        except Exception:
            # Fallback local in-memory
            if conversation_id in self._fallback_db:
                conv = self._fallback_db[conversation_id]
                if not hasattr(conv, "messages") or conv.messages is None:
                    conv.messages = []
                conv.messages.append(message)
                conv.updated_at = datetime.now(UTC)
        return message

    async def rename_conversation(
        self,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        new_title: str,
        user_id: uuid.UUID | None = None,
    ) -> Conversation | None:
        """Modifie le titre d'une discussion (si elle appartient à l'artisan)."""
        try:
            stmt = select(Conversation).where(Conversation.id == conversation_id)
            if user_id is not None:
                stmt = stmt.where(Conversation.user_id == user_id)
            res = await db.execute(stmt)
            conversation = res.scalar_one_or_none()
            if conversation:
                conversation.title = new_title
                from datetime import UTC, datetime

                conversation.updated_at = datetime.now(UTC)
                await db.commit()
                try:
                    await db.refresh(conversation)
                except Exception:
                    pass
                return conversation
        except Exception:
            pass

        conv = self._fallback_db.get(conversation_id)
        if conv is not None and (user_id is None or conv.user_id == user_id):
            conv.title = new_title
            from datetime import UTC, datetime

            conv.updated_at = datetime.now(UTC)
            return conv
        return None


chat_history_service = ChatHistoryService()
