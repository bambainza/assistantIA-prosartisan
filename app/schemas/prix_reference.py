"""Schémas Pydantic de la grille de prix de référence (back-office)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

TYPES_ITEM: tuple[str, ...] = ("FOURNITURE", "MAIN_D_OEUVRE", "FORFAIT")


def _type_item_valide(value: str) -> str:
    v = value.strip().upper()
    if v not in TYPES_ITEM:
        raise ValueError("type_item doit valoir FOURNITURE, MAIN_D_OEUVRE ou FORFAIT.")
    return v


class PrixReferenceCreate(BaseModel):
    """Création d'un prix de référence."""

    designation: str = Field(..., min_length=2, max_length=200)
    unite: str = Field(..., min_length=1, max_length=30)
    prix_unitaire: int = Field(..., ge=0, description="Prix unitaire en F CFA")
    type_item: str = Field(default="FOURNITURE")
    mots_cles: str | None = Field(
        default=None,
        max_length=500,
        description="Synonymes séparés par des virgules",
    )
    metier_id: int | None = Field(default=None, ge=1)
    commune: str | None = Field(default=None, max_length=100)
    source: str | None = Field(default=None, max_length=255)
    date_releve: date = Field(default_factory=date.today)
    is_active: bool = True

    _valider_type = field_validator("type_item")(_type_item_valide)


class PrixReferenceUpdate(BaseModel):
    """Mise à jour partielle d'un prix de référence."""

    designation: str | None = Field(default=None, min_length=2, max_length=200)
    unite: str | None = Field(default=None, min_length=1, max_length=30)
    prix_unitaire: int | None = Field(default=None, ge=0)
    type_item: str | None = None
    mots_cles: str | None = Field(default=None, max_length=500)
    metier_id: int | None = Field(default=None, ge=1)
    commune: str | None = Field(default=None, max_length=100)
    source: str | None = Field(default=None, max_length=255)
    date_releve: date | None = None
    is_active: bool | None = None

    @field_validator("type_item")
    @classmethod
    def _valider_type(cls, value: str | None) -> str | None:
        return None if value is None else _type_item_valide(value)


class PrixReferenceOut(BaseModel):
    """Prix de référence tel qu'exposé au back-office."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    designation: str
    unite: str
    prix_unitaire: int
    type_item: str
    mots_cles: str | None
    metier_id: int | None
    commune: str | None
    source: str | None
    date_releve: date
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None
