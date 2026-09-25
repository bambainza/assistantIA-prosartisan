"""
Router Admin — Supervision métier : devis générés et usage des calculateurs.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.middleware.auth import require_permission
from app.models.quote import Quote
from app.services.cache_service import cache_service

router = APIRouter()


@router.get("/quotes", status_code=status.HTTP_200_OK)
async def admin_list_quotes(
    limit: int = 50,
    offset: int = 0,
    status_filter: str | None = None,
    admin_id: uuid.UUID = Depends(require_permission("quotes.read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Supervision des devis et factures pro-forma générés par les artisans.

    Retourne la liste paginée ainsi que les agrégations financières globales
    (volume total, montant HT et TTC, taux de conversion).
    """
    stmt = select(Quote).order_by(Quote.created_at.desc())
    if status_filter:
        stmt = stmt.where(Quote.statut == status_filter)

    total_count_stmt = select(func.count(Quote.id))
    if status_filter:
        total_count_stmt = total_count_stmt.where(Quote.statut == status_filter)

    total_res = await db.execute(total_count_stmt)
    total_count = total_res.scalar_one() or 0

    quotes_res = await db.execute(stmt.offset(offset).limit(limit))
    quotes = quotes_res.scalars().all()

    # Agrégations financières globales
    agg_stmt = select(
        func.count(Quote.id),
        func.coalesce(func.sum(Quote.total_ht), 0.0),
        func.coalesce(func.sum(Quote.total_ttc), 0.0),
    )
    agg_res = await db.execute(agg_stmt)
    agg_row = agg_res.one()

    return {
        "total": total_count,
        "offset": offset,
        "limit": limit,
        "stats": {
            "total_quotes_count": agg_row[0],
            "total_montant_ht": float(agg_row[1]),
            "total_montant_ttc": float(agg_row[2]),
        },
        "quotes": [
            {
                "id": str(q.id),
                "numero": q.numero,
                "user_id": str(q.user_id),
                "titre": q.titre,
                "client_nom": q.client_nom,
                "client_telephone": q.client_telephone,
                "statut": q.statut,
                "total_ht": q.total_ht,
                "total_ttc": q.total_ttc,
                "created_at": q.created_at.isoformat() if q.created_at else None,
            }
            for q in quotes
        ],
    }


@router.get("/calculators/stats", status_code=status.HTTP_200_OK)
async def admin_get_calculators_stats(
    admin_id: uuid.UUID = Depends(require_permission("audit.read")),
) -> dict[str, Any]:
    """Statistiques d'utilisation des calculateurs métiers déterministes.

    Permet de suivre les moteurs de calcul les plus sollicités sur le terrain.
    """
    tools = [
        "calculer_dosage_beton_mortier",
        "calculer_section_cable_nfc15100",
        "calculer_pente_evacuation_dtu60",
        "calculer_surface_carrelage_colle",
        "calculer_bilan_thermique_climatisation",
    ]

    stats: dict[str, int] = {}
    total_calls = 0
    for tool in tools:
        count_str = await cache_service.get(f"prosartisan:calculator:{tool}:count")
        count = int(count_str) if count_str and count_str.isdigit() else 0
        stats[tool] = count
        total_calls += count

    return {
        "total_calculator_calls": total_calls,
        "by_tool": stats,
        "available_tools": len(tools),
    }
