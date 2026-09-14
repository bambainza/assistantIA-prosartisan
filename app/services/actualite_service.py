"""Service : Actualités (annonces/conseils métier) et suggestions issues du feedback."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.actualite import Actualite
from app.models.feedback import Feedback
from app.models.user import User


class ActualiteService:
    """CRUD des actualités et diffusion aux artisans concernés."""

    async def _promote_due_scheduled(self, db: AsyncSession) -> None:
        """Bascule "programme" → "publie" les actualités dont l'échéance est passée.

        Le projet n'a pas de tâche planifiée (pas de Celery/queue) : cette
        vérification "paresseuse" est faite à chaque lecture publique plutôt
        qu'en tâche de fond dédiée. Appelée uniquement depuis `list_published`
        (le flux réellement consommé par les artisans) pour limiter la portée
        de cet effet de bord dans un chemin de lecture. Best-effort : une
        panne ici ne doit jamais casser l'affichage des actualités déjà
        publiées (même repli que `rag_service.is_metier_active`) — l'élément
        programmé sera simplement retenté à la prochaine lecture.
        """
        try:
            now = datetime.now(UTC).replace(tzinfo=None)
            stmt = select(Actualite).where(
                Actualite.statut == "programme", Actualite.scheduled_at <= now
            )
            res = await db.execute(stmt)
            due = list(res.scalars().all())
            if not due:
                return
            for actualite in due:
                actualite.statut = "publie"
                actualite.publie_at = now
            await db.commit()
        except Exception:
            logging.getLogger("app").exception(
                "Échec de la bascule automatique des actualités programmées."
            )

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
        await self._promote_due_scheduled(db)

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
        category: str = "annonce",
        target_audience: str = "tous",
    ) -> Actualite:
        now = datetime.now(UTC).replace(tzinfo=None)
        actualite = Actualite(
            id=uuid.uuid4(),
            titre=titre,
            contenu=contenu,
            metier_id=metier_id,
            statut="brouillon",
            category=category,
            target_audience=target_audience,
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
        category: str | None = None,
        target_audience: str | None = None,
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
        if category is not None:
            actualite.category = category
        if target_audience is not None:
            actualite.target_audience = target_audience
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
        """Publie une actualité immédiatement (la rend visible via `list_published`).

        Annule au passage toute programmation en attente (`scheduled_at`) :
        une publication manuelle immédiate prime sur une échéance future.

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
        actualite.scheduled_at = None
        return actualite

    async def schedule(
        self, db: AsyncSession, actualite_id: uuid.UUID, *, scheduled_at: datetime
    ) -> Actualite | None:
        """Programme la publication future d'une actualité (statut "programme").

        La bascule effective vers "publie" a lieu paresseusement à la lecture
        publique une fois l'échéance atteinte, voir `_promote_due_scheduled`.
        """
        actualite = await self.get(db, actualite_id)
        if actualite is None:
            return None
        actualite.statut = "programme"
        actualite.scheduled_at = scheduled_at.replace(tzinfo=None)
        return actualite

    async def archive(
        self, db: AsyncSession, actualite_id: uuid.UUID
    ) -> Actualite | None:
        """Archive une actualité : la retire définitivement de la diffusion active
        sans la supprimer (conservée pour historique/audit)."""
        actualite = await self.get(db, actualite_id)
        if actualite is None:
            return None
        actualite.statut = "archive"
        return actualite

    async def target_user_ids(
        self,
        db: AsyncSession,
        *,
        metier_id: int | None,
        audience: str = "tous",
    ) -> list[uuid.UUID]:
        """IDs des artisans (non-admin) ciblés par métier et/ou segment d'audience."""
        stmt = select(User.id).where(User.is_admin == False)
        if metier_id is not None:
            stmt = stmt.where(User.metier_id == metier_id)
        if audience == "abonnes_payants":
            stmt = stmt.where(User.type_abonnement != "FREE")
        elif audience == "gratuits":
            stmt = stmt.where(User.type_abonnement == "FREE")
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
