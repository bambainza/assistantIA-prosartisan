"""Sondes de vie et de disponibilité, sans détails internes publics."""

import asyncio
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db
from app.services.cache_service import cache_service
from app.services.rag_service import rag_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Health"])


@router.get("/health")
@router.get("/api/health")
async def health_check() -> dict[str, str]:
    """Sonde de vie indépendante des dépendances externes."""
    return {
        "status": "ok",
        "service": "ProsArtisan IA Expert",
        "version": "0.1.0",
        "revision": settings.build_sha,
    }


async def _check_dependencies(db: AsyncSession) -> None:
    await db.execute(text("SELECT 1"))
    redis = await cache_service._get_redis()
    if redis is None or not await redis.ping():
        raise RuntimeError("Redis indisponible")
    await rag_service.qdrant_client.get_collection(
        collection_name=settings.qdrant_collection
    )


@router.get("/api/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Autorise le trafic seulement si PostgreSQL, Redis et le corpus répondent."""
    try:
        await asyncio.wait_for(_check_dependencies(db), timeout=4)
    except Exception:
        logger.exception("Sonde de disponibilité en échec.")
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return JSONResponse({"status": "ok", "revision": settings.build_sha})
