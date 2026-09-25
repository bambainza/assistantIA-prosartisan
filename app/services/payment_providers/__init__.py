"""Fournisseurs de paiement Mobile Money : sélection selon `PAYMENT_MODE`."""

from __future__ import annotations

from app.config import settings
from app.services.payment_providers.base import PaymentProvider
from app.services.payment_providers.demo import (
    DemoOrangeMoneyProvider,
    DemoWaveProvider,
)
from app.services.payment_providers.orange_money import OrangeMoneyLiveProvider
from app.services.payment_providers.wave import WaveLiveProvider

OPERATEURS = ("WAVE", "ORANGE")

_LIVE: dict[str, PaymentProvider] = {
    "WAVE": WaveLiveProvider(),
    "ORANGE": OrangeMoneyLiveProvider(),
}
_DEMO: dict[str, PaymentProvider] = {
    "WAVE": DemoWaveProvider(),
    "ORANGE": DemoOrangeMoneyProvider(),
}


def get_provider(operateur: str) -> PaymentProvider:
    """Fournisseur de l'opérateur (simulateur en mode démo, API officielle en live)."""
    providers = _DEMO if settings.payment_demo_mode else _LIVE
    try:
        return providers[operateur.upper()]
    except KeyError as exc:
        raise ValueError(f"Opérateur inconnu : {operateur}") from exc
