"""Schémas Pydantic : Utilisateur."""

import uuid

from pydantic import BaseModel


class UserCreate(BaseModel):
    telephone: str
    nom: str | None = None
    metier_id: int | None = None
    sous_metier_id: int | None = None


class UserResponse(BaseModel):
    id: uuid.UUID
    telephone: str
    nom: str | None
    metier_id: int | None
    sous_metier_id: int | None
    type_abonnement: str

    model_config = {"from_attributes": True}
