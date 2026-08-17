"""Modèle ORM : Transaction Mobile Money."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class TransactionMobileMoney(Base):
    """Enregistrement d'un paiement Mobile Money (Wave, Orange, MTN, Moov)."""

    __tablename__ = "transactions_mobile_money"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    montant: Mapped[int] = mapped_column(Integer, nullable=False)
    devise: Mapped[str] = mapped_column(String(5), default="XOF")
    operateur: Mapped[str] = mapped_column(String(20), nullable=False)
    statut_paiement: Mapped[str] = mapped_column(String(20), default="PENDING")
    type_achat: Mapped[str] = mapped_column(String(30), nullable=False)
    reference_externe: Mapped[str | None] = mapped_column(String(255), default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Relations
    user: Mapped["User"] = relationship(back_populates="transactions")
