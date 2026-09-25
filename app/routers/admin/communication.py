"""
Router Admin — Communication : actualités et diffusion de notifications.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session, get_db
from app.middleware.auth import require_permission
from app.models.actualite import ActualiteCategorie
from app.models.user import User
from app.schemas.actualite import (
    ActualiteCreate,
    ActualiteOut,
    ActualitePublishRequest,
    ActualiteScheduleRequest,
    ActualiteUpdate,
)
from app.schemas.notification import NotificationBroadcastRequest
from app.services.actualite_service import actualite_service
from app.services.audit_service import audit_service
from app.services.notification_service import notification_service

router = APIRouter()


@router.get("/actualites", response_model=list[ActualiteOut])
async def get_actualites_list(
    statut: str | None = None,
    admin_id: uuid.UUID = Depends(require_permission("actualites.read")),
    db: AsyncSession = Depends(get_db),
) -> list[Any]:
    """Liste toutes les actualités (y compris brouillons), filtrable par statut."""
    return await actualite_service.list_all(db, statut=statut)


@router.get("/actualites/suggestions")
async def get_actualites_suggestions(
    admin_id: uuid.UUID = Depends(require_permission("actualites.read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Suggère des sujets d'actualité à partir des conversations les plus mal notées."""
    suggestions = await actualite_service.suggested_topics_from_feedback(db)
    return {"suggestions": suggestions}


@router.get("/actualites/categories")
async def get_actualites_categories(
    admin_id: uuid.UUID = Depends(require_permission("actualites.read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Catégories actives disponibles pour créer/éditer une actualité.

    Alimente le <select> du formulaire de création — la gestion complète
    (créer/renommer/désactiver une catégorie) vit dans le module Paramètres
    (`app.routers.parametres`, permission `parametres.write`).
    """
    stmt = (
        select(ActualiteCategorie)
        .where(ActualiteCategorie.is_active == True)
        .order_by(ActualiteCategorie.label)
    )
    res = await db.execute(stmt)
    categories = res.scalars().all()
    return {"categories": [{"code": c.code, "label": c.label} for c in categories]}


@router.post(
    "/actualites", status_code=status.HTTP_201_CREATED, response_model=ActualiteOut
)
async def create_actualite(
    payload: ActualiteCreate,
    request: Request,
    admin_id: uuid.UUID = Depends(require_permission("actualites.write")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Crée une actualité en brouillon (non visible tant qu'elle n'est pas publiée)."""
    actualite = await actualite_service.create(
        db,
        titre=payload.titre,
        contenu=payload.contenu,
        metier_id=payload.metier_id,
        created_by=admin_id,
        category=payload.category,
        target_audience=payload.target_audience,
    )
    await audit_service.log_action(
        db,
        actor_id=admin_id,
        action="actualite.create",
        resource_type="actualite",
        resource_id=str(actualite.id),
        after={"titre": actualite.titre, "metier_id": actualite.metier_id},
        request=request,
    )
    await db.commit()
    await db.refresh(actualite)
    return actualite


@router.put("/actualites/{actualite_id}", response_model=ActualiteOut)
async def update_actualite(
    actualite_id: uuid.UUID,
    payload: ActualiteUpdate,
    request: Request,
    admin_id: uuid.UUID = Depends(require_permission("actualites.write")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Met à jour le titre/contenu/ciblage métier d'une actualité."""
    actualite = await actualite_service.update(
        db,
        actualite_id,
        titre=payload.titre,
        contenu=payload.contenu,
        metier_id=payload.metier_id,
        category=payload.category,
        target_audience=payload.target_audience,
    )
    if actualite is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Actualité introuvable."
        )
    await audit_service.log_action(
        db,
        actor_id=admin_id,
        action="actualite.update",
        resource_type="actualite",
        resource_id=str(actualite_id),
        after=payload.model_dump(exclude_unset=True),
        request=request,
    )
    await db.commit()
    await db.refresh(actualite)
    return actualite


@router.post("/actualites/{actualite_id}/publish", response_model=ActualiteOut)
async def publish_actualite(
    actualite_id: uuid.UUID,
    payload: ActualitePublishRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    admin_id: uuid.UUID = Depends(require_permission("actualites.write")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Publie une actualité, avec notification in-app optionnelle des artisans ciblés
    (envoi en tâche de fond, potentiellement vers de nombreux artisans)."""
    actualite = await actualite_service.publish(db, actualite_id)
    if actualite is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Actualité introuvable."
        )

    if payload.notifier_artisans:
        target_ids = await actualite_service.target_user_ids(
            db, metier_id=actualite.metier_id, audience=actualite.target_audience
        )
        background_tasks.add_task(
            _broadcast_notifications_task,
            target_ids,
            actualite.titre,
            actualite.contenu[:500],
            "in_app",
        )

    await audit_service.log_action(
        db,
        actor_id=admin_id,
        action="actualite.publish",
        resource_type="actualite",
        resource_id=str(actualite_id),
        after={"notifier_artisans": payload.notifier_artisans},
        request=request,
    )
    await db.commit()
    await db.refresh(actualite)
    return actualite


@router.post("/actualites/{actualite_id}/schedule", response_model=ActualiteOut)
async def schedule_actualite(
    actualite_id: uuid.UUID,
    payload: ActualiteScheduleRequest,
    request: Request,
    admin_id: uuid.UUID = Depends(require_permission("actualites.write")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Programme la publication future d'une actualité (statut "programme")."""
    now = datetime.now(UTC).replace(tzinfo=None)
    scheduled_naive = payload.scheduled_at.replace(tzinfo=None)
    if scheduled_naive <= now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La date de programmation doit être dans le futur.",
        )

    actualite = await actualite_service.schedule(
        db, actualite_id, scheduled_at=payload.scheduled_at
    )
    if actualite is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Actualité introuvable."
        )
    await audit_service.log_action(
        db,
        actor_id=admin_id,
        action="actualite.schedule",
        resource_type="actualite",
        resource_id=str(actualite_id),
        after={"scheduled_at": scheduled_naive.isoformat()},
        request=request,
    )
    await db.commit()
    await db.refresh(actualite)
    return actualite


@router.post("/actualites/{actualite_id}/archive", response_model=ActualiteOut)
async def archive_actualite(
    actualite_id: uuid.UUID,
    request: Request,
    admin_id: uuid.UUID = Depends(require_permission("actualites.write")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Archive une actualité (retirée de la diffusion active, conservée pour historique)."""
    actualite = await actualite_service.archive(db, actualite_id)
    if actualite is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Actualité introuvable."
        )
    await audit_service.log_action(
        db,
        actor_id=admin_id,
        action="actualite.archive",
        resource_type="actualite",
        resource_id=str(actualite_id),
        request=request,
    )
    await db.commit()
    await db.refresh(actualite)
    return actualite


@router.post("/actualites/{actualite_id}/unpublish", response_model=ActualiteOut)
async def unpublish_actualite(
    actualite_id: uuid.UUID,
    request: Request,
    admin_id: uuid.UUID = Depends(require_permission("actualites.write")),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Repasse une actualité publiée en brouillon (la retire de la diffusion)."""
    actualite = await actualite_service.unpublish(db, actualite_id)
    if actualite is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Actualité introuvable."
        )
    await audit_service.log_action(
        db,
        actor_id=admin_id,
        action="actualite.unpublish",
        resource_type="actualite",
        resource_id=str(actualite_id),
        request=request,
    )
    await db.commit()
    await db.refresh(actualite)
    return actualite


@router.delete("/actualites/{actualite_id}")
async def delete_actualite(
    actualite_id: uuid.UUID,
    request: Request,
    admin_id: uuid.UUID = Depends(require_permission("actualites.write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Supprime définitivement une actualité."""
    deleted = await actualite_service.delete(db, actualite_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Actualité introuvable."
        )
    await audit_service.log_action(
        db,
        actor_id=admin_id,
        action="actualite.delete",
        resource_type="actualite",
        resource_id=str(actualite_id),
        request=request,
    )
    await db.commit()
    return {"status": "success", "message": "Actualité supprimée."}


async def _broadcast_notifications_task(
    user_ids: list[uuid.UUID], title: str, body: str, channel: str
) -> None:
    """Tâche de fond : crée une notification pour chaque artisan ciblé (session dédiée,
    indépendante de la requête HTTP d'origine — voir AGENTS.md §1). Une erreur ici
    (base momentanément indisponible...) est journalisée sans jamais remonter : la
    requête HTTP d'origine a déjà répondu 202, il n'y a personne pour la recevoir."""
    try:
        async with async_session() as session:
            stmt = select(User).where(User.id.in_(user_ids))
            res = await session.execute(stmt)
            for artisan in res.scalars().all():
                await notification_service.notify(
                    session, user=artisan, title=title, body=body, channel=channel
                )
            await session.commit()
    except Exception:
        logging.getLogger("app").exception(
            "Échec de la diffusion de notification en tâche de fond."
        )


@router.post("/notifications/broadcast", status_code=status.HTTP_202_ACCEPTED)
async def broadcast_notification(
    payload: NotificationBroadcastRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    admin_id: uuid.UUID = Depends(require_permission("notifications.send")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Compose et diffuse une notification aux artisans (tous, ciblés par métier
    et/ou par segment d'audience — abonnés payants ou gratuits).

    L'envoi effectif est exécuté en tâche de fond (potentiellement de
    nombreux artisans) ; la réponse est immédiate (202 Accepted).
    """
    target_ids = await actualite_service.target_user_ids(
        db, metier_id=payload.metier_id, audience=payload.target_audience
    )

    background_tasks.add_task(
        _broadcast_notifications_task,
        target_ids,
        payload.title,
        payload.body,
        payload.channel,
    )

    await audit_service.log_action(
        db,
        actor_id=admin_id,
        action="notification.broadcast",
        resource_type="notification",
        after={
            "metier_id": payload.metier_id,
            "target_audience": payload.target_audience,
            "channel": payload.channel,
            "cible_count": len(target_ids),
            "titre": payload.title,
        },
        request=request,
    )
    await db.commit()

    return {
        "status": "accepted",
        "cible_count": len(target_ids),
        "message": f"Diffusion lancée en arrière-plan vers {len(target_ids)} artisan(s).",
    }
