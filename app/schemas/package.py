"""Schémas Pydantic pour la gestion des packages et des abonnements."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PackageBase(BaseModel):
    """Caractéristiques fondamentales d'un package."""

    code: str = Field(
        ...,
        min_length=2,
        max_length=50,
        description="Code unique du package (ex: pass_mois)",
    )
    nom: str = Field(
        ..., min_length=2, max_length=100, description="Nom d'affichage commercial"
    )
    description: str | None = Field(
        None, description="Description détaillée de l'offre"
    )
    prix: int = Field(..., ge=0, description="Prix en F CFA (XOF)")
    devise: str = Field("XOF", max_length=5)
    type_package: str = Field(
        "DURATION", description="Type : 'DURATION', 'CREDITS', 'HYBRID'"
    )
    duree_jours: int | None = Field(
        None, ge=1, description="Durée de validité en jours"
    )
    quota_requetes: int | None = Field(
        None, ge=1, description="Volume de requêtes incluses"
    )
    auto_renouvelable: bool = Field(
        False, description="Renouvellement automatique par défaut"
    )
    model_config = ConfigDict(populate_by_name=True)

    est_actif: bool = Field(
        default=True, description="Visible et souscriptible au catalogue"
    )
    fonctionnalites: list[str] = Field(
        default_factory=list,
        description="Liste des avantages inclus",
    )

    @model_validator(mode="before")
    @classmethod
    def accepter_aliases_api(cls, data: object) -> object:
        """Accepte les noms historiques anglais sans alias Pydantic ambigu."""
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        if "est_actif" not in normalized and "is_active" in normalized:
            normalized["est_actif"] = normalized["is_active"]
        if "fonctionnalites" not in normalized and "features" in normalized:
            normalized["fonctionnalites"] = normalized["features"]
        return normalized


class PackageCreate(PackageBase):
    """Création d'un nouveau package."""


class PackageUpdate(BaseModel):
    """Mise à jour partielle d'un package."""

    model_config = ConfigDict(populate_by_name=True)

    nom: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = None
    prix: int | None = Field(default=None, ge=0)
    type_package: str | None = None
    duree_jours: int | None = Field(default=None, ge=1)
    quota_requetes: int | None = Field(default=None, ge=1)
    auto_renouvelable: bool | None = None
    est_actif: bool | None = None
    fonctionnalites: list[str] | None = None

    @model_validator(mode="before")
    @classmethod
    def accepter_aliases_api(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        if "est_actif" not in normalized and "is_active" in normalized:
            normalized["est_actif"] = normalized["is_active"]
        if "fonctionnalites" not in normalized and "features" in normalized:
            normalized["fonctionnalites"] = normalized["features"]
        return normalized


class PackageResponse(PackageBase):
    """Package avec identifiant et compteurs."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    abonnements_actifs_count: int = 0


class SubscriptionAssignRequest(BaseModel):
    """Attribution manuelle ou renouvellement d'un abonnement par un administrateur."""

    user_id: uuid.UUID = Field(..., description="ID de l'artisan bénéficiaire")
    package_id: uuid.UUID | None = Field(None, description="ID du package choisi")
    package_code: str | None = Field(
        None, description="Ou code du package (ex: pass_mois)"
    )
    duree_jours: int | None = Field(
        None, ge=1, description="Durée personnalisée (optionnelle)"
    )
    quota_initial: int | None = Field(
        None, ge=1, description="Quota personnalisé (optionnel)"
    )
    renouvellement_auto: bool = Field(
        False, description="Activer le renouvellement automatique"
    )


class SubscriptionExtendRequest(BaseModel):
    """Prolongation de la date d'échéance d'un abonnement."""

    jours_supplementaires: int = Field(
        30, ge=1, le=365, description="Nombre de jours à ajouter"
    )


class SubscriptionResponse(BaseModel):
    """Détail complet d'un abonnement / souscription artisan."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    user_nom: str
    user_telephone: str
    user_email: str | None
    user_metier: str
    package_id: uuid.UUID
    package_code: str
    package_nom: str
    package_prix: int
    package_type: str
    statut: str
    date_debut: datetime
    date_fin: datetime | None
    jours_restants: int | None
    quota_initial: int | None
    quota_consomme: int
    quota_restant: int | None
    renouvellement_auto: bool
    est_actif: bool


class SubscriptionsKPIs(BaseModel):
    """Indicateurs clés de performance du module packages."""

    total_inscrits: int = 0
    total_abonnements: int = 0
    abonnements_actifs: int = 0
    abonnements_expires: int = 0
    expirant_bientot: int = 0
    chiffre_affaires_mrr: int = 0
    repartition_packages: dict[str, int] = Field(default_factory=dict)
