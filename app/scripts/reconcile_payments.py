"""
Réconciliation des paiements Mobile Money restés `PENDING`.

Avec une connectivité instable, une notification opérateur peut se perdre :
ce script redemande l'état de chaque paiement en attente depuis plus de
`--older-than` minutes (Wave : `GET /v1/checkout/sessions/{id}` ; Orange
Money : `transactionstatus`), puis crédite ou clôture la transaction — avec
les mêmes contrôles (montant, idempotence) que les webhooks.

À planifier toutes les 10 à 15 minutes (cron, Cloud Scheduler...).

Usage : python -m app.scripts.reconcile_payments [--older-than 15] [--limit 100]
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from app.db.session import async_session
from app.services.payment_service import payment_service


async def reconcile(older_than: int, limit: int) -> dict[str, int]:
    async with async_session() as db:
        return await payment_service.reconcile_pending(
            db, older_than_minutes=older_than, limit=limit
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--older-than", type=int, default=15)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    stats = asyncio.run(reconcile(args.older_than, args.limit))
    print(
        f"Vérifiées : {stats['verifiees']} — créditées : {stats['creditees']} — "
        f"clôturées : {stats['cloturees']} — erreurs : {stats['erreurs']}"
    )


if __name__ == "__main__":
    main()
