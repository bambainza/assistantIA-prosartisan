"""Router Finance : dashboard, journal filtrable, remboursements, corrections
manuelles de statut et rapports périodiques sur les transactions Mobile Money.

Toutes les routes exigent la permission RBAC `transactions.read` (lecture) ou
`finance.write` (remboursement / correction de statut) — voir AGENTS.md §11.
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.middleware.auth import require_permission
from app.schemas.finance import (
    FinanceOverviewOut,
    TransactionListOut,
    TransactionRefundRequest,
    TransactionStatusAdjustRequest,
)
from app.services.audit_service import audit_service
from app.services.finance_service import finance_service

router = APIRouter(prefix="/api/admin/finance", tags=["Finance (Back-office)"])


@router.get("/overview", response_model=FinanceOverviewOut)
async def get_finance_overview(
    admin_id: uuid.UUID = Depends(require_permission("transactions.read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """KPIs du module Finance : revenu total/30j, taux de succès, répartitions."""
    return await finance_service.get_overview(db)


@router.get("/transactions", response_model=TransactionListOut)
async def get_finance_transactions(
    statut: str | None = None,
    operateur: str | None = None,
    type_achat: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    q: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    admin_id: uuid.UUID = Depends(require_permission("transactions.read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Journal des transactions Mobile Money, filtrable et paginé."""
    transactions, total = await finance_service.list_transactions(
        db,
        statut=statut,
        operateur=operateur,
        type_achat=type_achat,
        date_from=date_from,
        date_to=date_to,
        q=q,
        limit=limit,
        offset=offset,
    )
    return {"transactions": transactions, "total": total}


@router.get("/transactions/export")
async def export_finance_transactions(
    statut: str | None = None,
    operateur: str | None = None,
    type_achat: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    q: str | None = None,
    admin_id: uuid.UUID = Depends(require_permission("transactions.read")),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Exporte le journal filtré en CSV (jusqu'à 5000 lignes par export)."""
    transactions, _ = await finance_service.list_transactions(
        db,
        statut=statut,
        operateur=operateur,
        type_achat=type_achat,
        date_from=date_from,
        date_to=date_to,
        q=q,
        limit=5000,
        offset=0,
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "id",
            "artisan",
            "montant",
            "devise",
            "operateur",
            "statut",
            "type_achat",
            "reference_externe",
            "cree_le",
            "rembourse_le",
            "motif_remboursement",
        ]
    )
    for txn in transactions:
        writer.writerow(
            [
                str(txn["id"]),
                txn["artisan"],
                txn["montant"],
                txn["devise"],
                txn["operateur"],
                txn["statut_paiement"],
                txn["type_achat"],
                txn["reference_externe"] or "",
                txn["created_at"].isoformat() if txn["created_at"] else "",
                txn["refunded_at"].isoformat() if txn["refunded_at"] else "",
                txn["refund_reason"] or "",
            ]
        )

    buffer.seek(0)
    filename = (
        f"transactions_prosartisan_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.csv"
    )
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reports")
async def get_finance_reports(
    period: str = Query("day", pattern="^(day|week|month)$"),
    admin_id: uuid.UUID = Depends(require_permission("transactions.read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Revenu agrégé par jour, semaine ou mois (paiements aboutis uniquement)."""
    entries = await finance_service.get_report(db, period=period)
    return {"period": period, "entries": entries}


@router.post("/transactions/{transaction_id}/refund", response_model=None)
async def refund_transaction(
    transaction_id: uuid.UUID,
    payload: TransactionRefundRequest,
    request: Request,
    admin_id: uuid.UUID = Depends(require_permission("finance.write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Marque une transaction aboutie comme remboursée."""
    try:
        txn = await finance_service.refund_transaction(
            db, transaction_id, reason=payload.reason, admin_id=admin_id
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)
        ) from err

    await audit_service.log_action(
        db,
        actor_id=admin_id,
        action="transaction.refund",
        resource_type="transaction",
        resource_id=str(transaction_id),
        after={"reason": payload.reason, "montant": txn.montant},
        request=request,
    )
    await db.commit()
    return {
        "status": "success",
        "message": "Transaction remboursée avec succès.",
        "transaction_id": str(transaction_id),
    }


@router.post("/transactions/{transaction_id}/adjust-status", response_model=None)
async def adjust_transaction_status(
    transaction_id: uuid.UUID,
    payload: TransactionStatusAdjustRequest,
    request: Request,
    admin_id: uuid.UUID = Depends(require_permission("finance.write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Corrige manuellement le statut d'une transaction restée bloquée."""
    try:
        updated = await finance_service.adjust_transaction_status(
            db, transaction_id, new_status=payload.new_status, reason=payload.reason
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)
        ) from err

    await audit_service.log_action(
        db,
        actor_id=admin_id,
        action="transaction.status_adjust",
        resource_type="transaction",
        resource_id=str(transaction_id),
        after={"new_status": payload.new_status, "reason": payload.reason},
        request=request,
    )
    await db.commit()
    return {
        "status": "success",
        "message": f"Statut mis à jour : {updated.statut_paiement}.",
        "transaction_id": str(transaction_id),
    }
