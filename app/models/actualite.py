"""Modèle ORM : Actualité (annonces et conseils métier publiés aux artisans)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Actualite(Base):
    """Une annonce ou un conseil publié par l'équipe, ciblé par métier (ou global)."""

    __tablename__ = "actualites"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    titre: Mapped[str] = mapped_column(String(200), nullable=False)
    contenu: Mapped[str] = mapped_column(Text, nullable=False)
    # None = diffusée à tous les métiers.
    metier_id: Mapped[int | None] = mapped_column(
        ForeignKey("metiers.id"), default=None
    )
    # "brouillon" | "programme" | "publie" | "archive"
    statut: Mapped[str] = mapped_column(String(20), default="brouillon", index=True)
    # "annonce" | "maintenance" | "conseil" | "promotion"
    category: Mapped[str] = mapped_column(String(30), default="annonce")
    # "tous" | "abonnes_payants" | "gratuits" — n'affecte que la notification
    # liée à la publication, pas la visibilité de l'actualité elle-même.
    target_audience: Mapped[str] = mapped_column(String(30), default="tous")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )

    # Publication différée : si renseignée et future, l'actualité reste au
    # statut "programme" jusqu'à ce qu'un appel à `list_published`/`list_all`
    # constate l'échéance passée et la fasse basculer en "publie" (voir
    # `ActualiteService._promote_scheduled`, pas de tâche planifiée dédiée).
    scheduled_at: Mapped[datetime | None] = mapped_column(default=None)
    publie_at: Mapped[datetime | None] = mapped_column(default=None)
    # `default=datetime.now` : une instance non encore rafraîchie depuis la base
    # (juste après construction, avant `db.refresh`) expose déjà un datetime
    # valide plutôt que `None` — cohérent avec app.models.feedback.Feedback.
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.now, server_default=func.now(), onupdate=func.now()
    )
