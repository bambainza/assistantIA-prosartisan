"""Modèle ORM : Abonnement Utilisateur (souscription à un package)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.package import Package
    from app.models.user import User


class UserSubscription(Base):
    """Suivi d'un abonnement actif ou historique souscrit par un artisan."""

    __tablename__ = "user_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    package_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("packages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # États possibles : 'ACTIVE', 'EXPIRED', 'GRACE_PERIOD', 'CANCELED'
    statut: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)

    date_debut: Mapped[datetime] = mapped_column(server_default=func.now())
    date_fin: Mapped[datetime | None] = mapped_column(default=None, index=True)

    quota_initial: Mapped[int | None] = mapped_column(Integer, default=None)
    quota_consomme: Mapped[int] = mapped_column(Integer, default=0)

    renouvellement_auto: Mapped[bool] = mapped_column(Boolean, default=False)
    date_prochain_renouvellement: Mapped[datetime | None] = mapped_column(default=None)
    tentatives_renouvellement: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    # Relations
    user: Mapped[User] = relationship(back_populates="subscriptions")
    package: Mapped[Package] = relationship(back_populates="subscriptions")

    @property
    def quota_restant(self) -> int | None:
        """Nombre de requêtes restantes si forfait limité."""
        if self.quota_initial is None:
            return None
        return max(0, self.quota_initial - self.quota_consomme)

    @property
    def jours_restants(self) -> int | None:
        """Nombre de jours restants avant expiration."""
        if not self.date_fin:
            return None
        from datetime import UTC, datetime

        now = datetime.now(UTC).replace(tzinfo=None)
        end = (
            self.date_fin.replace(tzinfo=None)
            if self.date_fin.tzinfo
            else self.date_fin
        )
        delta = end - now
        return max(0, delta.days)

    @property
    def est_actif(self) -> bool:
        """Indique si l'abonnement est actif et non expiré."""
        if self.statut != "ACTIVE":
            return False
        if self.date_fin is not None:
            from datetime import UTC, datetime

            now = datetime.now(UTC).replace(tzinfo=None)
            end = (
                self.date_fin.replace(tzinfo=None)
                if self.date_fin.tzinfo
                else self.date_fin
            )
            if end < now:
                return False
        return not (
            self.quota_initial is not None
            and self.quota_restant is not None
            and self.quota_restant <= 0
        )
