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
from app.models.payment_method import PaymentMethodConfig
from app.services.payment_providers import OPERATEURS

_LIBELLES_OPERATEURS_PAR_DEFAUT: dict[str, str] = {
    "WAVE": "Wave",
    "ORANGE": "Orange Money",
    "CINETPAY": "CinetPay",
}


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

    async def list_metiers_actifs(self, db: AsyncSession) -> list[Metier]:
        """Métiers proposés aux artisans (filtre du RAG), par identifiant."""
        stmt = select(Metier).where(Metier.is_active.is_(True)).order_by(Metier.id)
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

    # ── Moyens de paiement (Wave, Orange Money, CinetPay) ────────────────
    async def list_payment_methods(self, db: AsyncSession) -> list[PaymentMethodConfig]:
        stmt = select(PaymentMethodConfig).order_by(PaymentMethodConfig.id)
        res = await db.execute(stmt)
        rows = [
            row for row in res.scalars().all() if isinstance(row, PaymentMethodConfig)
        ]
        if rows:
            existing_codes = {r.code for r in rows}
            for idx, code in enumerate(OPERATEURS, start=len(rows) + 1):
                if code not in existing_codes:
                    rows.append(
                        PaymentMethodConfig(
                            id=idx,
                            code=code,
                            label=_LIBELLES_OPERATEURS_PAR_DEFAUT.get(code, code),
                            is_active=True,
                        )
                    )
            return rows
        return [
            PaymentMethodConfig(
                id=idx,
                code=code,
                label=_LIBELLES_OPERATEURS_PAR_DEFAUT.get(code, code),
                is_active=True,
            )
            for idx, code in enumerate(OPERATEURS, start=1)
        ]

    async def list_active_payment_operators(self, db: AsyncSession) -> list[str]:
        """Retourne les codes des opérateurs de paiement actuellement activés."""
        methods = await self.list_payment_methods(db)
        return [m.code for m in methods if m.is_active]

    async def is_payment_operator_active(self, db: AsyncSession, code: str) -> bool:
        """Indique si l'opérateur est activé (par défaut True si absent de la base)."""
        normalized = code.upper()
        if normalized not in OPERATEURS:
            return False
        stmt = select(PaymentMethodConfig).where(PaymentMethodConfig.code == normalized)
        res = await db.execute(stmt)
        obj = res.scalar_one_or_none()
        if isinstance(obj, PaymentMethodConfig):
            return bool(obj.is_active)
        return True

    async def toggle_payment_method(
        self, db: AsyncSession, code: str
    ) -> PaymentMethodConfig | None:
        """Active ou désactive un moyen de paiement par son code (WAVE, ORANGE, CINETPAY)."""
        normalized = code.upper()
        if normalized not in OPERATEURS:
            return None
        stmt = select(PaymentMethodConfig).where(PaymentMethodConfig.code == normalized)
        res = await db.execute(stmt)
        obj = res.scalar_one_or_none()
        if isinstance(obj, PaymentMethodConfig):
            obj.is_active = not obj.is_active
            return obj
        new_obj = PaymentMethodConfig(
            code=normalized,
            label=_LIBELLES_OPERATEURS_PAR_DEFAUT.get(normalized, normalized),
            is_active=False,
        )
        db.add(new_obj)
        return new_obj


parametres_service = ParametresService()
