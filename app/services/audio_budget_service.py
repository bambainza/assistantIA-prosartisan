"""Budgets audio journaliers partagés, indépendants des questions du chat."""

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Literal

from fastapi import HTTPException

from app.config import settings
from app.services.cache_service import cache_service
from app.services.quota_service import identite_quota

logger = logging.getLogger(__name__)


@asynccontextmanager
async def audio_budget(
    kind: Literal["stt", "tts"],
    user_id: uuid.UUID | None,
    client_ip: str,
    amount: int = 1,
) -> AsyncIterator[None]:
    """Réserve avant facturation et restitue la même clé datée en cas d'échec."""
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    identity = identite_quota(user_id, client_ip)
    key = f"prosartisan:quota:audio:{kind}:{day}:{identity}"
    limit = (
        settings.audio_stt_requests_per_day
        if kind == "stt"
        else settings.audio_tts_chars_per_day
    )
    if not await cache_service.reserve_budget(key, amount, limit, 2 * 86400):
        raise HTTPException(status_code=429, detail="Budget audio journalier épuisé.")
    try:
        yield
    except BaseException:
        try:
            await cache_service.increment(key, 2 * 86400, amount=-amount)
        except Exception:
            logger.exception("Restitution du budget audio impossible.")
        raise
