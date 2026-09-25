"""Liste publique des métiers, pour le sélecteur des clients (web, mobile).

Les identifiants viennent de la base (auto-incrément) et diffèrent d'une
installation à l'autre : les clients ne doivent jamais les coder en dur.
"""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.parametres import MetierPublic
from app.services.parametres_service import parametres_service

router = APIRouter(prefix="/api", tags=["Métiers"])


@router.get("/metiers", response_model=list[MetierPublic])
async def list_metiers_publics(db: AsyncSession = Depends(get_db)) -> Any:
    """Métiers actifs (id, nom, slug) ; sans filtre, le RAG couvre tous les métiers."""
    return await parametres_service.list_metiers_actifs(db)
