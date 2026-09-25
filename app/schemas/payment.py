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
    transaction_id: str | None = None
    reference_externe: str | None = None
    montant: int | None = None
    operateur: str | None = None
    mode: str | None = None  # "demo" | "live"


class TransactionStatusResponse(BaseModel):
    transaction_id: str
    # "PENDING" | "ACCEPTED" | "FAILED" | "EXPIRED" | "REFUNDED"
    statut: str
    operateur: str
    montant: int
    type_achat: str


class WebhookPayload(BaseModel):
    """Webhook générique (agrégateur), signé `X-Signature`."""

    transaction_id: str
    status: str  # "ACCEPTED" | "REFUSED"
    # Montant effectivement encaissé (FCFA, entier). Obligatoire pour qu'un
    # paiement abouti soit crédité : il doit égaler le montant de la transaction.
    montant: int | None = None
    metadata: dict | None = None
