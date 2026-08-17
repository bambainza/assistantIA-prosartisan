"""Modèle ORM : Utilisateur (artisan)."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class User(Base):
    """Un artisan inscrit sur la plateforme ProsArtisan."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    telephone: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, index=True
    )
    nom: Mapped[str | None] = mapped_column(String(100), default=None)
    password_hash: Mapped[str | None] = mapped_column(String(255), default=None)

    metier_id: Mapped[int | None] = mapped_column(
        ForeignKey("metiers.id"), default=None
    )
    sous_metier_id: Mapped[int | None] = mapped_column(
        ForeignKey("sous_metiers.id"), default=None
    )
    type_abonnement: Mapped[str] = mapped_column(
        String(20), default="FREE"
    )

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    # Relations
    quota: Mapped["QuotaUtilisateur"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    transactions: Mapped[list["TransactionMobileMoney"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
