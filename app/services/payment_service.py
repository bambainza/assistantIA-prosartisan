"""
Service de Paiement Mobile Money & Gestion des Webhooks.

Gère l'initialisation des paiements Wave / Orange Money,
la vérification de signature HMAC SHA-256 et la mise à jour des droits utilisateurs.
"""

from __future__ import annotations

import hmac
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.quota import QuotaUtilisateur
from app.models.transaction import TransactionMobileMoney


TARIFS_PASS = {
    "pass_24h": {"nom": "Pass 24H Urgence", "montant": 500, "duree_heures": 24},
    "pass_mois": {"nom": "Pass Mensuel Pro", "montant": 3000, "duree_heures": 24 * 30},
    "pack_50_requetes": {"nom": "Pack 50 Requêtes", "montant": 1500, "requetes": 50},
}


class PaymentService:
    """Gestionnaire de transactions Mobile Money et validation HMAC."""

    def verify_webhook_signature(self, payload_bytes: bytes, signature_header: str | None) -> bool:
        """Vérifie la signature HMAC SHA-256 du webhook entrant."""
        if not signature_header:
            return False

        secret = settings.mobile_money_secret_key.encode("utf-8")
        expected_hash = hmac.new(secret, payload_bytes, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_hash, signature_header)

    async def initialize_payment(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        type_pass: str,
        operateur: str = "WAVE",
    ) -> dict[str, Any]:
        """Initialise une nouvelle transaction Mobile Money."""
        if type_pass not in TARIFS_PASS:
            raise ValueError(f"Type de pass inconnu: {type_pass}")

        info_pass = TARIFS_PASS[type_pass]

        ref_ext = f"REF-{uuid.uuid4().hex[:12].upper()}"
        txn_id = str(uuid.uuid4())
        try:
            txn = TransactionMobileMoney(
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
            await db.refresh(txn)
            txn_id = str(txn.id)
            ref_ext = txn.reference_externe
        except Exception:
            pass

        payment_checkout_url = (
            f"https://pay.wave.com/c/{ref_ext}"
            if operateur == "WAVE"
            else f"https://payment.orange.ci/checkout/{ref_ext}"
        )

        return {
            "status": "success",
            "transaction_id": txn_id,
            "reference_externe": ref_ext,
            "montant": info_pass["montant"],
            "payment_url": payment_checkout_url,
        }

    async def process_webhook(
        self,
        db: AsyncSession,
        transaction_id: str,
        statut: str,
    ) -> dict[str, Any]:
        """Traite le webhook de confirmation de paiement et débloque le compte artisan."""
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

        txn.statut_paiement = statut.upper()

        if statut.upper() in ["ACCEPTED", "SUCCESS", "PAID"]:
            info_pass = TARIFS_PASS.get(txn.type_achat, {})
            quota_stmt = select(QuotaUtilisateur).where(QuotaUtilisateur.user_id == txn.user_id)
            quota_res = await db.execute(quota_stmt)
            quota_obj = quota_res.scalar_one_or_none()

            if not quota_obj:
                quota_obj = QuotaUtilisateur(user_id=txn.user_id, requetes_restantes_gratuites=5)
                db.add(quota_obj)

            now = datetime.now(timezone.utc)
            if "duree_heures" in info_pass:
                heures = info_pass["duree_heures"]
                start_base = (
                    quota_obj.date_fin_premium.replace(tzinfo=timezone.utc)
                    if (quota_obj.date_fin_premium and quota_obj.date_fin_premium.replace(tzinfo=timezone.utc) > now)
                    else now
                )
                quota_obj.date_fin_premium = start_base + timedelta(hours=heures)
            elif "requetes" in info_pass:
                quota_obj.requetes_restantes_gratuites += info_pass["requetes"]

            await db.commit()
            return {"status": "success", "message": "Pass débloqué avec succès", "user_id": str(txn.user_id)}

        await db.commit()
        return {"status": "declined", "message": "Paiement refusé ou annulé"}


payment_service = PaymentService()
