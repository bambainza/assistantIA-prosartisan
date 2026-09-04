"""Tests du ChatHistoryService : isolation des discussions par propriétaire."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.conversation import Conversation
from app.services.chat_history_service import ChatHistoryService


def _db_indisponible() -> MagicMock:
    """Session dont toute requête échoue → force le repli en mémoire."""
    session = MagicMock()
    session.execute = AsyncMock(side_effect=RuntimeError("db down"))
    session.commit = AsyncMock()
    session.delete = AsyncMock()
    return session


@pytest.fixture
def service_avec_conversation():
    service = ChatHistoryService()
    owner = uuid.uuid4()
    conv = Conversation(
        id=uuid.uuid4(),
        user_id=owner,
        title="Chantier de Kouassi",
        messages=[],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    service._fallback_db[conv.id] = conv
    return service, owner, conv


@pytest.mark.asyncio
async def test_lecture_refusee_a_un_autre_utilisateur(service_avec_conversation):
    service, owner, conv = service_avec_conversation
    autre = uuid.uuid4()

    assert (
        await service.get_conversation_with_messages(
            _db_indisponible(), conv.id, user_id=autre
        )
        is None
    )
    assert (
        await service.get_conversation_with_messages(
            _db_indisponible(), conv.id, user_id=owner
        )
        is conv
    )


@pytest.mark.asyncio
async def test_suppression_refusee_a_un_autre_utilisateur(service_avec_conversation):
    service, _owner, conv = service_avec_conversation

    assert (
        await service.delete_conversation(
            _db_indisponible(), conv.id, user_id=uuid.uuid4()
        )
        is False
    )
    assert conv.id in service._fallback_db  # toujours présente


@pytest.mark.asyncio
async def test_renommage_refuse_a_un_autre_utilisateur(service_avec_conversation):
    service, _owner, conv = service_avec_conversation

    assert (
        await service.rename_conversation(
            _db_indisponible(), conv.id, "Piraté", user_id=uuid.uuid4()
        )
        is None
    )
    assert conv.title == "Chantier de Kouassi"
