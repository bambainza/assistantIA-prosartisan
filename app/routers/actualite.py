"""Router Actualités : consultation publique des annonces/conseils publiés."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.middleware.auth import get_optional_user_id
from app.models.user import User
from app.schemas.actualite import ActualiteOut
from app.services.actualite_service import actualite_service

router = APIRouter(prefix="/api/actualites", tags=["Actualités"])


@router.get("", response_model=list[ActualiteOut])
async def list_public_actualites(
    metier_id: int | None = None,
    user_id: uuid.UUID | None = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[Any]:
    """Actualités publiées, filtrées par métier (paramètre explicite, sinon déduit
    du profil de l'utilisateur connecté s'il y en a un)."""
    effective_metier_id = metier_id
    if effective_metier_id is None and user_id is not None:
        stmt = select(User.metier_id).where(User.id == user_id)
        res = await db.execute(stmt)
        effective_metier_id = res.scalar_one_or_none()

    return await actualite_service.list_published(db, metier_id=effective_metier_id)
