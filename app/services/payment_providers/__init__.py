"""Fournisseurs de paiement Mobile Money : sélection selon `PAYMENT_MODE`."""

from __future__ import annotations

from app.config import settings
from app.services.payment_providers.base import PaymentProvider
from app.services.payment_providers.cinetpay import CinetPayLiveProvider
from app.services.payment_providers.demo import (
    DemoCinetPayProvider,
    DemoOrangeMoneyProvider,
    DemoWaveProvider,
)
from app.services.payment_providers.orange_money import OrangeMoneyLiveProvider
from app.services.payment_providers.wave import WaveLiveProvider

OPERATEURS = ("WAVE", "ORANGE", "CINETPAY")

# Moyen de paiement proposé en premier aux artisans (et retenu quand une
# requête `/api/payment/init` ne précise pas d'opérateur).
OPERATEUR_PAR_DEFAUT = "CINETPAY"


def ordonner_operateurs(codes: list[str]) -> list[str]:
    """Place l'opérateur par défaut en tête, sans changer l'ordre des autres."""
    return sorted(codes, key=lambda code: code != OPERATEUR_PAR_DEFAUT)


_LIVE: dict[str, PaymentProvider] = {
    "WAVE": WaveLiveProvider(),
    "ORANGE": OrangeMoneyLiveProvider(),
    "CINETPAY": CinetPayLiveProvider(),
}
_DEMO: dict[str, PaymentProvider] = {
    "WAVE": DemoWaveProvider(),
    "ORANGE": DemoOrangeMoneyProvider(),
    "CINETPAY": DemoCinetPayProvider(),
}


def get_provider(operateur: str) -> PaymentProvider:
    """Fournisseur de l'opérateur (simulateur en mode démo, API officielle en live)."""
    providers = _DEMO if settings.payment_demo_mode else _LIVE
    try:
        return providers[operateur.upper()]
    except KeyError as exc:
        raise ValueError(f"Opérateur inconnu : {operateur}") from exc
