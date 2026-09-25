"""
Wave Checkout API (https://docs.wave.com/checkout).

Parcours officiel :
1. `POST /v1/checkout/sessions` (Bearer API key) avec `amount` (chaîne),
   `currency=XOF`, `success_url`, `error_url`, `client_reference` →
   session `{"id": "cos-...", "wave_launch_url": "...", "payment_status":
   "processing", "checkout_status": "open", ...}`.
2. L'artisan est redirigé vers `wave_launch_url` et paie dans l'application
   Wave, puis revient sur `success_url` / `error_url`.
3. Wave notifie le webhook configuré dans le portail marchand :
   `{"id": "EV_...", "type": "checkout.session.completed" |
   "checkout.session.payment_failed", "data": <session>}`, signé par
   l'en-tête `Wave-Signature: t=<horodatage>,v1=<HMAC-SHA256(secret, t + corps)>`.
4. `GET /v1/checkout/sessions/{id}` permet de consulter l'état (réconciliation).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.config import settings
from app.models.transaction import TransactionMobileMoney
from app.services.payment_providers.base import (
    CheckoutRequest,
    CheckoutSession,
    EtatPaiement,
    NotificationInvalideError,
    PaymentProviderError,
    StatutOperateur,
)

WAVE_SIGNATURE_HEADER = "Wave-Signature"
EVENEMENT_SUCCES = "checkout.session.completed"
EVENEMENT_ECHEC = "checkout.session.payment_failed"
_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


def sign_wave_payload(secret: str, timestamp: int, body: bytes) -> str:
    """Signature `v1` d'un webhook Wave : HMAC-SHA256(secret, horodatage + corps brut)."""
    message = str(timestamp).encode("utf-8") + body
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_wave_signature(
    header: str | None,
    body: bytes,
    secret: str,
    tolerance_seconds: int,
    now: float | None = None,
) -> bool:
    """Vérifie l'en-tête `Wave-Signature` (plusieurs `v1` acceptés, rotation de secret).

    Refuse un horodatage hors de la fenêtre de tolérance : un webhook capturé
    ne peut pas être rejoué plus tard.
    """
    if not header:
        return False
    timestamp: int | None = None
    signatures: list[str] = []
    for part in header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError:
                return False
        elif key == "v1" and value:
            signatures.append(value)
    if timestamp is None or not signatures:
        return False
    if abs((now or time.time()) - timestamp) > tolerance_seconds:
        return False
    expected = sign_wave_payload(secret, timestamp, body)
    return any(hmac.compare_digest(expected, sig) for sig in signatures)


def _parse_amount(value: Any) -> int | None:
    """Montant Wave (chaîne décimale) → FCFA entier ; None si non entier ou invalide."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return int(amount) if amount == amount.to_integral_value() else None


def etat_depuis_session(data: dict[str, Any]) -> EtatPaiement:
    """Normalise une session Checkout Wave."""
    payment_status = data.get("payment_status")
    if payment_status == "succeeded":
        statut = StatutOperateur.SUCCES
    elif payment_status == "cancelled":
        statut = StatutOperateur.ECHEC
    elif data.get("checkout_status") == "expired":
        statut = StatutOperateur.EXPIRE
    else:
        statut = StatutOperateur.EN_ATTENTE
    return EtatPaiement(
        statut=statut,
        transaction_id=data.get("transaction_id"),
        montant=_parse_amount(data.get("amount")),
    )


@dataclass(frozen=True)
class WaveEvent:
    type: str
    session_id: str | None
    client_reference: str | None
    currency: str | None
    etat: EtatPaiement


def parse_wave_event(body: bytes) -> WaveEvent:
    """Analyse un événement webhook Wave (lève ValueError si le corps est invalide)."""
    event = json.loads(body)
    if not isinstance(event, dict) or not isinstance(event.get("data"), dict):
        raise NotificationInvalideError("Événement Wave invalide.")
    data = event["data"]
    etat = etat_depuis_session(data)
    if event.get("type") == EVENEMENT_ECHEC:
        etat = EtatPaiement(StatutOperateur.ECHEC, etat.transaction_id, etat.montant)
    return WaveEvent(
        type=str(event.get("type", "")),
        session_id=data.get("id"),
        client_reference=data.get("client_reference"),
        currency=data.get("currency"),
        etat=etat,
    )


class WaveLiveProvider:
    """Appels réels à l'API Wave Checkout."""

    operateur = "WAVE"

    def _headers(self, idempotency_key: str | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {settings.wave_api_key}"}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    async def create_checkout(self, request: CheckoutRequest) -> CheckoutSession:
        payload = {
            "amount": str(request.montant),
            "currency": "XOF",
            "success_url": request.success_url,
            "error_url": request.error_url,
            "client_reference": request.reference,
        }
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.post(
                    f"{settings.wave_api_base}/v1/checkout/sessions",
                    json=payload,
                    # Une nouvelle tentative réseau ne crée pas de 2e session.
                    headers=self._headers(idempotency_key=request.reference),
                )
            response.raise_for_status()
            data = response.json()
            return CheckoutSession(
                session_id=data["id"], payment_url=data["wave_launch_url"]
            )
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise PaymentProviderError(f"Wave Checkout indisponible : {exc}") from exc

    async def fetch_status(self, txn: TransactionMobileMoney) -> EtatPaiement:
        if not txn.provider_session_id:
            return EtatPaiement(StatutOperateur.EN_ATTENTE)
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.get(
                    f"{settings.wave_api_base}/v1/checkout/sessions/{txn.provider_session_id}",
                    headers=self._headers(),
                )
            response.raise_for_status()
            return etat_depuis_session(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise PaymentProviderError(f"Wave Checkout indisponible : {exc}") from exc
