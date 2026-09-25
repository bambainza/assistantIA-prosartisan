"""
Simulateur d'opérateurs (mode `PAYMENT_MODE=demo`).

Joue le rôle de Wave et d'Orange Money en attendant les accès officiels, en
reproduisant leurs parcours à l'identique côté ProsArtisan :

- création du paiement : mêmes identifiants (`cos-...` pour Wave ; `pay_token`
  + `notif_token` pour Orange Money) et une URL de paiement vers une page de
  simulation (`/api/payment/demo/checkout/{session}`) ;
- décision du payeur sur cette page (payer / annuler) ;
- notification envoyée **au format officiel** au même code de traitement que
  les webhooks réels : événement Wave signé `Wave-Signature` (avec
  `WAVE_WEBHOOK_SECRET`), notification Orange Money `{status, notif_token,
  txnid}` ensuite confirmée par `fetch_status` (équivalent `transactionstatus`) ;
- redirection vers `success_url` / `error_url` comme le ferait l'opérateur.

Passer en réel ne demande donc que les identifiants et `PAYMENT_MODE=live`.
"""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.config import settings
from app.models.transaction import TransactionMobileMoney
from app.services.cache_service import cache_service
from app.services.payment_providers.base import (
    CheckoutRequest,
    CheckoutSession,
    EtatPaiement,
    StatutOperateur,
)
from app.services.payment_providers.wave import (
    EVENEMENT_ECHEC,
    EVENEMENT_SUCCES,
    WAVE_SIGNATURE_HEADER,
    sign_wave_payload,
)

DEMO_CHECKOUT_ROUTE = "/api/payment/demo/checkout"
_STATE_TTL_SECONDS = 86400


def _state_key(session_id: str) -> str:
    return f"prosartisan:payment_demo:{session_id}"


async def charger_session(session_id: str) -> dict[str, Any] | None:
    """État d'une session simulée (None si inconnue ou expirée)."""
    raw = await cache_service.get(_state_key(session_id))
    return json.loads(raw) if raw else None


async def _enregistrer(session_id: str, state: dict[str, Any]) -> None:
    await cache_service.set(
        _state_key(session_id), json.dumps(state), ttl_seconds=_STATE_TTL_SECONDS
    )


class _DemoProvider:
    operateur: str

    async def _creer(self, request: CheckoutRequest, session_id: str, **extra: Any):
        await _enregistrer(
            session_id,
            {
                "operateur": self.operateur,
                "reference": request.reference,
                "montant": request.montant,
                "statut": StatutOperateur.EN_ATTENTE.value,
                "transaction_id": None,
                "success_url": request.success_url,
                "error_url": request.error_url,
                "created_at": int(time.time()),
                **extra,
            },
        )
        return f"{settings.public_base_url}{DEMO_CHECKOUT_ROUTE}/{session_id}"

    async def fetch_status(self, txn: TransactionMobileMoney) -> EtatPaiement:
        state = (
            await charger_session(txn.provider_session_id)
            if txn.provider_session_id
            else None
        )
        if state is None:
            return EtatPaiement(StatutOperateur.EXPIRE)
        return EtatPaiement(
            statut=StatutOperateur(state["statut"]),
            transaction_id=state.get("transaction_id"),
            montant=state["montant"],
        )


class DemoWaveProvider(_DemoProvider):
    operateur = "WAVE"

    async def create_checkout(self, request: CheckoutRequest) -> CheckoutSession:
        session_id = f"cos-{secrets.token_hex(8)}"
        url = await self._creer(request, session_id)
        return CheckoutSession(session_id=session_id, payment_url=url)


class DemoOrangeMoneyProvider(_DemoProvider):
    operateur = "ORANGE"

    async def create_checkout(self, request: CheckoutRequest) -> CheckoutSession:
        pay_token = f"v1{secrets.token_hex(16)}"
        notif_token = secrets.token_hex(16)
        url = await self._creer(request, pay_token, notif_token=notif_token)
        return CheckoutSession(
            session_id=pay_token, payment_url=url, notif_token=notif_token
        )


@dataclass(frozen=True)
class NotificationSimulee:
    """Notification que l'opérateur réel enverrait, prête à être traitée."""

    operateur: str
    body: bytes
    headers: dict[str, str]
    redirect_url: str


async def decision_du_payeur(
    session_id: str, accepte: bool
) -> NotificationSimulee | None:
    """Applique le choix du payeur et construit la notification au format officiel.

    Retourne None si la session est inconnue, expirée ou déjà traitée (un
    double clic ne produit pas deux notifications).
    """
    state = await charger_session(session_id)
    if state is None or state["statut"] != StatutOperateur.EN_ATTENTE.value:
        return None

    statut = StatutOperateur.SUCCES if accepte else StatutOperateur.ECHEC
    state["statut"] = statut.value
    if accepte:
        prefixe = "T_" if state["operateur"] == "WAVE" else "MP"
        state["transaction_id"] = f"{prefixe}{secrets.token_hex(6).upper()}"
    await _enregistrer(session_id, state)

    redirect_url = state["success_url"] if accepte else state["error_url"]
    if state["operateur"] == "WAVE":
        maintenant = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        event = {
            "id": f"EV_{secrets.token_hex(6)}",
            "type": EVENEMENT_SUCCES if accepte else EVENEMENT_ECHEC,
            "data": {
                "id": session_id,
                "amount": str(state["montant"]),
                "currency": "XOF",
                "client_reference": state["reference"],
                "checkout_status": "complete" if accepte else "open",
                "payment_status": "succeeded" if accepte else "cancelled",
                "transaction_id": state["transaction_id"],
                "when_completed": maintenant if accepte else None,
            },
        }
        body = json.dumps(event).encode("utf-8")
        timestamp = int(time.time())
        signature = sign_wave_payload(settings.wave_webhook_secret, timestamp, body)
        return NotificationSimulee(
            operateur="WAVE",
            body=body,
            headers={WAVE_SIGNATURE_HEADER: f"t={timestamp},v1={signature}"},
            redirect_url=redirect_url,
        )

    body = json.dumps(
        {
            "status": statut.value,
            "notif_token": state["notif_token"],
            "txnid": state["transaction_id"],
        }
    ).encode("utf-8")
    return NotificationSimulee(
        operateur="ORANGE", body=body, headers={}, redirect_url=redirect_url
    )
