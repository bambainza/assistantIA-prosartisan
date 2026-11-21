"""Modèle ORM : PaymentMethodConfig (activation/désactivation des moyens de paiement)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, String, func, true
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PaymentMethodConfig(Base):
    """Configuration d'activation d'un opérateur de paiement (Wave, Orange Money, CinetPay)."""

    __tablename__ = "payment_methods"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.now, server_default=func.now(), onupdate=func.now()
    )
