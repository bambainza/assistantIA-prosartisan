"""
Router Quota : Solde de questions et statut d'abonnement.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.middleware.auth import get_optional_user_id
from app.middleware.client_ip import get_client_ip
from app.services.quota_service import quota_service

router = APIRouter(prefix="/api/quota", tags=["Quotas & Abonnements"])


@router.get("")
async def get_user_quota(
    request: Request,
    current_user_id: uuid.UUID | None = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Consulte le solde de questions et le statut Premium de l'artisan courant.

    L'identité est déduite du JWT (ou de l'IP cliente pour un visiteur non
    connecté) : il n'existe plus de route ``/{user_id}`` qui exposerait le
    quota d'un tiers à partir de son seul identifiant.
    """
    return await quota_service.get_user_quota_info(
        db=db, user_id=current_user_id, client_ip=get_client_ip(request)
    )
