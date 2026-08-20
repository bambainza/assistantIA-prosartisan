"""Modèle ORM : Utilisateur (artisan)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.conversation import Conversation
    from app.models.quota import QuotaUtilisateur
    from app.models.transaction import TransactionMobileMoney


class User(Base):
    """Un artisan inscrit sur la plateforme ProsArtisan."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True, index=True, default=None
    )
    telephone: Mapped[str | None] = mapped_column(
        String(20), unique=True, nullable=True, index=True, default=None
    )
    nom: Mapped[str | None] = mapped_column(String(100), default=None)
    password_hash: Mapped[str | None] = mapped_column(String(255), default=None)

    # Google OAuth fields
    google_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True, default=None
    )
    avatar_url: Mapped[str | None] = mapped_column(String(500), default=None)
    auth_provider: Mapped[str] = mapped_column(
        String(20), default="local"
    )  # "local", "google"

    metier_id: Mapped[int | None] = mapped_column(
        ForeignKey("metiers.id"), default=None
    )
    sous_metier_id: Mapped[int | None] = mapped_column(
        ForeignKey("sous_metiers.id"), default=None
    )
    type_abonnement: Mapped[str] = mapped_column(String(20), default="FREE")

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    # Relations
    quota: Mapped[QuotaUtilisateur] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    transactions: Mapped[list[TransactionMobileMoney]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    conversations: Mapped[list[Conversation]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
