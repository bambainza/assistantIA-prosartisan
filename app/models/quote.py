"""Modèle ORM SQLAlchemy pour les devis et factures pro-forma générés pour les artisans."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.metier import Metier
    from app.models.user import User


class Quote(Base):
    """Devis ou facture pro-forma édité par un artisan via ProsArtisan."""

    __tablename__ = "quotes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    numero: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )
    titre: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    client_nom: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    client_telephone: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    client_adresse: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    metier_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("metiers.id", ondelete="SET NULL"),
        nullable=True,
    )
    statut: Mapped[str] = mapped_column(
        String(30),
        default="BROUILLON",
        nullable=False,
        index=True,
    )  # BROUILLON, ENVOYE, ACCEPTE, REFUSE, FACTURE, ANNULE
    items: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    total_ht: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    remise_pct: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )
    tva_pct: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )
    total_ttc: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    acompte_demande_pct: Mapped[float] = mapped_column(
        Float,
        default=30.0,
        nullable=False,
    )
    montant_acompte: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    mode_paiement: Mapped[str] = mapped_column(
        String(50),
        default="Wave / Orange Money",
        nullable=False,
    )
    delai_jours: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    date_emission: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
    )
    date_validite: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        onupdate=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
    )

    # Relations
    user: Mapped[User] = relationship("User", backref="quotes")
    metier: Mapped[Metier | None] = relationship("Metier")
