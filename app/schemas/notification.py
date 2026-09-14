"""Schémas Pydantic pour les notifications et l'enregistrement d'appareil."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NotificationOut(BaseModel):
    """Une notification adressée à l'utilisateur connecté."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    channel: str
    title: str
    body: str
    read_at: datetime | None
    created_at: datetime


class DeviceRegisterRequest(BaseModel):
    """Enregistrement du jeton d'appareil (FCM) pour les notifications push."""

    fcm_token: str = Field(..., min_length=10, max_length=255)


class WebPushKeys(BaseModel):
    """Clés cryptographiques d'un abonnement Web Push (fournies par le navigateur)."""

    p256dh: str
    auth: str


class WebPushSubscribeRequest(BaseModel):
    """Corps de `PushSubscription.toJSON()` tel que renvoyé par le navigateur."""

    endpoint: str = Field(..., min_length=10)
    keys: WebPushKeys


class WebPushUnsubscribeRequest(BaseModel):
    endpoint: str = Field(..., min_length=10)


class NotificationBroadcastRequest(BaseModel):
    """Composition d'une notification diffusée par un administrateur."""

    title: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1, max_length=1000)
    metier_id: int | None = Field(
        None, description="Null = tous les artisans, sinon ciblage par métier"
    )
    channel: str = Field("in_app", description="'in_app' ou 'push'")
