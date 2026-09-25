"""Schémas Pydantic pour le module Paramètres (gestion des données de référence :
métiers, sous-métiers, catégories d'actualités — alimentent les listes de choix
du back-office et de l'ingestion RAG).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SousMetierOut(BaseModel):
    """Une spécialité au sein d'un métier."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    metier_id: int
    nom: str
    slug: str


class SousMetierCreateRequest(BaseModel):
    """Création d'une spécialité, rattachée à un métier existant."""

    metier_id: int
    nom: str = Field(..., min_length=2, max_length=100)
    slug: str = Field(
        ..., min_length=2, max_length=100, pattern=r"^[a-z0-9][a-z0-9_-]*$"
    )


class SousMetierUpdateRequest(BaseModel):
    """Mise à jour d'une spécialité (le rattachement au métier ne change pas)."""

    nom: str | None = Field(None, min_length=2, max_length=100)
    slug: str | None = Field(
        None, min_length=2, max_length=100, pattern=r"^[a-z0-9][a-z0-9_-]*$"
    )


class MetierOut(BaseModel):
    """Un secteur d'activité artisanale et ses spécialités."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nom: str
    slug: str
    description: str | None = None
    is_active: bool
    sous_metiers: list[SousMetierOut] = Field(default_factory=list)

    @field_validator("is_active", mode="before")
    @classmethod
    def _default_is_active(cls, value: object) -> object:
        """Un `Metier` fraîchement créé et pas encore flush/commit expose `None`
        pour `is_active` (default Python appliqué seulement au flush) plutôt que
        `True` — même correctif que `UserProfile._normalise_is_admin`."""
        return value if value is not None else True


class MetierPublic(BaseModel):
    """Métier proposé dans les clients (sélecteur du chat)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nom: str
    slug: str


class MetierCreateRequest(BaseModel):
    """Création d'un nouveau métier."""

    nom: str = Field(..., min_length=2, max_length=100)
    slug: str = Field(
        ..., min_length=2, max_length=100, pattern=r"^[a-z0-9][a-z0-9_-]*$"
    )
    description: str | None = None


class MetierUpdateRequest(BaseModel):
    """Mise à jour d'un métier existant."""

    nom: str | None = Field(None, min_length=2, max_length=100)
    slug: str | None = Field(
        None, min_length=2, max_length=100, pattern=r"^[a-z0-9][a-z0-9_-]*$"
    )
    description: str | None = None


class ActualiteCategorieOut(BaseModel):
    """Une catégorie de référence pour les actualités."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    label: str
    is_active: bool

    @field_validator("is_active", mode="before")
    @classmethod
    def _default_is_active(cls, value: object) -> object:
        return value if value is not None else True


class ActualiteCategorieCreateRequest(BaseModel):
    """Création d'une catégorie d'actualité."""

    code: str = Field(
        ...,
        min_length=2,
        max_length=30,
        pattern=r"^[a-z][a-z0-9_]*$",
        description="Identifiant technique unique (ex: 'evenement').",
    )
    label: str = Field(..., min_length=2, max_length=100)


class ActualiteCategorieUpdateRequest(BaseModel):
    """Mise à jour du libellé d'une catégorie (le code reste immuable une fois créé,
    pour ne pas invalider les actualités qui le référencent déjà)."""

    label: str = Field(..., min_length=2, max_length=100)
