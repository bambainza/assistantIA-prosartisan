"""Schémas Pydantic : Paiement Mobile Money."""

from typing import Literal

from pydantic import BaseModel


class PaymentInitRequest(BaseModel):
    # L'utilisateur est déduit du JWT, jamais transmis par le client.
    type_pass: str  # "pass_24h" | "pass_mois" | "pack_50_requetes"
    operateur: Literal["WAVE", "ORANGE"] = "WAVE"


class PaymentInitResponse(BaseModel):
    status: str
    payment_url: str


class WebhookPayload(BaseModel):
    transaction_id: str
    status: str  # "ACCEPTED" | "REFUSED"
    # Montant effectivement encaissé (FCFA, entier). Obligatoire pour qu'un
    # paiement abouti soit crédité : il doit égaler le montant de la transaction.
    montant: int | None = None
    metadata: dict | None = None
