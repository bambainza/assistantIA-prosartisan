"""Modèle ORM : Journal d'audit des actions d'administration."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuditLog(Base):
    """Trace immuable d'une action sensible effectuée depuis le back-office admin."""

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None, index=True
    )
    # Format "<ressource>.<verbe>", ex: "package.update", "user.grant_pass", "role.assign".
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    resource_id: Mapped[str | None] = mapped_column(String(100), default=None)

    before_json: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"), default=None
    )
    after_json: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"), default=None
    )

    ip_address: Mapped[str | None] = mapped_column(String(45), default=None)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
