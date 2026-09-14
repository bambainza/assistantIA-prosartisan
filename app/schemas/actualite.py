"""Schémas Pydantic pour le module Actualités."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ActualiteCreate(BaseModel):
    """Création d'une actualité (brouillon par défaut)."""

    titre: str = Field(..., min_length=3, max_length=200)
    contenu: str = Field(..., min_length=3)
    metier_id: int | None = Field(
        None, description="Null = diffusée à tous les métiers"
    )


class ActualiteUpdate(BaseModel):
    """Mise à jour partielle d'une actualité."""

    titre: str | None = Field(None, min_length=3, max_length=200)
    contenu: str | None = Field(None, min_length=3)
    metier_id: int | None = None


class ActualitePublishRequest(BaseModel):
    """Publication d'une actualité, avec notification optionnelle des artisans concernés."""

    notifier_artisans: bool = Field(
        False, description="Envoyer une notification in-app aux artisans ciblés"
    )


class ActualiteOut(BaseModel):
    """Une actualité, telle que consommée par le back-office ou le chat/mobile."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    titre: str
    contenu: str
    metier_id: int | None
    statut: str
    publie_at: datetime | None
    created_at: datetime
