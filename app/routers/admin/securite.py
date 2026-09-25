"""
Router Admin — Sécurité : rôles et permissions RBAC, statistiques de sécurité, journal d'audit.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.middleware.auth import require_permission
from app.models.audit_log import AuditLog
from app.models.role import Permission, Role
from app.models.user import User
from app.schemas.audit_log import AuditLogOut
from app.schemas.role import (
    PermissionOut,
    RoleAssignRequest,
    RoleCreateRequest,
    RoleOut,
    RolePermissionsUpdateRequest,
)
from app.services.audit_service import audit_service
from app.services.cache_service import cache_service

router = APIRouter()


@router.get("/roles", response_model=list[RoleOut])
async def get_roles_list(
    admin_id: uuid.UUID = Depends(require_permission("roles.read")),
    db: AsyncSession = Depends(get_db),
) -> list[Role]:
    """Retourne la liste des rôles RBAC disponibles avec leurs permissions."""
    stmt = select(Role).options(selectinload(Role.permissions)).order_by(Role.code)
    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.get("/permissions", response_model=list[PermissionOut])
async def get_permissions_list(
    admin_id: uuid.UUID = Depends(require_permission("roles.read")),
    db: AsyncSession = Depends(get_db),
) -> list[Permission]:
    """Retourne le catalogue complet des permissions granulaires."""
    stmt = select(Permission).order_by(Permission.code)
    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.post("/roles", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
async def create_role(
    payload: RoleCreateRequest,
    request: Request,
    admin_id: uuid.UUID = Depends(require_permission("roles.write")),
    db: AsyncSession = Depends(get_db),
) -> Role:
    """Crée un nouveau rôle RBAC, avec son jeu de permissions initial."""
    existing_stmt = select(Role).where(Role.code == payload.code)
    existing_res = await db.execute(existing_stmt)
    if existing_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Le rôle '{payload.code}' existe déjà.",
        )

    permissions: list[Permission] = []
    if payload.permission_codes:
        perms_stmt = select(Permission).where(
            Permission.code.in_(payload.permission_codes)
        )
        perms_res = await db.execute(perms_stmt)
        permissions = list(perms_res.scalars().all())
        found_codes = {p.code for p in permissions}
        missing = set(payload.permission_codes) - found_codes
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Permission(s) inconnue(s) : {', '.join(sorted(missing))}",
            )

    new_role = Role(
        id=uuid.uuid4(),
        code=payload.code,
        label=payload.label,
        permissions=permissions,
    )
    db.add(new_role)

    await audit_service.log_action(
        db,
        actor_id=admin_id,
        action="role.create",
        resource_type="role",
        resource_id=str(new_role.id),
        after={
            "code": new_role.code,
            "label": new_role.label,
            "permissions": sorted(payload.permission_codes),
        },
        request=request,
    )
    await db.commit()
    await db.refresh(new_role)
    return new_role


@router.put("/roles/{role_id}/permissions", response_model=RoleOut)
async def update_role_permissions(
    role_id: uuid.UUID,
    payload: RolePermissionsUpdateRequest,
    request: Request,
    admin_id: uuid.UUID = Depends(require_permission("roles.write")),
    db: AsyncSession = Depends(get_db),
) -> Role:
    """Remplace le jeu de permissions actives d'un rôle (active/désactive en bloc)."""
    role_stmt = (
        select(Role).options(selectinload(Role.permissions)).where(Role.id == role_id)
    )
    role_res = await db.execute(role_stmt)
    role = role_res.scalar_one_or_none()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Rôle introuvable."
        )

    before_codes = sorted(p.code for p in role.permissions)

    permissions: list[Permission] = []
    if payload.permission_codes:
        perms_stmt = select(Permission).where(
            Permission.code.in_(payload.permission_codes)
        )
        perms_res = await db.execute(perms_stmt)
        permissions = list(perms_res.scalars().all())
        found_codes = {p.code for p in permissions}
        missing = set(payload.permission_codes) - found_codes
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Permission(s) inconnue(s) : {', '.join(sorted(missing))}",
            )

    role.permissions = permissions

    await audit_service.log_action(
        db,
        actor_id=admin_id,
        action="role.permissions.update",
        resource_type="role",
        resource_id=str(role.id),
        before={"permissions": before_codes},
        after={"permissions": sorted(p.code for p in permissions)},
        request=request,
    )
    await db.commit()
    await db.refresh(role)
    return role


@router.post("/users/{user_id}/role")
async def assign_role_to_user(
    user_id: uuid.UUID,
    payload: RoleAssignRequest,
    request: Request,
    admin_id: uuid.UUID = Depends(require_permission("roles.write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Assigne (ou retire, si `role_code` est nul) un rôle RBAC à un compte admin."""
    user_stmt = select(User).where(User.id == user_id)
    user_res = await db.execute(user_stmt)
    user = user_res.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable."
        )

    before_role_id = str(user.role_id) if user.role_id else None
    new_role = None
    if payload.role_code is not None:
        role_stmt = select(Role).where(Role.code == payload.role_code)
        role_res = await db.execute(role_stmt)
        new_role = role_res.scalar_one_or_none()
        if not new_role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Rôle '{payload.role_code}' introuvable.",
            )
        user.role_id = new_role.id
    else:
        user.role_id = None

    await audit_service.log_action(
        db,
        actor_id=admin_id,
        action="role.assign",
        resource_type="user",
        resource_id=str(user_id),
        before={"role_id": before_role_id},
        after={"role_id": str(new_role.id) if new_role else None},
        request=request,
    )
    await db.commit()

    return {
        "status": "success",
        "user_id": str(user_id),
        "role_code": payload.role_code,
        "message": (
            f"Rôle '{payload.role_code}' assigné avec succès."
            if payload.role_code
            else "Rôle retiré : accès admin hérité (non restreint) restauré."
        ),
    }


@router.get("/security-stats")
async def get_security_stats(
    admin_id: uuid.UUID = Depends(require_permission("audit.read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Indicateurs sécurité pour le dashboard admin (fenêtre glissante de 30 jours)."""
    since_24h = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=24)
    stmt = select(func.count(AuditLog.id)).where(AuditLog.created_at >= since_24h)
    res = await db.execute(stmt)
    actions_24h = res.scalar() or 0

    async def _counter(key: str) -> int:
        value = await cache_service.get(f"prosartisan:security:{key}")
        return int(value) if value else 0

    return {
        "actions_admin_dernieres_24h": actions_24h,
        "tentatives_connexion_echouees_30j": await _counter("login_failed_total"),
        "webhooks_rejetes_30j": await _counter("webhook_rejected_total"),
        "tokens_revoques_30j": await _counter("revoked_tokens_total"),
    }


@router.get("/audit-logs", response_model=list[AuditLogOut])
async def get_audit_logs(
    actor_id: uuid.UUID | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
    admin_id: uuid.UUID = Depends(require_permission("audit.read")),
    db: AsyncSession = Depends(get_db),
) -> list[Any]:
    """Retourne le journal d'audit des actions administrateur, filtrable et paginé."""
    return await audit_service.list_logs(
        db,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        limit=min(limit, 200),
        offset=offset,
    )
