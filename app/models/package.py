"""Modèle ORM : Package / Forfait (catalogue dynamique)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.subscription import UserSubscription


class Package(Base):
    """Offre commerciale de services ProsArtisan (durée, volume de requêtes, fonctionnalités)."""

    __tablename__ = "packages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    nom: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    prix: Mapped[int] = mapped_column(Integer, nullable=False)  # En F CFA (XOF)
    devise: Mapped[str] = mapped_column(String(5), default="XOF")

    # Type de forfait : 'DURATION' (ex. 24h, 30j), 'CREDITS' (ex. 50 questions), 'HYBRID'
    type_package: Mapped[str] = mapped_column(String(20), default="DURATION")

    duree_jours: Mapped[int | None] = mapped_column(Integer, default=None)
    quota_requetes: Mapped[int | None] = mapped_column(Integer, default=None)

    auto_renouvelable: Mapped[bool] = mapped_column(Boolean, default=False)
    est_actif: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # Fonctionnalités incluses (stockées en JSON / string pour SQLite/PG)
    fonctionnalites: Mapped[list[str] | dict[str, Any] | None] = mapped_column(
        JSONB().with_variant(Text, "sqlite"), default=list
    )

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    # Relations
    subscriptions: Mapped[list[UserSubscription]] = relationship(
        back_populates="package", cascade="all, delete-orphan"
    )
