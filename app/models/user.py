"""Modèle ORM : Utilisateur (artisan)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, false, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.conversation import Conversation
    from app.models.quota import QuotaUtilisateur
    from app.models.role import Role
    from app.models.subscription import UserSubscription
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
    is_admin: Mapped[bool] = mapped_column(
        default=False, server_default=false(), nullable=False
    )
    # Rôle RBAC optionnel : affine les permissions d'un compte is_admin=True.
    # Un admin sans rôle assigné conserve l'accès complet historique (compatibilité
    # descendante) — voir app.middleware.auth.require_permission.
    role_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("roles.id"), default=None
    )

    # Authentification à deux facteurs (TOTP) — réservée aux comptes admin.
    totp_secret: Mapped[str | None] = mapped_column(String(64), default=None)
    totp_enabled: Mapped[bool] = mapped_column(
        default=False, server_default=false(), nullable=False
    )

    # Jeton de l'appareil pour les notifications push (Firebase Cloud Messaging).
    # Un seul appareil par compte dans cette première version (voir
    # docs/PLAN_AMELIORATION.md, item 4.2, pour le multi-device).
    fcm_device_token: Mapped[str | None] = mapped_column(String(255), default=None)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    # Relations
    quota: Mapped[QuotaUtilisateur] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    transactions: Mapped[list[TransactionMobileMoney]] = relationship(
        back_populates="user",
        foreign_keys="TransactionMobileMoney.user_id",
        cascade="all, delete-orphan",
    )
    conversations: Mapped[list[Conversation]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    subscriptions: Mapped[list[UserSubscription]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    role: Mapped[Role | None] = relationship(back_populates="users")
