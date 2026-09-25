"""
Router Admin — Offres : packages commerciaux et abonnements des artisans.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.middleware.auth import require_permission
from app.schemas.package import (
    PackageCreate,
    PackageUpdate,
    SubscriptionAssignRequest,
    SubscriptionExtendRequest,
)
from app.services.audit_service import audit_service
from app.services.subscription_service import subscription_service

router = APIRouter()


@router.get("/packages")
async def get_packages_list(
    only_active: bool = False,
    admin_id: uuid.UUID = Depends(require_permission("packages.read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retourne la liste des packages commerciaux avec le nombre d'abonnés actifs."""
    packages = await subscription_service.list_packages(db, only_active=only_active)
    return {"packages": packages}


@router.post("/packages", status_code=status.HTTP_201_CREATED)
async def create_package(
    payload: PackageCreate,
    request: Request,
    admin_id: uuid.UUID = Depends(require_permission("packages.write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Crée une nouvelle offre commerciale."""
    try:
        pkg = await subscription_service.create_package(db, payload)
        await audit_service.log_action(
            db,
            actor_id=admin_id,
            action="package.create",
            resource_type="package",
            resource_id=str(pkg.id),
            after={"code": pkg.code, "nom": pkg.nom, "prix": pkg.prix},
            request=request,
        )
        await db.commit()
        return {
            "status": "success",
            "package": {
                "id": str(pkg.id),
                "code": pkg.code,
                "nom": pkg.nom,
                "description": pkg.description,
                "prix": pkg.prix,
                "devise": pkg.devise,
                "type_package": pkg.type_package,
                "duree_jours": pkg.duree_jours,
                "quota_requetes": pkg.quota_requetes,
                "auto_renouvelable": pkg.auto_renouvelable,
                "est_actif": pkg.est_actif,
                "fonctionnalites": pkg.fonctionnalites or [],
            },
        }
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )


@router.put("/packages/{package_id}")
async def update_package(
    package_id: uuid.UUID,
    payload: PackageUpdate,
    request: Request,
    admin_id: uuid.UUID = Depends(require_permission("packages.write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Met à jour une offre commerciale existante."""
    try:
        pkg = await subscription_service.update_package(db, package_id, payload)
        await audit_service.log_action(
            db,
            actor_id=admin_id,
            action="package.update",
            resource_type="package",
            resource_id=str(package_id),
            after=payload.model_dump(exclude_unset=True, by_alias=False),
            request=request,
        )
        await db.commit()
        return {
            "status": "success",
            "package": {
                "id": str(pkg.id),
                "code": pkg.code,
                "nom": pkg.nom,
                "description": pkg.description,
                "prix": pkg.prix,
                "devise": pkg.devise,
                "type_package": pkg.type_package,
                "duree_jours": pkg.duree_jours,
                "quota_requetes": pkg.quota_requetes,
                "auto_renouvelable": pkg.auto_renouvelable,
                "est_actif": pkg.est_actif,
                "fonctionnalites": pkg.fonctionnalites or [],
            },
        }
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )


@router.patch("/packages/{package_id}/toggle")
async def toggle_package(
    package_id: uuid.UUID,
    request: Request,
    active: bool | None = None,
    admin_id: uuid.UUID = Depends(require_permission("packages.write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Bascule ou définit l'état actif/inactif d'un package dans le catalogue."""
    try:
        pkg = await subscription_service.toggle_package(db, package_id, active=active)
        await audit_service.log_action(
            db,
            actor_id=admin_id,
            action="package.toggle",
            resource_type="package",
            resource_id=str(package_id),
            after={"est_actif": pkg.est_actif},
            request=request,
        )
        await db.commit()
        action_str = (
            "activé (mis en vente)"
            if pkg.est_actif
            else "désactivé (retiré de la vente)"
        )
        return {
            "status": "success",
            "package_id": str(package_id),
            "est_actif": pkg.est_actif,
            "is_active": pkg.est_actif,
            "message": f"Package '{pkg.nom}' {action_str} avec succès.",
        }
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )


@router.delete("/packages/{package_id}")
async def delete_package(
    package_id: uuid.UUID,
    request: Request,
    force: bool = False,
    admin_id: uuid.UUID = Depends(require_permission("packages.write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Supprime un package du catalogue (vérifie les abonnements actifs si force=False)."""
    try:
        res = await subscription_service.delete_package(db, package_id, force=force)
        await audit_service.log_action(
            db,
            actor_id=admin_id,
            action="package.delete",
            resource_type="package",
            resource_id=str(package_id),
            after={"force": force},
            request=request,
        )
        await db.commit()
        return res
    except ValueError as err:
        detail = str(err)
        status_code = (
            status.HTTP_404_NOT_FOUND
            if "introuvable" in detail.lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(
            status_code=status_code,
            detail=detail,
        )


@router.get("/subscriptions")
async def get_subscriptions_list(
    statut: str | None = None,
    package: str | None = None,
    q: str | None = None,
    admin_id: uuid.UUID = Depends(require_permission("packages.read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retourne la liste des inscrits et abonnements souscrits avec filtres."""
    subs = await subscription_service.list_subscriptions(
        db, status_filter=statut, package_code=package, query=q
    )
    return {"subscriptions": subs}


@router.post("/subscriptions/assign")
async def assign_subscription(
    payload: SubscriptionAssignRequest,
    request: Request,
    admin_id: uuid.UUID = Depends(require_permission("subscriptions.write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Assigne ou renouvelle manuellement un package à un artisan."""
    try:
        sub = await subscription_service.assign_subscription(db, payload)
        await audit_service.log_action(
            db,
            actor_id=admin_id,
            action="subscription.assign",
            resource_type="subscription",
            resource_id=str(sub.id),
            after={"user_id": str(payload.user_id), "package_id": str(sub.package_id)},
            request=request,
        )
        await db.commit()
        return {
            "status": "success",
            "message": "Abonnement assigné avec succès.",
            "subscription_id": str(sub.id),
        }
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )


@router.post("/subscriptions/{sub_id}/extend")
async def extend_subscription(
    sub_id: uuid.UUID,
    payload: SubscriptionExtendRequest,
    request: Request,
    admin_id: uuid.UUID = Depends(require_permission("subscriptions.write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Prolonge la durée d'un abonnement existant."""
    try:
        sub = await subscription_service.extend_subscription(
            db, sub_id, payload.jours_supplementaires
        )
        await audit_service.log_action(
            db,
            actor_id=admin_id,
            action="subscription.extend",
            resource_type="subscription",
            resource_id=str(sub_id),
            after={"jours_supplementaires": payload.jours_supplementaires},
            request=request,
        )
        await db.commit()
        return {
            "status": "success",
            "message": f"Abonnement prolongé de {payload.jours_supplementaires} jours.",
            "subscription_id": str(sub.id),
            "date_fin": sub.date_fin.isoformat() if sub.date_fin else None,
        }
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )


@router.post("/subscriptions/{sub_id}/cancel")
async def cancel_subscription(
    sub_id: uuid.UUID,
    request: Request,
    admin_id: uuid.UUID = Depends(require_permission("subscriptions.write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Résilie un abonnement et réinitialise l'artisan en formule gratuite."""
    try:
        sub = await subscription_service.cancel_subscription(db, sub_id)
        await audit_service.log_action(
            db,
            actor_id=admin_id,
            action="subscription.cancel",
            resource_type="subscription",
            resource_id=str(sub_id),
            request=request,
        )
        await db.commit()
        return {
            "status": "success",
            "message": "Abonnement résilié avec succès.",
            "subscription_id": str(sub.id),
        }
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )


@router.get("/subscriptions/stats")
async def get_subscription_stats(
    admin_id: uuid.UUID = Depends(require_permission("packages.read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Indicateurs clés et KPIs du module packages."""
    kpis = await subscription_service.get_subscription_kpis(db)
    return {"kpis": kpis}
