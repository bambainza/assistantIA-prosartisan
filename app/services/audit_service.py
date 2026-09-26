"""Service : Journal d'audit des actions d'administration.

Chaque mutation sensible du back-office (packages, abonnements, documents,
rôles...) doit être tracée ici pour permettre l'investigation a posteriori :
qui a fait quoi, quand, sur quelle ressource, avec quel état avant/après.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.client_ip import get_client_ip
from app.models.audit_log import AuditLog


class AuditService:
    """Enregistrement et consultation du journal d'audit."""

    async def log_action(
        self,
        db: AsyncSession,
        *,
        actor_id: uuid.UUID,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        before: dict[str, Any] | list[Any] | None = None,
        after: dict[str, Any] | list[Any] | None = None,
        request: Request | None = None,
    ) -> AuditLog:
        """Prépare une entrée d'audit dans la session courante (pas de commit ici).

        L'action métier et sa trace d'audit doivent être validées ensemble par
        l'appelant (un seul `await db.commit()`) : on ne veut jamais d'action
        sensible réussie sans sa trace, ni l'inverse.
        """
        entry = AuditLog(
            id=uuid.uuid4(),
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            before_json=before,
            after_json=after,
            ip_address=get_client_ip(request) if request is not None else None,
        )
        db.add(entry)
        return entry

    async def list_logs(
        self,
        db: AsyncSession,
        *,
        actor_id: uuid.UUID | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditLog]:
        """Retourne les entrées du journal d'audit, les plus récentes d'abord."""
        stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
        if actor_id is not None:
            stmt = stmt.where(AuditLog.actor_id == actor_id)
        if action is not None:
            stmt = stmt.where(AuditLog.action == action)
        if resource_type is not None:
            stmt = stmt.where(AuditLog.resource_type == resource_type)
        stmt = stmt.limit(limit).offset(offset)
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def count_logs(
        self,
        db: AsyncSession,
        *,
        actor_id: uuid.UUID | None = None,
        action: str | None = None,
        resource_type: str | None = None,
    ) -> int:
        """Compte les entrées correspondant aux mêmes filtres que `list_logs`."""
        stmt = select(func.count(AuditLog.id))
        if actor_id is not None:
            stmt = stmt.where(AuditLog.actor_id == actor_id)
        if action is not None:
            stmt = stmt.where(AuditLog.action == action)
        if resource_type is not None:
            stmt = stmt.where(AuditLog.resource_type == resource_type)
        res = await db.execute(stmt)
        return res.scalar() or 0


audit_service = AuditService()
