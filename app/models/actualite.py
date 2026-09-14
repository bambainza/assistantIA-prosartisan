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
    # "brouillon" | "publie"
    statut: Mapped[str] = mapped_column(String(20), default="brouillon", index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )

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
