"""Schémas Pydantic pour la gestion des rôles et permissions (RBAC)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class PermissionOut(BaseModel):
    """Une permission granulaire."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    description: str | None = None


class RoleOut(BaseModel):
    """Un rôle et ses permissions associées."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    label: str
    permissions: list[PermissionOut] = Field(default_factory=list)


class RoleAssignRequest(BaseModel):
    """Attribution (ou retrait) d'un rôle RBAC à un compte administrateur."""

    role_code: str | None = Field(
        None,
        description=(
            "Code du rôle à assigner (ex: 'support'). "
            "Null pour retirer le rôle (accès admin hérité, non restreint)."
        ),
    )


class RoleCreateRequest(BaseModel):
    """Création d'un nouveau rôle RBAC, avec son jeu de permissions initial."""

    code: str = Field(
        ...,
        min_length=2,
        max_length=50,
        pattern=r"^[a-z][a-z0-9_]*$",
        description="Identifiant technique unique (ex: 'support_niveau_2').",
    )
    label: str = Field(..., min_length=2, max_length=100)
    permission_codes: list[str] = Field(
        default_factory=list,
        description="Codes des permissions à activer dès la création du rôle.",
    )


class RolePermissionsUpdateRequest(BaseModel):
    """Remplace l'intégralité du jeu de permissions actives d'un rôle.

    L'UI envoie l'ensemble complet des permissions cochées (activées) : toute
    permission absente de la liste est désactivée pour ce rôle.
    """

    permission_codes: list[str] = Field(default_factory=list)
