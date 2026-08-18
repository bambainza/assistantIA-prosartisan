"""Route de vérification de santé de l'application."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)) -> dict:
    """Vérifie que le serveur et la base de données sont opérationnels."""
    db_status = "ok"
    db_version = "inaccessible"

    try:
        result = await db.execute(text("SELECT version()"))
        version_row = result.scalar()
        if version_row:
            db_version = version_row
    except Exception as e:
        db_status = f"error: {e}"

    return {
        "status": "ok",
        "service": "ProsArtisan IA Expert",
        "version": "0.1.0",
        "database": {
            "status": db_status,
            "sgbd": "PostgreSQL",
            "version_detail": db_version,
        },
    }
