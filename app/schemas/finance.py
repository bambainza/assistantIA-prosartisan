"""Schémas Pydantic pour le module Finance (back-office admin)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# Statuts qu'un admin peut assigner manuellement pour corriger une
# transaction restée bloquée (ex: webhook opérateur jamais reçu). Le
# remboursement passe par son propre endpoint dédié, jamais par celui-ci —
# une seule voie pour marquer une transaction "REFUNDED".
STATUTS_AJUSTABLES = {"PENDING", "ACCEPTED", "FAILED"}


class TransactionOut(BaseModel):
    """Une transaction Mobile Money, telle qu'exposée au back-office."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    artisan: str | None = None
    montant: int
    devise: str
    operateur: str
    statut_paiement: str
    type_achat: str
    reference_externe: str | None = None
    created_at: datetime
    refunded_at: datetime | None = None
    refund_reason: str | None = None


class TransactionListOut(BaseModel):
    """Page de résultats du journal des transactions, avec le total filtré."""

    transactions: list[TransactionOut]
    total: int


class TransactionRefundRequest(BaseModel):
    """Marque une transaction comme remboursée."""

    reason: str = Field(..., min_length=3, max_length=255)


class TransactionStatusAdjustRequest(BaseModel):
    """Corrige manuellement le statut d'une transaction bloquée."""

    new_status: str = Field(...)
    reason: str = Field(..., min_length=3, max_length=255)


class FinanceOverviewOut(BaseModel):
    """Indicateurs clés du module Finance."""

    revenu_total: int
    revenu_30j: int
    revenu_rembourse_total: int
    taux_succes_pct: float
    total_transactions: int
    par_operateur: dict[str, int]
    par_statut: dict[str, int]


class FinanceReportEntry(BaseModel):
    """Une ligne agrégée du rapport périodique (jour/semaine/mois)."""

    periode: str
    revenu: int
    nb_transactions: int
