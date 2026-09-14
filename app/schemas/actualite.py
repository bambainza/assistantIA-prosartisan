"""Schémas Pydantic pour le module Actualités."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

CATEGORIES_VALIDES = {"annonce", "maintenance", "conseil", "promotion"}
AUDIENCES_VALIDES = {"tous", "abonnes_payants", "gratuits"}


class ActualiteCreate(BaseModel):
    """Création d'une actualité (brouillon par défaut)."""

    titre: str = Field(..., min_length=3, max_length=200)
    contenu: str = Field(..., min_length=3)
    metier_id: int | None = Field(
        None, description="Null = diffusée à tous les métiers"
    )
    category: str = Field(
        "annonce", description="annonce|maintenance|conseil|promotion"
    )
    target_audience: str = Field(
        "tous", description="tous|abonnes_payants|gratuits — affine la notification"
    )


class ActualiteUpdate(BaseModel):
    """Mise à jour partielle d'une actualité."""

    titre: str | None = Field(None, min_length=3, max_length=200)
    contenu: str | None = Field(None, min_length=3)
    metier_id: int | None = None
    category: str | None = None
    target_audience: str | None = None


class ActualitePublishRequest(BaseModel):
    """Publication d'une actualité, avec notification optionnelle des artisans concernés."""

    notifier_artisans: bool = Field(
        False, description="Envoyer une notification in-app aux artisans ciblés"
    )


class ActualiteScheduleRequest(BaseModel):
    """Programme la publication future d'une actualité."""

    scheduled_at: datetime = Field(..., description="Date/heure de publication future")


class ActualiteOut(BaseModel):
    """Une actualité, telle que consommée par le back-office ou le chat/mobile."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    titre: str
    contenu: str
    metier_id: int | None
    statut: str
    category: str
    target_audience: str
    scheduled_at: datetime | None
    publie_at: datetime | None
    created_at: datetime

    @field_validator("category", mode="before")
    @classmethod
    def _default_category(cls, value: object) -> object:
        """Un ``Actualite`` non encore rafraîchi depuis la base expose ``None``
        pour les colonnes à défaut Python (`default=`, appliqué seulement au
        flush) plutôt que la valeur par défaut — même correctif que
        `UserProfile._normalise_is_admin`."""
        return value if value is not None else "annonce"

    @field_validator("target_audience", mode="before")
    @classmethod
    def _default_target_audience(cls, value: object) -> object:
        return value if value is not None else "tous"
