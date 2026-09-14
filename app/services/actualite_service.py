"""Service : Actualités (annonces/conseils métier) et suggestions issues du feedback."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.actualite import Actualite
from app.models.feedback import Feedback
from app.models.user import User


class ActualiteService:
    """CRUD des actualités et diffusion aux artisans concernés."""

    async def list_all(
        self, db: AsyncSession, *, statut: str | None = None
    ) -> list[Actualite]:
        """Liste complète (back-office), filtrable par statut."""
        stmt = select(Actualite).order_by(Actualite.created_at.desc())
        if statut is not None:
            stmt = stmt.where(Actualite.statut == statut)
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def list_published(
        self, db: AsyncSession, *, metier_id: int | None = None
    ) -> list[Actualite]:
        """Actualités publiées visibles par un artisan (globales + celles de son métier)."""
        stmt = select(Actualite).where(Actualite.statut == "publie")
        if metier_id is not None:
            stmt = stmt.where(
                (Actualite.metier_id.is_(None)) | (Actualite.metier_id == metier_id)
            )
        stmt = stmt.order_by(Actualite.publie_at.desc())
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def get(self, db: AsyncSession, actualite_id: uuid.UUID) -> Actualite | None:
        stmt = select(Actualite).where(Actualite.id == actualite_id)
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    async def create(
        self,
        db: AsyncSession,
        *,
        titre: str,
        contenu: str,
        metier_id: int | None,
        created_by: uuid.UUID,
    ) -> Actualite:
        now = datetime.now(UTC).replace(tzinfo=None)
        actualite = Actualite(
            id=uuid.uuid4(),
            titre=titre,
            contenu=contenu,
            metier_id=metier_id,
            statut="brouillon",
            created_at=now,
            updated_at=now,
            created_by=created_by,
        )
        db.add(actualite)
        return actualite

    async def update(
        self,
        db: AsyncSession,
        actualite_id: uuid.UUID,
        *,
        titre: str | None,
        contenu: str | None,
        metier_id: int | None,
    ) -> Actualite | None:
        actualite = await self.get(db, actualite_id)
        if actualite is None:
            return None
        if titre is not None:
            actualite.titre = titre
        if contenu is not None:
            actualite.contenu = contenu
        if metier_id is not None:
            actualite.metier_id = metier_id
        return actualite

    async def delete(self, db: AsyncSession, actualite_id: uuid.UUID) -> bool:
        actualite = await self.get(db, actualite_id)
        if actualite is None:
            return False
        await db.delete(actualite)
        return True

    async def publish(
        self, db: AsyncSession, actualite_id: uuid.UUID
    ) -> Actualite | None:
        """Publie une actualité (la rend visible via `list_published`).

        La notification des artisans concernés, potentiellement nombreux, est
        déclenchée séparément en tâche de fond par l'appelant (voir
        `app.routers.admin.publish_actualite`) — jamais ici, pour ne pas
        bloquer la requête HTTP (AGENTS.md §1).
        """
        actualite = await self.get(db, actualite_id)
        if actualite is None:
            return None
        actualite.statut = "publie"
        actualite.publie_at = datetime.now(UTC).replace(tzinfo=None)
        return actualite

    async def target_user_ids(
        self, db: AsyncSession, *, metier_id: int | None
    ) -> list[uuid.UUID]:
        """IDs des artisans (non-admin) ciblés par un métier donné (ou tous si `None`)."""
        stmt = select(User.id).where(User.is_admin == False)
        if metier_id is not None:
            stmt = stmt.where(User.metier_id == metier_id)
        res = await db.execute(stmt)
        return [row[0] for row in res.all()]

    async def unpublish(
        self, db: AsyncSession, actualite_id: uuid.UUID
    ) -> Actualite | None:
        actualite = await self.get(db, actualite_id)
        if actualite is None:
            return None
        actualite.statut = "brouillon"
        return actualite

    async def suggested_topics_from_feedback(
        self, db: AsyncSession, *, limit: int = 10
    ) -> list[dict[str, int]]:
        """Agrège les retours négatifs récents par conversation pour suggérer des sujets
        d'actualité (guides à publier). Pas de nouveau modèle : simple agrégation."""
        stmt = (
            select(Feedback.conversation_id, func.count(Feedback.id).label("negatifs"))
            .where(Feedback.rating < 0, Feedback.conversation_id.is_not(None))
            .group_by(Feedback.conversation_id)
            .order_by(func.count(Feedback.id).desc())
            .limit(limit)
        )
        res = await db.execute(stmt)
        return [
            {
                "conversation_id": str(row.conversation_id),
                "feedbacks_negatifs": row.negatifs,
            }
            for row in res.all()
        ]


actualite_service = ActualiteService()
