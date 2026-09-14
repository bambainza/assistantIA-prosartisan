"""Router Notifications : centre de notifications in-app et enregistrement d'appareil push."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db
from app.middleware.auth import get_current_user_id
from app.models.push_subscription import PushSubscription
from app.models.user import User
from app.schemas.notification import (
    DeviceRegisterRequest,
    NotificationOut,
    WebPushSubscribeRequest,
    WebPushUnsubscribeRequest,
)
from app.services.notification_service import notification_service

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


@router.get("/vapid-public-key")
async def get_vapid_public_key() -> dict[str, str]:
    """Clé publique VAPID à fournir à `PushManager.subscribe()` côté navigateur.

    Publique par nature (elle circule dans le protocole Web Push) : aucune
    authentification requise pour la lire.
    """
    return {"public_key": settings.vapid_public_key}


@router.get("", response_model=list[NotificationOut])
async def list_notifications(
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[Any]:
    """Liste les notifications de l'utilisateur connecté (filtrées par propriétaire)."""
    return await notification_service.list_for_user(
        db,
        user_id=user_id,
        unread_only=unread_only,
        limit=min(limit, 200),
        offset=offset,
    )


@router.get("/unread-count")
async def get_unread_count(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    """Retourne le nombre de notifications non lues (badge)."""
    count = await notification_service.count_unread(db, user_id=user_id)
    return {"unread_count": count}


@router.patch("/{notification_id}/read", response_model=NotificationOut)
async def mark_notification_read(
    notification_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Marque une notification comme lue (anti-IDOR : filtrée par propriétaire)."""
    entry = await notification_service.mark_read(
        db, notification_id=notification_id, user_id=user_id
    )
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification introuvable.",
        )
    await db.commit()
    return entry


@router.post(
    "/register-device", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
async def register_device(
    payload: DeviceRegisterRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Enregistre le jeton d'appareil (FCM) de l'utilisateur connecté pour le push."""
    stmt = select(User).where(User.id == user_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable."
        )
    user.fcm_device_token = payload.fcm_token
    await db.commit()


@router.post(
    "/web-push/subscribe", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
async def subscribe_web_push(
    payload: WebPushSubscribeRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Enregistre un abonnement Web Push (un utilisateur peut avoir plusieurs
    navigateurs/appareils abonnés). Idempotent par `endpoint`."""
    stmt = select(PushSubscription).where(PushSubscription.endpoint == payload.endpoint)
    res = await db.execute(stmt)
    existing = res.scalar_one_or_none()

    if existing is not None:
        existing.user_id = user_id
        existing.p256dh_key = payload.keys.p256dh
        existing.auth_key = payload.keys.auth
    else:
        db.add(
            PushSubscription(
                id=uuid.uuid4(),
                user_id=user_id,
                endpoint=payload.endpoint,
                p256dh_key=payload.keys.p256dh,
                auth_key=payload.keys.auth,
            )
        )
    await db.commit()


@router.post(
    "/web-push/unsubscribe",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def unsubscribe_web_push(
    payload: WebPushUnsubscribeRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Supprime un abonnement Web Push (filtré par propriétaire — anti-IDOR)."""
    stmt = delete(PushSubscription).where(
        PushSubscription.endpoint == payload.endpoint,
        PushSubscription.user_id == user_id,
    )
    await db.execute(stmt)
    await db.commit()
