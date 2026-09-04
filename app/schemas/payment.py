"""Schémas Pydantic : Paiement Mobile Money."""

from pydantic import BaseModel


class PaymentInitRequest(BaseModel):
    # L'utilisateur est déduit du JWT, jamais transmis par le client.
    type_pass: str  # "pass_24h" | "pass_mois" | "pack_50_requetes"


class PaymentInitResponse(BaseModel):
    status: str
    payment_url: str


class WebhookPayload(BaseModel):
    transaction_id: str
    status: str  # "ACCEPTED" | "REFUSED"
    metadata: dict | None = None
