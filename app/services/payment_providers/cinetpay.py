"""
CinetPay v1 API (https://docs.cinetpay.com).

Parcours officiel :
1. Jeton OAuth : `POST {base}/v1/oauth/login` avec `{"api_key": ...,
   "api_password": ...}` → `{"access_token": "...", ...}`.
2. Initialisation du paiement web : `POST {base}/v1/payment` (Bearer token)
   avec `currency` (`XOF`), `merchant_transaction_id` (≤ 30 car.), `amount`,
   `lang="fr"`, `designation`, `client_email`, `client_first_name`,
   `client_last_name`, `direct_pay=false`, `success_url`, `failed_url`,
   `notify_url` (≤ 120 car.) → `{"code": 200, "status": "OK", "notify_token":
   "...", "transaction_id": "...", "payment_token": "...", "payment_url":
   "..."}`.
3. L'artisan paie sur `payment_url`, puis revient sur `success_url` /
   `failed_url`.
4. CinetPay sonde `notify_url` en `GET` (200 OK requis), puis envoie une
   notification `POST` : `{"notify_token": "...", "merchant_transaction_id":
   "...", "transaction_id": "...", "user": {...}}`.
   **Règle d'or sécurité** : ne jamais se fier au payload du webhook ;
   vérifier `notify_token` en temps constant, puis appeler systématiquement
   `GET {base}/v1/payment/{merchant_transaction_id}` pour récupérer le statut
   canonique (`100` / `SUCCESS`) avant tout crédit.
"""

from __future__ import annotations

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

_TIMEOUT = httpx.Timeout(15.0, connect=5.0)

_STATUTS_PAR_CHAINE = {
    "SUCCESS": StatutOperateur.SUCCES,
    "FAILED": StatutOperateur.ECHEC,
    "INSUFFICIENT_BALANCE": StatutOperateur.ECHEC,
    "EXPIRED": StatutOperateur.EXPIRE,
    "OTP_EXPIRED": StatutOperateur.EXPIRE,
    "INITIATED": StatutOperateur.EN_ATTENTE,
    "PENDING": StatutOperateur.EN_ATTENTE,
    "WAITING": StatutOperateur.EN_ATTENTE,
}

_STATUTS_PAR_CODE = {
    100: StatutOperateur.SUCCES,
    2001: StatutOperateur.EN_ATTENTE,
    2002: StatutOperateur.EN_ATTENTE,
    2003: StatutOperateur.EXPIRE,
    2005: StatutOperateur.ECHEC,
    2008: StatutOperateur.EXPIRE,
    2010: StatutOperateur.ECHEC,
}


def _parse_amount(value: Any) -> int | None:
    """Convertit un montant CinetPay en entier FCFA ; None si absent ou non entier."""
    if value is None:
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return int(amount) if amount == amount.to_integral_value() else None


def statut_cinetpay(status_val: Any, code_val: Any = None) -> StatutOperateur:
    """Normalise un statut/code CinetPay vers `StatutOperateur`."""
    try:
        if code_val is not None and int(code_val) in _STATUTS_PAR_CODE:
            return _STATUTS_PAR_CODE[int(code_val)]
    except (TypeError, ValueError):
        pass
    s = str(status_val or "").upper()
    if s in _STATUTS_PAR_CHAINE:
        return _STATUTS_PAR_CHAINE[s]
    return StatutOperateur.EN_ATTENTE


@dataclass(frozen=True)
class CinetPayNotification:
    notify_token: str
    merchant_transaction_id: str
    transaction_id: str | None


def parse_cinetpay_notification(body: bytes) -> CinetPayNotification:
    """Analyse une notification POST CinetPay (lève NotificationInvalideError si invalide)."""
    try:
        data = json.loads(body)
    except (ValueError, TypeError) as exc:
        raise NotificationInvalideError("Notification CinetPay illisible.") from exc
    if (
        not isinstance(data, dict)
        or not data.get("notify_token")
        or not data.get("merchant_transaction_id")
    ):
        raise NotificationInvalideError("Notification CinetPay incomplète.")
    tx_id = data.get("transaction_id")
    return CinetPayNotification(
        notify_token=str(data["notify_token"]),
        merchant_transaction_id=str(data["merchant_transaction_id"]),
        transaction_id=str(tx_id) if tx_id else None,
    )


class CinetPayLiveProvider:
    """Appels réels à l'API CinetPay v1."""

    operateur = "CINETPAY"

    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    async def _access_token(
        self, client: httpx.AsyncClient, force_refresh: bool = False
    ) -> str:
        if not force_refresh and self._token and time.time() < self._token_expires_at:
            return self._token
        response = await client.post(
            f"{settings.cinetpay_api_base}/v1/oauth/login",
            json={
                "api_key": settings.cinetpay_api_key,
                "api_password": settings.cinetpay_api_password,
            },
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        data = response.json()
        nested = data.get("data") if isinstance(data.get("data"), dict) else {}
        token = (
            data.get("access_token")
            or data.get("token")
            or nested.get("access_token")
            or nested.get("token")
        )
        if not token:
            raise PaymentProviderError("Jeton OAuth CinetPay absent de la réponse.")
        expires_in = int(data.get("expires_in") or nested.get("expires_in") or 3600)
        self._token = str(token)
        self._token_expires_at = time.time() + max(expires_in - 60, 60)
        return self._token

    async def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                token = await self._access_token(client)
                response = await client.request(
                    method,
                    f"{settings.cinetpay_api_base}{path}",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json",
                    },
                )
                # Renouvellement automatique si le jeton a expiré côté CinetPay
                if response.status_code == 401:
                    token = await self._access_token(client, force_refresh=True)
                    response = await client.request(
                        method,
                        f"{settings.cinetpay_api_base}{path}",
                        json=payload,
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Accept": "application/json",
                        },
                    )
                response.raise_for_status()
                body = response.json()
                if isinstance(body, dict) and body.get("code") in (1002, 1003):
                    token = await self._access_token(client, force_refresh=True)
                    response = await client.request(
                        method,
                        f"{settings.cinetpay_api_base}{path}",
                        json=payload,
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Accept": "application/json",
                        },
                    )
                    response.raise_for_status()
                    body = response.json()
                if not isinstance(body, dict):
                    raise PaymentProviderError("Réponse CinetPay invalide.")
                return body
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise PaymentProviderError(f"CinetPay indisponible : {exc}") from exc

    async def create_checkout(self, request: CheckoutRequest) -> CheckoutSession:
        payload: dict[str, Any] = {
            "currency": settings.cinetpay_currency,
            "merchant_transaction_id": request.reference[:30],
            "amount": request.montant,
            "lang": "fr",
            "designation": request.designation,
            "client_email": request.client_email,
            "client_first_name": request.client_first_name[:255],
            "client_last_name": request.client_last_name[:255],
            "direct_pay": False,
            "success_url": request.success_url,
            "failed_url": request.error_url,
            "notify_url": request.notif_url,
        }
        if request.client_phone_number:
            payload["client_phone_number"] = request.client_phone_number
        if settings.cinetpay_payment_method:
            payload["payment_method"] = settings.cinetpay_payment_method

        data = await self._request("POST", "/v1/payment", payload)
        details = data.get("details") if isinstance(data.get("details"), dict) else {}
        if details.get("status") == "FAILED" or details.get("code") == 2010:
            raise PaymentProviderError(
                f"Paiement CinetPay refusé à l'initialisation : {details.get('message', 'FAILED')}"
            )
        try:
            session_id = data.get("payment_token") or data["transaction_id"]
            return CheckoutSession(
                session_id=str(session_id),
                payment_url=str(data["payment_url"]),
                notif_token=str(data["notify_token"]),
            )
        except KeyError as exc:
            raise PaymentProviderError(f"Réponse CinetPay incomplète : {exc}") from exc

    async def fetch_status(self, txn: TransactionMobileMoney) -> EtatPaiement:
        if not txn.reference_externe:
            return EtatPaiement(StatutOperateur.EN_ATTENTE)
        data = await self._request("GET", f"/v1/payment/{txn.reference_externe}")
        # Les détails de statut peuvent être au premier niveau ou dans `details` / `data`.
        sous_objet = (
            data.get("details")
            if isinstance(data.get("details"), dict)
            else data.get("data")
            if isinstance(data.get("data"), dict)
            else {}
        )
        statut = statut_cinetpay(
            sous_objet.get("status") or data.get("status"),
            sous_objet.get("code") if "code" in sous_objet else data.get("code"),
        )
        tx_id = sous_objet.get("transaction_id") or data.get("transaction_id")

        raw_amount = (
            sous_objet.get("amount") if "amount" in sous_objet else data.get("amount")
        )
        montant = _parse_amount(raw_amount) if raw_amount is not None else txn.montant
        devise = sous_objet.get("currency") or data.get("currency")
        if devise and str(devise).upper() != settings.cinetpay_currency.upper():
            montant = None

        return EtatPaiement(
            statut=statut,
            transaction_id=str(tx_id) if tx_id else None,
            montant=montant,
        )
