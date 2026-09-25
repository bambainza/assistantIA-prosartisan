"""Contrat commun des fournisseurs de paiement Mobile Money (Wave, Orange Money)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.models.transaction import TransactionMobileMoney


class StatutOperateur(StrEnum):
    """État d'un paiement tel que rapporté par l'opérateur, normalisé."""

    SUCCES = "SUCCESS"
    ECHEC = "FAILED"
    EXPIRE = "EXPIRED"
    EN_ATTENTE = "PENDING"


@dataclass(frozen=True)
class CheckoutRequest:
    """Demande de création d'un paiement auprès de l'opérateur."""

    reference: str  # notre référence unique (`client_reference` / `order_id`)
    montant: int  # FCFA, entier
    success_url: str
    error_url: str
    notif_url: str


@dataclass(frozen=True)
class CheckoutSession:
    """Réponse de l'opérateur : où envoyer l'artisan pour payer."""

    session_id: str  # Wave : id `cos-...` ; Orange Money : `pay_token`
    payment_url: str  # Wave : `wave_launch_url` ; Orange Money : `payment_url`
    notif_token: str | None = None  # Orange Money uniquement


@dataclass(frozen=True)
class EtatPaiement:
    """État d'un paiement consulté auprès de l'opérateur."""

    statut: StatutOperateur
    transaction_id: str | None = None
    montant: int | None = None


class NotificationInvalideError(ValueError):
    """Corps de notification opérateur illisible ou incomplet."""


class PaymentProviderError(RuntimeError):
    """L'opérateur est injoignable ou a refusé la requête."""


class PaymentProvider(Protocol):
    """Interface d'un fournisseur (implémentations « live » et « demo »)."""

    operateur: str

    async def create_checkout(self, request: CheckoutRequest) -> CheckoutSession: ...

    async def fetch_status(self, txn: TransactionMobileMoney) -> EtatPaiement: ...
