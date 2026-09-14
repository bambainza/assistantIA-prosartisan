"""Service : module Paramètres — CRUD des données de référence qui alimentent
les listes de choix du back-office et de l'ingestion RAG (métiers, sous-métiers,
catégories d'actualités).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.actualite import ActualiteCategorie
from app.models.metier import Metier, SousMetier


class ParametresService:
    """Lecture et écriture des tables de référence pilotées depuis le back-office."""

    # ── Métiers ──────────────────────────────────────────────────────────
    async def list_metiers(self, db: AsyncSession) -> list[Metier]:
        stmt = (
            select(Metier)
            .options(selectinload(Metier.sous_metiers))
            .order_by(Metier.nom)
        )
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def get_metier(self, db: AsyncSession, metier_id: int) -> Metier | None:
        stmt = (
            select(Metier)
            .options(selectinload(Metier.sous_metiers))
            .where(Metier.id == metier_id)
        )
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    async def create_metier(
        self, db: AsyncSession, *, nom: str, slug: str, description: str | None
    ) -> Metier:
        metier = Metier(nom=nom, slug=slug, description=description)
        db.add(metier)
        return metier

    async def update_metier(
        self,
        db: AsyncSession,
        metier_id: int,
        *,
        nom: str | None,
        slug: str | None,
        description: str | None,
    ) -> Metier | None:
        metier = await self.get_metier(db, metier_id)
        if metier is None:
            return None
        if nom is not None:
            metier.nom = nom
        if slug is not None:
            metier.slug = slug
        if description is not None:
            metier.description = description
        return metier

    async def toggle_metier(self, db: AsyncSession, metier_id: int) -> Metier | None:
        metier = await self.get_metier(db, metier_id)
        if metier is None:
            return None
        metier.is_active = not metier.is_active
        return metier

    async def delete_metier(self, db: AsyncSession, metier_id: int) -> bool:
        metier = await self.get_metier(db, metier_id)
        if metier is None:
            return False
        await db.delete(metier)
        return True

    # ── Sous-métiers ─────────────────────────────────────────────────────
    async def get_sous_metier(
        self, db: AsyncSession, sous_metier_id: int
    ) -> SousMetier | None:
        stmt = select(SousMetier).where(SousMetier.id == sous_metier_id)
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    async def create_sous_metier(
        self, db: AsyncSession, *, metier_id: int, nom: str, slug: str
    ) -> SousMetier:
        sous_metier = SousMetier(metier_id=metier_id, nom=nom, slug=slug)
        db.add(sous_metier)
        return sous_metier

    async def update_sous_metier(
        self,
        db: AsyncSession,
        sous_metier_id: int,
        *,
        nom: str | None,
        slug: str | None,
    ) -> SousMetier | None:
        sous_metier = await self.get_sous_metier(db, sous_metier_id)
        if sous_metier is None:
            return None
        if nom is not None:
            sous_metier.nom = nom
        if slug is not None:
            sous_metier.slug = slug
        return sous_metier

    async def delete_sous_metier(self, db: AsyncSession, sous_metier_id: int) -> bool:
        sous_metier = await self.get_sous_metier(db, sous_metier_id)
        if sous_metier is None:
            return False
        await db.delete(sous_metier)
        return True

    # ── Catégories d'actualités ──────────────────────────────────────────
    async def list_categories(self, db: AsyncSession) -> list[ActualiteCategorie]:
        stmt = select(ActualiteCategorie).order_by(ActualiteCategorie.label)
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def get_categorie(
        self, db: AsyncSession, categorie_id: int
    ) -> ActualiteCategorie | None:
        stmt = select(ActualiteCategorie).where(ActualiteCategorie.id == categorie_id)
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    async def create_categorie(
        self, db: AsyncSession, *, code: str, label: str
    ) -> ActualiteCategorie:
        categorie = ActualiteCategorie(code=code, label=label)
        db.add(categorie)
        return categorie

    async def update_categorie(
        self, db: AsyncSession, categorie_id: int, *, label: str
    ) -> ActualiteCategorie | None:
        categorie = await self.get_categorie(db, categorie_id)
        if categorie is None:
            return None
        categorie.label = label
        return categorie

    async def toggle_categorie(
        self, db: AsyncSession, categorie_id: int
    ) -> ActualiteCategorie | None:
        categorie = await self.get_categorie(db, categorie_id)
        if categorie is None:
            return None
        categorie.is_active = not categorie.is_active
        return categorie

    async def delete_categorie(self, db: AsyncSession, categorie_id: int) -> bool:
        categorie = await self.get_categorie(db, categorie_id)
        if categorie is None:
            return False
        await db.delete(categorie)
        return True


parametres_service = ParametresService()
