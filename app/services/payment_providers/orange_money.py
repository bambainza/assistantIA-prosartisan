"""
Orange Money WebPay (https://developer.orange.com/apis/om-webpay).

Parcours officiel :
1. Jeton OAuth2 : `POST /oauth/v3/token` (`Authorization: Basic
   base64(client_id:client_secret)`, `grant_type=client_credentials`).
2. `POST {webpay}/webpayment` avec `merchant_key`, `currency` (`OUV` en bac à
   sable, `XOF` en production), `order_id`, `amount`, `return_url`,
   `cancel_url`, `notif_url`, `lang`, `reference` → `{"status": 201,
   "pay_token": "...", "payment_url": "...", "notif_token": "..."}`.
3. L'artisan paie sur `payment_url`, puis revient sur `return_url` / `cancel_url`.
4. Orange notifie `notif_url` : `{"status": "SUCCESS" | "FAILED",
   "notif_token": "...", "txnid": "..."}`. Cette notification **n'est pas
   signée** : elle est authentifiée par le `notif_token` reçu à l'étape 2, puis
   confirmée par `POST {webpay}/webpayment/transactionstatus` (`order_id`,
   `amount`, `pay_token`) avant tout crédit.
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
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

_TIMEOUT = httpx.Timeout(15.0, connect=5.0)
_STATUTS = {
    "SUCCESS": StatutOperateur.SUCCES,
    "FAILED": StatutOperateur.ECHEC,
    "EXPIRED": StatutOperateur.EXPIRE,
    "INITIATED": StatutOperateur.EN_ATTENTE,
    "PENDING": StatutOperateur.EN_ATTENTE,
}


def statut_orange(value: Any) -> StatutOperateur:
    return _STATUTS.get(str(value or "").upper(), StatutOperateur.EN_ATTENTE)


@dataclass(frozen=True)
class OrangeMoneyNotification:
    statut: StatutOperateur
    notif_token: str
    txnid: str | None


def parse_orange_notification(body: bytes) -> OrangeMoneyNotification:
    """Analyse une notification WebPay (lève ValueError si le corps est invalide)."""
    data = json.loads(body)
    if not isinstance(data, dict) or not data.get("notif_token"):
        raise NotificationInvalideError("Notification Orange Money invalide.")
    return OrangeMoneyNotification(
        statut=statut_orange(data.get("status")),
        notif_token=str(data["notif_token"]),
        txnid=data.get("txnid"),
    )


class OrangeMoneyLiveProvider:
    """Appels réels à l'API Orange Money WebPay."""

    operateur = "ORANGE"

    def __init__(self) -> None:
        # Jeton OAuth2 mis en cache par worker jusqu'à son expiration (ce n'est
        # pas un état métier partagé : chaque worker peut obtenir le sien).
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    @property
    def _webpay_url(self) -> str:
        return f"{settings.orange_api_base}{settings.orange_webpay_path}"

    async def _access_token(self, client: httpx.AsyncClient) -> str:
        if self._token and time.time() < self._token_expires_at:
            return self._token
        credentials = base64.b64encode(
            f"{settings.orange_client_id}:{settings.orange_client_secret}".encode()
        ).decode("ascii")
        response = await client.post(
            f"{settings.orange_api_base}/oauth/v3/token",
            data={"grant_type": "client_credentials"},
            headers={"Authorization": f"Basic {credentials}"},
        )
        response.raise_for_status()
        data = response.json()
        self._token = data["access_token"]
        self._token_expires_at = time.time() + int(data.get("expires_in", 3600)) - 60
        return self._token

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                token = await self._access_token(client)
                response = await client.post(
                    f"{self._webpay_url}{path}",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json",
                    },
                )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise PaymentProviderError(
                f"Orange Money WebPay indisponible : {exc}"
            ) from exc

    async def create_checkout(self, request: CheckoutRequest) -> CheckoutSession:
        data = await self._post(
            "/webpayment",
            {
                "merchant_key": settings.orange_merchant_key,
                "currency": settings.orange_currency,
                "order_id": request.reference,
                "amount": request.montant,
                "return_url": request.success_url,
                "cancel_url": request.error_url,
                "notif_url": request.notif_url,
                "lang": "fr",
                "reference": "ProsArtisan",
            },
        )
        try:
            return CheckoutSession(
                session_id=data["pay_token"],
                payment_url=data["payment_url"],
                notif_token=data["notif_token"],
            )
        except KeyError as exc:
            raise PaymentProviderError(
                f"Réponse Orange Money incomplète : {exc}"
            ) from exc

    async def fetch_status(self, txn: TransactionMobileMoney) -> EtatPaiement:
        if not txn.provider_session_id:
            return EtatPaiement(StatutOperateur.EN_ATTENTE)
        data = await self._post(
            "/webpayment/transactionstatus",
            {
                "order_id": txn.reference_externe,
                "amount": txn.montant,
                "pay_token": txn.provider_session_id,
            },
        )
        return EtatPaiement(
            statut=statut_orange(data.get("status")),
            transaction_id=data.get("txnid"),
            # Le statut est demandé pour le montant enregistré : Orange ne
            # répond SUCCESS que si order_id, amount et pay_token concordent.
            montant=txn.montant,
        )
