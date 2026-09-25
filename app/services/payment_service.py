"""
Service de Paiement Mobile Money & Gestion des Webhooks.

Parcours officiels Wave Checkout et Orange Money WebPay (voir
`app/services/payment_providers/`), en mode `demo` (simulateur fidèle) ou
`live` (API officielles) selon `PAYMENT_MODE` :

1. `initialize_payment` enregistre la transaction `PENDING`, puis crée le
   paiement chez l'opérateur et renvoie son URL de paiement.
2. L'opérateur notifie : `handle_wave_webhook` (signature `Wave-Signature`
   obligatoire) ou `handle_orange_money_notification` (`notif_token`
   obligatoire, puis confirmation par `transactionstatus`).
3. `_appliquer_etat` crédite le Pass une seule fois (idempotence), et
   seulement si le montant confirmé par l'opérateur est exact.
4. `reconcile_pending` rattrape les notifications perdues (réseau instable).

Le webhook générique `process_webhook` (en-tête `X-Signature`) est conservé
pour une intégration via agrégateur.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.quota import QuotaUtilisateur
from app.models.transaction import TransactionMobileMoney
from app.services.payment_providers import OPERATEURS, get_provider
from app.services.payment_providers.base import (
    CheckoutRequest,
    EtatPaiement,
    PaymentProviderError,
    StatutOperateur,
)
from app.services.payment_providers.orange_money import parse_orange_notification
from app.services.payment_providers.wave import parse_wave_event, verify_wave_signature

logger = logging.getLogger(__name__)

# Statuts opérateur considérés comme un paiement abouti
STATUTS_PAIEMENT_ABOUTIS = {"ACCEPTED", "SUCCESS", "PAID"}
# Statut enregistré pour un paiement abouti (celui que suivent le tableau de
# bord admin et le module Finance).
STATUT_ABOUTI = "ACCEPTED"
STATUTS_FINAUX = STATUTS_PAIEMENT_ABOUTIS | {"FAILED", "EXPIRED", "REFUNDED"}

TARIFS_PASS = {
    "pass_24h": {"nom": "Pass 24H Urgence", "montant": 500, "duree_heures": 24},
    "pass_mois": {"nom": "Pass Mensuel Pro", "montant": 3000, "duree_heures": 24 * 30},
    "pack_50_requetes": {"nom": "Pack 50 Requêtes", "montant": 1500, "requetes": 50},
}


class PaiementIndisponibleError(RuntimeError):
    """Paiement impossible pour l'instant (opérateur injoignable, démo en production)."""


class WebhookNonAuthentifieError(RuntimeError):
    """Notification opérateur sans signature / jeton valide (→ 401)."""


def urls_de_retour(txn_id: uuid.UUID) -> tuple[str, str]:
    """URLs de retour transmises à l'opérateur (succès, échec/annulation)."""
    base = f"{settings.public_base_url}/chat/?transaction={txn_id}&paiement="
    return base + "succes", base + "echec"


class PaymentService:
    """Gestionnaire de transactions Mobile Money."""

    # ── Création du paiement ──

    def paiement_disponible(self) -> bool:
        """Le simulateur ne délivre jamais de Pass gratuit en production par défaut."""
        return not (
            settings.is_production
            and settings.payment_demo_mode
            and not settings.payment_demo_in_production
        )

    async def initialize_payment(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        type_pass: str,
        operateur: str = "WAVE",
    ) -> dict[str, Any]:
        """Enregistre la transaction puis crée le paiement chez l'opérateur."""
        if type_pass not in TARIFS_PASS:
            raise ValueError(f"Type de pass inconnu: {type_pass}")
        if operateur not in OPERATEURS:
            raise ValueError(f"Opérateur inconnu: {operateur}")
        if not self.paiement_disponible():
            raise PaiementIndisponibleError(
                "Paiement Mobile Money bientôt disponible (intégration opérateur en cours)."
            )

        info_pass = TARIFS_PASS[type_pass]

        # La transaction est enregistrée AVANT l'appel opérateur : aucune URL de
        # paiement n'existe pour une transaction inconnue de notre base (une
        # erreur d'écriture remonte en 500, jamais d'URL renvoyée).
        ref_ext = f"REF-{uuid.uuid4().hex[:12].upper()}"
        txn = TransactionMobileMoney(
            id=uuid.uuid4(),
            user_id=user_id,
            montant=info_pass["montant"],
            devise="XOF",
            operateur=operateur,
            statut_paiement="PENDING",
            type_achat=type_pass,
            reference_externe=ref_ext,
        )
        db.add(txn)
        await db.commit()

        success_url, error_url = urls_de_retour(txn.id)
        try:
            session = await get_provider(operateur).create_checkout(
                CheckoutRequest(
                    reference=ref_ext,
                    montant=info_pass["montant"],
                    success_url=success_url,
                    error_url=error_url,
                    notif_url=f"{settings.public_base_url}/api/payment/webhooks/orange-money",
                )
            )
        except PaymentProviderError as exc:
            logger.error("Création du paiement %s impossible : %s", ref_ext, exc)
            txn.statut_paiement = "FAILED"
            await db.commit()
            raise PaiementIndisponibleError(
                "L'opérateur de paiement est momentanément indisponible."
            ) from exc

        txn.provider_session_id = session.session_id
        txn.provider_notif_token = session.notif_token
        txn.payment_url = session.payment_url
        await db.commit()

        return {
            "status": "success",
            "transaction_id": str(txn.id),
            "reference_externe": ref_ext,
            "montant": info_pass["montant"],
            "operateur": operateur,
            "payment_url": session.payment_url,
            "mode": "demo" if settings.payment_demo_mode else "live",
        }

    # ── Application d'un état opérateur ──

    async def _crediter(self, db: AsyncSession, txn: TransactionMobileMoney) -> None:
        """Débloque le Pass / les crédits correspondant à la transaction."""
        info_pass = TARIFS_PASS.get(txn.type_achat, {})
        quota_res = await db.execute(
            select(QuotaUtilisateur).where(QuotaUtilisateur.user_id == txn.user_id)
        )
        quota_obj = quota_res.scalar_one_or_none()
        if not quota_obj:
            quota_obj = QuotaUtilisateur(user_id=txn.user_id, credits_requetes=0)
            db.add(quota_obj)

        now = datetime.now(UTC)
        if "duree_heures" in info_pass:
            start_base = (
                quota_obj.date_fin_premium.replace(tzinfo=UTC)
                if (
                    quota_obj.date_fin_premium
                    and quota_obj.date_fin_premium.replace(tzinfo=UTC) > now
                )
                else now
            )
            quota_obj.date_fin_premium = start_base + timedelta(
                hours=info_pass["duree_heures"]
            )
        elif "requetes" in info_pass:
            quota_obj.credits_requetes = (quota_obj.credits_requetes or 0) + info_pass[
                "requetes"
            ]

    async def _appliquer_etat(
        self, db: AsyncSession, txn: TransactionMobileMoney, etat: EtatPaiement
    ) -> dict[str, Any]:
        """Applique l'état confirmé par l'opérateur (idempotent)."""
        if txn.statut_paiement in STATUTS_PAIEMENT_ABOUTIS:
            return {
                "status": "success",
                "message": "Paiement déjà traité (webhook idempotent)",
                "user_id": str(txn.user_id),
            }
        if txn.statut_paiement in STATUTS_FINAUX:
            return {"status": "ignored", "message": "Transaction déjà clôturée"}

        if etat.statut is StatutOperateur.SUCCES:
            if etat.montant != txn.montant:
                logger.warning(
                    "Paiement %s refusé : montant confirmé %s, attendu %s.",
                    txn.reference_externe,
                    etat.montant,
                    txn.montant,
                )
                return {
                    "status": "montant_invalide",
                    "message": "Montant du paiement absent ou non conforme à la transaction",
                }
            txn.statut_paiement = STATUT_ABOUTI
            txn.provider_transaction_id = etat.transaction_id
            await self._crediter(db, txn)
            await db.commit()
            return {
                "status": "success",
                "message": "Pass débloqué avec succès",
                "user_id": str(txn.user_id),
            }

        if etat.statut in (StatutOperateur.ECHEC, StatutOperateur.EXPIRE):
            txn.statut_paiement = etat.statut.value
            await db.commit()
            return {"status": "declined", "message": "Paiement refusé ou annulé"}

        return {"status": "pending", "message": "Paiement en cours chez l'opérateur"}

    # ── Webhooks officiels ──

    async def handle_wave_webhook(
        self, db: AsyncSession, raw_body: bytes, signature_header: str | None
    ) -> dict[str, Any]:
        """Webhook Wave Checkout : `Wave-Signature` obligatoire (horodatage + HMAC)."""
        if not verify_wave_signature(
            signature_header,
            raw_body,
            settings.wave_webhook_secret,
            settings.payment_webhook_tolerance_seconds,
        ):
            raise WebhookNonAuthentifieError("Signature Wave manquante ou invalide")

        try:
            event = parse_wave_event(raw_body)
        except ValueError:
            return {"status": "ignored", "message": "Événement illisible"}
        if not event.type.startswith("checkout.session.") or not event.session_id:
            return {"status": "ignored", "message": f"Événement {event.type} ignoré"}

        res = await db.execute(
            select(TransactionMobileMoney).where(
                TransactionMobileMoney.provider_session_id == event.session_id,
                TransactionMobileMoney.operateur == "WAVE",
            )
        )
        txn = res.scalar_one_or_none()
        if txn is None or (
            event.client_reference and event.client_reference != txn.reference_externe
        ):
            logger.warning(
                "Webhook Wave pour une session inconnue : %s", event.session_id
            )
            return {"status": "ignored", "message": "Session inconnue"}

        etat = event.etat
        if event.currency and event.currency != "XOF":
            etat = EtatPaiement(etat.statut, etat.transaction_id, montant=None)
        return await self._appliquer_etat(db, txn, etat)

    async def handle_orange_money_notification(
        self, db: AsyncSession, raw_body: bytes
    ) -> dict[str, Any]:
        """Notification WebPay : `notif_token` obligatoire, puis confirmation opérateur.

        La notification Orange Money n'étant pas signée, elle ne fait jamais
        foi seule : l'état est redemandé à l'opérateur (`transactionstatus`)
        avant tout crédit.
        """
        try:
            notification = parse_orange_notification(raw_body)
        except ValueError as exc:
            raise WebhookNonAuthentifieError(
                "Notification Orange Money invalide"
            ) from exc

        res = await db.execute(
            select(TransactionMobileMoney).where(
                TransactionMobileMoney.provider_notif_token == notification.notif_token,
                TransactionMobileMoney.operateur == "ORANGE",
            )
        )
        txn = res.scalar_one_or_none()
        if txn is None or not hmac.compare_digest(
            txn.provider_notif_token or "", notification.notif_token
        ):
            raise WebhookNonAuthentifieError("notif_token Orange Money inconnu")

        try:
            etat = await get_provider("ORANGE").fetch_status(txn)
        except PaymentProviderError as exc:
            # Pas de crédit sans confirmation : la réconciliation reprendra.
            logger.warning("Confirmation Orange Money impossible : %s", exc)
            return {"status": "pending", "message": "Confirmation opérateur en attente"}

        if etat.statut is not notification.statut:
            logger.warning(
                "Notification Orange Money %s (%s) non confirmée : statut réel %s.",
                txn.reference_externe,
                notification.statut,
                etat.statut,
            )
        return await self._appliquer_etat(db, txn, etat)

    # ── Suivi & réconciliation ──

    async def get_transaction_status(
        self, db: AsyncSession, user_id: uuid.UUID, transaction_id: uuid.UUID
    ) -> TransactionMobileMoney | None:
        """Transaction de l'utilisateur (anti-IDOR : filtrée par propriétaire)."""
        res = await db.execute(
            select(TransactionMobileMoney).where(
                TransactionMobileMoney.id == transaction_id,
                TransactionMobileMoney.user_id == user_id,
            )
        )
        return res.scalar_one_or_none()

    async def reconcile_pending(
        self, db: AsyncSession, older_than_minutes: int = 15, limit: int = 100
    ) -> dict[str, int]:
        """Interroge l'opérateur pour les paiements restés `PENDING` (notification perdue)."""
        seuil = datetime.now(UTC).replace(tzinfo=None) - timedelta(
            minutes=older_than_minutes
        )
        res = await db.execute(
            select(TransactionMobileMoney)
            .where(
                TransactionMobileMoney.statut_paiement == "PENDING",
                TransactionMobileMoney.provider_session_id.is_not(None),
                TransactionMobileMoney.created_at <= seuil,
            )
            .order_by(TransactionMobileMoney.created_at)
            .limit(limit)
        )
        stats = {"verifiees": 0, "creditees": 0, "cloturees": 0, "erreurs": 0}
        for txn in res.scalars().all():
            stats["verifiees"] += 1
            try:
                etat = await get_provider(txn.operateur).fetch_status(txn)
            except (PaymentProviderError, ValueError) as exc:
                logger.warning("Réconciliation %s impossible : %s", txn.id, exc)
                stats["erreurs"] += 1
                continue
            resultat = await self._appliquer_etat(db, txn, etat)
            if resultat["status"] == "success":
                stats["creditees"] += 1
            elif resultat["status"] == "declined":
                stats["cloturees"] += 1
        return stats

    # ── Webhook générique (agrégateur, en-tête X-Signature) ──

    def verify_webhook_signature(
        self, payload_bytes: bytes, signature_header: str | None
    ) -> bool:
        """Vérifie la signature HMAC SHA-256 du webhook générique.

        La signature est **obligatoire** : un webhook sans en-tête ``X-Signature``
        est rejeté. Cela empêche un tiers d'appeler le webhook pour débloquer
        gratuitement un Pass premium.
        """
        if not signature_header:
            return False

        secret = settings.mobile_money_secret_key.encode("utf-8")
        expected_hash = hmac.new(secret, payload_bytes, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_hash, signature_header)

    async def process_webhook(
        self,
        db: AsyncSession,
        transaction_id: str,
        statut: str,
        montant: int | None = None,
    ) -> dict[str, Any]:
        """Webhook générique signé : débloque le compte si le montant est exact."""
        stmt = select(TransactionMobileMoney).where(
            TransactionMobileMoney.reference_externe == transaction_id
        )
        res = await db.execute(stmt)
        txn = res.scalar_one_or_none()

        if not txn:
            # Fallback par ID primaire UUID si recherché par ID direct
            try:
                uuid_obj = uuid.UUID(transaction_id)
                stmt2 = select(TransactionMobileMoney).where(
                    TransactionMobileMoney.id == uuid_obj
                )
                res2 = await db.execute(stmt2)
                txn = res2.scalar_one_or_none()
            except ValueError:
                pass

        if not txn:
            return {"status": "error", "message": "Transaction non trouvée"}

        statut_normalise = statut.upper()
        if statut_normalise in STATUTS_PAIEMENT_ABOUTIS:
            etat = EtatPaiement(StatutOperateur.SUCCES, montant=montant)
        elif statut_normalise == "EXPIRED":
            etat = EtatPaiement(StatutOperateur.EXPIRE)
        else:
            etat = EtatPaiement(StatutOperateur.ECHEC)
        return await self._appliquer_etat(db, txn, etat)


payment_service = PaymentService()
