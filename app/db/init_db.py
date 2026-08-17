"""Initialisation de la base de données (création des tables + seed)."""

from sqlalchemy import text

from app.db.session import engine
from app.models.base import Base


async def init_db() -> None:
    """Crée toutes les tables définies par les modèles SQLAlchemy."""
    async with engine.begin() as conn:
        # Active l'extension UUID si nécessaire
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "pgcrypto"'))
        await conn.run_sync(Base.metadata.create_all)


async def drop_db() -> None:
    """Supprime toutes les tables (usage test uniquement)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
