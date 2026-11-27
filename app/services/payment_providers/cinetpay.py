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
import re
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

# Seuls SUCCESS (100), FAILED (2010) et INSUFFICIENT_BALANCE (2005) sont des
# statuts finaux selon la documentation CinetPay v1 (« Codes de statut »).
# EXPIRED (2003) et OTP_EXPIRED (2008) ne le sont pas : le paiement peut encore
# aboutir, la transaction reste donc en attente. La réconciliation la clôt
# localement après PAYMENT_PENDING_MAX_HOURS, et un succès confirmé plus tard
# est tout de même crédité (voir PaymentService._appliquer_etat).
_STATUTS_PAR_CHAINE = {
    "SUCCESS": StatutOperateur.SUCCES,
    "FAILED": StatutOperateur.ECHEC,
    "INSUFFICIENT_BALANCE": StatutOperateur.ECHEC,
    "EXPIRED": StatutOperateur.EN_ATTENTE,
    "OTP_EXPIRED": StatutOperateur.EN_ATTENTE,
    "INITIATED": StatutOperateur.EN_ATTENTE,
    "PENDING": StatutOperateur.EN_ATTENTE,
    "WAITING": StatutOperateur.EN_ATTENTE,
}

_STATUTS_PAR_CODE = {
    100: StatutOperateur.SUCCES,
    2001: StatutOperateur.EN_ATTENTE,
    2002: StatutOperateur.EN_ATTENTE,
    2003: StatutOperateur.EN_ATTENTE,
    2005: StatutOperateur.ECHEC,
    2008: StatutOperateur.EN_ATTENTE,
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


_CODES_JETON_INVALIDE = (1002, 1003)

# Codes d'erreur de la documentation CinetPay v1 (« Codes de statut ») qui ne
# décrivent pas un paiement mais un refus de la requête : jamais lus comme
# « paiement en attente », sinon la transaction resterait bloquée sans alerte.
_CODES_ERREUR_REQUETE = {
    -1: "OPERATION_ERROR",
    1004: "INVALID_PARAMS",
    1005: "INVALID_CREDENTIALS",
    2011: "NOT_ALLOWED (IP du serveur absente de la liste blanche CinetPay)",
}

_TELEPHONE_CI_RE = re.compile(r"^(?:\+225|00225|225)?(\d{10})$")


def telephone_international(telephone: str | None) -> str | None:
    """Numéro ivoirien au format attendu par CinetPay (`+2250707000000`).

    `client_phone_number` est facultatif : un numéro non reconnu n'est pas
    transmis plutôt que de faire échouer l'initialisation (`1004`).
    """
    if not telephone:
        return None
    compact = re.sub(r"[\s.\-()]", "", telephone)
    correspondance = _TELEPHONE_CI_RE.match(compact)
    return f"+225{correspondance.group(1)}" if correspondance else None


def _corps_json(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _jeton_rejete(response: httpx.Response) -> bool:
    """Jeton OAuth refusé : HTTP 401, ou code 1002/1003 quel que soit le statut HTTP."""
    if response.status_code == 401:
        return True
    return _corps_json(response).get("code") in _CODES_JETON_INVALIDE


def _erreur_cinetpay(response: httpx.Response) -> str:
    """Résumé d'une erreur CinetPay (HTTP, code et statut métier, jamais le jeton)."""
    body = _corps_json(response)
    details = " ".join(
        str(body[cle]) for cle in ("code", "status") if body.get(cle) is not None
    )
    return f"HTTP {response.status_code}" + (f" ({details})" if details else "")


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
        if response.is_error:
            # Ex. : HTTP 422 {"code": 1005, "status": "INVALID_CREDENTIALS"}.
            raise PaymentProviderError(
                f"Authentification CinetPay refusée : {_erreur_cinetpay(response)}"
            )
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

                async def envoyer(token: str) -> httpx.Response:
                    return await client.request(
                        method,
                        f"{settings.cinetpay_api_base}{path}",
                        json=payload,
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Accept": "application/json",
                        },
                    )

                response = await envoyer(await self._access_token(client))
                # Jeton expiré ou révoqué côté CinetPay : l'API répond
                # HTTP 422 {"code": 1002, "status": "INVALID_TOKEN"} (ou 401).
                # Le code est lu AVANT tout contrôle du statut HTTP, sinon le
                # renouvellement ne se déclencherait jamais.
                if _jeton_rejete(response):
                    response = await envoyer(
                        await self._access_token(client, force_refresh=True)
                    )
                if response.is_error:
                    raise PaymentProviderError(
                        f"CinetPay a refusé la requête : {_erreur_cinetpay(response)}"
                    )
                body = response.json()
                if not isinstance(body, dict):
                    raise PaymentProviderError("Réponse CinetPay invalide.")
                if body.get("code") in _CODES_ERREUR_REQUETE:
                    raise PaymentProviderError(
                        "CinetPay a refusé la requête : "
                        f"{body['code']} {_CODES_ERREUR_REQUETE[body['code']]}"
                    )
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
        telephone = telephone_international(request.client_phone_number)
        if telephone:
            payload["client_phone_number"] = telephone
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
