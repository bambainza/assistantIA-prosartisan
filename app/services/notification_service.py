"""Service : Notifications (in-app, push, email, sms — canaux pluggables).

Chaque canal externe est un "provider" au sens `NotificationProvider` :
best-effort, jamais bloquant. Un provider non configuré (pas de clé API, pas
de device token) ne fait jamais échouer l'envoi global — il est seulement
journalisé comme non délivré. L'entrée in-app (écrite en base) est toujours
la source de vérité, consultable via `GET /api/notifications` même si aucun
canal externe n'est configuré ou n'a abouti.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Protocol

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.notification import Notification
from app.models.push_subscription import PushSubscription
from app.models.user import User

logger = logging.getLogger(__name__)

_FCM_MESSAGING_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"


class NotificationProvider(Protocol):
    """Un canal de livraison externe (push, sms, email...)."""

    async def send(self, *, target: str, title: str, body: str) -> bool: ...


class FcmPushProvider:
    """Envoi de notifications push via Firebase Cloud Messaging — API HTTP v1.

    Authentifié par compte de service (OAuth2), pas par une "clé serveur" :
    l'ancienne API FCM legacy est dépréciée par Google et n'est plus proposée
    pour les nouveaux projets Firebase. On utilise `google-auth` seul (pas le
    SDK complet `firebase-admin`, dont les dépendances entrent en conflit
    direct avec le pin `httpx` requis par `mistralai`).

    No-op journalisé si `FCM_SERVICE_ACCOUNT_PATH` n'est pas configuré, si le
    fichier est introuvable, ou si l'utilisateur n'a pas de device token —
    voir docs/PLAN_AMELIORATION.md (item 4.2).
    """

    def __init__(self) -> None:
        self._credentials = None  # google.oauth2.service_account.Credentials | None
        self._project_id: str | None = None
        self._load_attempted = False

    def _load_credentials_sync(self) -> None:
        self._load_attempted = True
        if not settings.fcm_service_account_path:
            return
        path = Path(settings.fcm_service_account_path)
        if not path.exists():
            logger.warning(
                "FCM_SERVICE_ACCOUNT_PATH configuré mais introuvable : %s", path
            )
            return
        try:
            from google.oauth2 import service_account

            credentials = service_account.Credentials.from_service_account_file(
                str(path), scopes=[_FCM_MESSAGING_SCOPE]
            )
            self._credentials = credentials
            self._project_id = credentials.project_id
        except Exception as exc:
            logger.warning("Compte de service FCM invalide (%s) : %s", path, exc)

    def _get_valid_token_sync(self) -> str | None:
        if not self._load_attempted:
            self._load_credentials_sync()
        if self._credentials is None:
            return None
        if not self._credentials.valid:
            from google.auth.transport.requests import Request as GoogleAuthRequest

            self._credentials.refresh(GoogleAuthRequest())
        return self._credentials.token

    async def send(self, *, target: str, title: str, body: str) -> bool:
        if not target:
            return False

        token = await asyncio.to_thread(self._get_valid_token_sync)
        if not token or not self._project_id:
            logger.info("Push FCM ignoré (compte de service non configuré) : %s", title)
            return False

        url = f"https://fcm.googleapis.com/v1/projects/{self._project_id}/messages:send"
        payload = {
            "message": {"token": target, "notification": {"title": title, "body": body}}
        }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                return response.status_code == 200
        except Exception as exc:
            logger.warning("Échec d'envoi push FCM : %s", exc)
            return False


class WebPushProvider:
    """Envoi de notifications Web Push aux navigateurs abonnés (protocole VAPID).

    Aucun compte tiers requis (contrairement à FCM) : la paire de clés VAPID
    est générée localement — voir `app.config.settings.vapid_private_key`.
    """

    def _send_sync(self, subscription: PushSubscription, title: str, body: str) -> bool:
        from pywebpush import WebPushException, webpush

        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {
                        "p256dh": subscription.p256dh_key,
                        "auth": subscription.auth_key,
                    },
                },
                data=json.dumps({"title": title, "body": body}),
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={"sub": f"mailto:{settings.vapid_claims_email}"},
            )
            return True
        except WebPushException as exc:
            logger.warning("Échec d'envoi Web Push : %s", exc)
            return False

    async def send_to_subscription(
        self, subscription: PushSubscription, title: str, body: str
    ) -> bool:
        # pywebpush est synchrone (requests) : on le déporte dans un thread
        # pour ne jamais bloquer la boucle événementielle asyncio.
        return await asyncio.to_thread(self._send_sync, subscription, title, body)


class NotificationService:
    """Écrit systématiquement l'entrée in-app, puis tente le(s) canal(aux) externe(s) demandé(s)."""

    def __init__(self) -> None:
        self.fcm_provider = FcmPushProvider()
        self.web_push_provider = WebPushProvider()

    async def notify(
        self,
        db: AsyncSession,
        *,
        user: User,
        title: str,
        body: str,
        channel: str = "in_app",
    ) -> Notification:
        """Crée la notification in-app et tente, en best-effort, le(s) canal(aux) demandé(s)."""
        entry = Notification(
            id=uuid.uuid4(),
            user_id=user.id,
            channel=channel,
            title=title,
            body=body,
        )
        db.add(entry)

        if channel == "push":
            if user.fcm_device_token:
                await self.fcm_provider.send(
                    target=user.fcm_device_token, title=title, body=body
                )

            stmt = select(PushSubscription).where(PushSubscription.user_id == user.id)
            res = await db.execute(stmt)
            for subscription in res.scalars().all():
                await self.web_push_provider.send_to_subscription(
                    subscription, title, body
                )

        return entry

    async def list_for_user(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Notification]:
        """Liste les notifications d'un utilisateur, les plus récentes d'abord."""
        stmt = select(Notification).where(Notification.user_id == user_id)
        if unread_only:
            stmt = stmt.where(Notification.read_at.is_(None))
        stmt = stmt.order_by(Notification.created_at.desc()).limit(limit).offset(offset)
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def count_unread(self, db: AsyncSession, *, user_id: uuid.UUID) -> int:
        stmt = select(func.count(Notification.id)).where(
            Notification.user_id == user_id, Notification.read_at.is_(None)
        )
        res = await db.execute(stmt)
        return res.scalar() or 0

    async def mark_read(
        self, db: AsyncSession, *, notification_id: uuid.UUID, user_id: uuid.UUID
    ) -> Notification | None:
        """Marque une notification comme lue — filtrée par propriétaire (anti-IDOR)."""
        stmt = select(Notification).where(
            Notification.id == notification_id, Notification.user_id == user_id
        )
        res = await db.execute(stmt)
        entry = res.scalar_one_or_none()
        if entry is None:
            return None
        entry.read_at = func.now()
        return entry


notification_service = NotificationService()
