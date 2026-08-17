"""Schémas Pydantic : Quotas."""

from pydantic import BaseModel


class QuotaResponse(BaseModel):
    statut: str  # "premium" | "freemium"
    restantes: int | None = None
    message: str | None = None

    model_config = {"from_attributes": True}


class QuotaEpuiseResponse(BaseModel):
    code: int = 402
    message: str = "Quota gratuit épuisé. Passez à la version Pro."
    offres_disponibles: list[dict] = [
        {"id": "pass_24h", "nom": "Pass 24H Urgence", "prix": 500},
        {"id": "pass_mois", "nom": "Pass Mensuel Pro", "prix": 3000},
    ]
