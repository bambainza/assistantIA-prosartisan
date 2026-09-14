"""Service : Module Finance (back-office) — KPIs, journal filtrable, remboursements,
corrections manuelles de statut et rapports périodiques sur les transactions
Mobile Money.

L'agrégation par période (jour/semaine/mois) est faite côté Python plutôt
qu'en SQL (`date_trunc`, propre à PostgreSQL) : le projet garde un repli
SQLite en dev/CI (voir `app/db/session.py`), donc toute requête doit rester
portable entre les deux moteurs.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import TransactionMobileMoney
from app.models.user import User
from app.schemas.finance import STATUTS_AJUSTABLES

# Statuts opérateur considérés comme un paiement abouti (revenu réel).
STATUTS_ABOUTIS = {"ACCEPTED", "SUCCESS", "PAID"}


class FinanceService:
    """Lecture, remboursement et correction des transactions Mobile Money."""

    async def list_transactions(
        self,
        db: AsyncSession,
        *,
        statut: str | None = None,
        operateur: str | None = None,
        type_achat: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Journal filtré et paginé, jointure sur le nom de l'artisan."""
        conditions = []
        if statut is not None:
            conditions.append(TransactionMobileMoney.statut_paiement == statut)
        if operateur is not None:
            conditions.append(TransactionMobileMoney.operateur == operateur)
        if type_achat is not None:
            conditions.append(TransactionMobileMoney.type_achat == type_achat)
        if date_from is not None:
            conditions.append(TransactionMobileMoney.created_at >= date_from)
        if date_to is not None:
            conditions.append(TransactionMobileMoney.created_at <= date_to)
        if q:
            like = f"%{q}%"
            conditions.append(
                (TransactionMobileMoney.reference_externe.ilike(like))
                | (User.nom.ilike(like))
            )

        # Même jointure sur les deux requêtes (liste + comptage) pour que le
        # total corresponde exactement aux lignes réellement filtrées, sans
        # produit cartésien accidentel si le nom de l'artisan est référencé.
        stmt = select(TransactionMobileMoney, User.nom).outerjoin(
            User, TransactionMobileMoney.user_id == User.id
        )
        count_stmt = select(func.count(TransactionMobileMoney.id)).outerjoin(
            User, TransactionMobileMoney.user_id == User.id
        )
        for cond in conditions:
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)

        stmt = (
            stmt.order_by(TransactionMobileMoney.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        res = await db.execute(stmt)
        rows = res.all()
        total_res = await db.execute(count_stmt)
        total = total_res.scalar() or 0

        transactions = [
            {
                "id": txn.id,
                "user_id": txn.user_id,
                "artisan": nom or "Artisan inconnu",
                "montant": txn.montant,
                "devise": txn.devise,
                "operateur": txn.operateur,
                "statut_paiement": txn.statut_paiement,
                "type_achat": txn.type_achat,
                "reference_externe": txn.reference_externe,
                "created_at": txn.created_at,
                "refunded_at": txn.refunded_at,
                "refund_reason": txn.refund_reason,
            }
            for txn, nom in rows
        ]
        return transactions, total

    async def get_overview(self, db: AsyncSession) -> dict[str, Any]:
        """KPIs agrégés : revenu total, revenu 30j, taux de succès, répartitions."""
        stmt = select(
            TransactionMobileMoney.montant,
            TransactionMobileMoney.statut_paiement,
            TransactionMobileMoney.operateur,
            TransactionMobileMoney.created_at,
        )
        res = await db.execute(stmt)
        rows = res.all()

        since_30j = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)
        revenu_total = 0
        revenu_30j = 0
        revenu_rembourse_total = 0
        par_operateur: dict[str, int] = defaultdict(int)
        par_statut: dict[str, int] = defaultdict(int)
        nb_aboutis = 0

        for montant, statut, operateur, created_at in rows:
            par_statut[statut] += 1
            if statut in STATUTS_ABOUTIS:
                nb_aboutis += 1
                revenu_total += montant
                par_operateur[operateur] += montant
                if created_at and created_at >= since_30j:
                    revenu_30j += montant
            elif statut == "REFUNDED":
                revenu_rembourse_total += montant

        total = len(rows)
        taux_succes = (nb_aboutis / total * 100) if total else 0.0

        return {
            "revenu_total": revenu_total,
            "revenu_30j": revenu_30j,
            "revenu_rembourse_total": revenu_rembourse_total,
            "taux_succes_pct": round(taux_succes, 1),
            "total_transactions": total,
            "par_operateur": dict(par_operateur),
            "par_statut": dict(par_statut),
        }

    async def get_report(
        self, db: AsyncSession, *, period: str = "day"
    ) -> list[dict[str, Any]]:
        """Revenu agrégé par jour / semaine / mois (paiements aboutis uniquement)."""
        if period not in ("day", "week", "month"):
            period = "day"

        stmt = select(
            TransactionMobileMoney.montant, TransactionMobileMoney.created_at
        ).where(TransactionMobileMoney.statut_paiement.in_(STATUTS_ABOUTIS))
        res = await db.execute(stmt)
        rows = res.all()

        buckets: dict[str, dict[str, int]] = defaultdict(
            lambda: {"revenu": 0, "nb_transactions": 0}
        )
        for montant, created_at in rows:
            if created_at is None:
                continue
            if period == "day":
                key = created_at.strftime("%Y-%m-%d")
            elif period == "week":
                iso = created_at.isocalendar()
                key = f"{iso[0]}-S{iso[1]:02d}"
            else:
                key = created_at.strftime("%Y-%m")
            buckets[key]["revenu"] += montant
            buckets[key]["nb_transactions"] += 1

        return [
            {
                "periode": key,
                "revenu": val["revenu"],
                "nb_transactions": val["nb_transactions"],
            }
            for key, val in sorted(buckets.items())
        ]

    async def refund_transaction(
        self,
        db: AsyncSession,
        transaction_id: uuid.UUID,
        *,
        reason: str,
        admin_id: uuid.UUID,
    ) -> TransactionMobileMoney:
        """Marque une transaction aboutie comme remboursée.

        Raises:
            ValueError: transaction introuvable, ou statut non remboursable
                (déjà remboursée, ou jamais aboutie en premier lieu).
        """
        stmt = select(TransactionMobileMoney).where(
            TransactionMobileMoney.id == transaction_id
        )
        res = await db.execute(stmt)
        txn = res.scalar_one_or_none()
        if txn is None:
            raise ValueError("Transaction introuvable.")
        if txn.statut_paiement not in STATUTS_ABOUTIS:
            raise ValueError(
                f"Impossible de rembourser une transaction au statut "
                f"'{txn.statut_paiement}' (seuls les paiements aboutis le sont)."
            )

        txn.statut_paiement = "REFUNDED"
        txn.refunded_at = datetime.now(UTC).replace(tzinfo=None)
        txn.refund_reason = reason
        txn.refunded_by_admin_id = admin_id
        return txn

    async def adjust_transaction_status(
        self,
        db: AsyncSession,
        transaction_id: uuid.UUID,
        *,
        new_status: str,
        reason: str,
    ) -> TransactionMobileMoney:
        """Corrige manuellement le statut d'une transaction restée bloquée.

        Raises:
            ValueError: transaction introuvable, ou statut cible non autorisé
                (le remboursement passe par `refund_transaction`, jamais ici).
        """
        if new_status not in STATUTS_AJUSTABLES:
            raise ValueError(
                f"Statut '{new_status}' non autorisé pour un ajustement manuel."
            )

        stmt = select(TransactionMobileMoney).where(
            TransactionMobileMoney.id == transaction_id
        )
        res = await db.execute(stmt)
        txn = res.scalar_one_or_none()
        if txn is None:
            raise ValueError("Transaction introuvable.")

        txn.statut_paiement = new_status
        return txn


finance_service = FinanceService()
