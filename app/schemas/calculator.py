"""Schémas Pydantic pour les calculateurs techniques de chantier."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CalculateRequest(BaseModel):
    """Requête d'exécution d'un calcul technique de chantier."""

    tool_name: str = Field(
        ...,
        description="Nom de l'outil (ex: calculer_dosage_beton, calculer_section_cable...)",
    )
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Paramètres d'entrée du calculateur",
    )


class CalculateResponse(BaseModel):
    """Réponse structurée d'un calcul technique."""

    tool_name: str
    status: str = "success"
    result: dict[str, Any]


class CalculatorInfo(BaseModel):
    """Description d'un outil de calcul disponible."""

    name: str
    description: str
    parameters: dict[str, Any]
