"""Modèle ORM : Quota utilisateur (freemium / premium)."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class QuotaUtilisateur(Base):
    """Suivi des droits d'utilisation d'un artisan (gratuit ou premium)."""

    __tablename__ = "quotas_utilisateurs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    requetes_restantes_gratuites: Mapped[int] = mapped_column(
        Integer, default=5
    )
    date_fin_premium: Mapped[datetime | None] = mapped_column(default=None)

    # Relations
    user: Mapped["User"] = relationship(back_populates="quota")
