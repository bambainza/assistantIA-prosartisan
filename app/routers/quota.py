"""
Router Quota : Solde de questions et statut d'abonnement.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.quota_service import quota_service

router = APIRouter(prefix="/api/quota", tags=["Quotas & Abonnements"])


@router.get("/{user_id}")
async def get_user_quota(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Consulte le solde de questions et le statut Premium de l'artisan."""
    return await quota_service.get_user_quota_info(db=db, user_id=user_id)
