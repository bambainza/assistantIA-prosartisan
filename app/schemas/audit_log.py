"""Schémas Pydantic pour la consultation du journal d'audit."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditLogOut(BaseModel):
    """Une entrée du journal d'audit."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_id: uuid.UUID | None
    action: str
    resource_type: str
    resource_id: str | None
    before_json: dict[str, Any] | list[Any] | None
    after_json: dict[str, Any] | list[Any] | None
    ip_address: str | None
    created_at: datetime
