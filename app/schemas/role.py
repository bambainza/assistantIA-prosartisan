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
