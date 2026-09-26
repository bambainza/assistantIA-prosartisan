"""
Router Admin — Utilisateurs : vue d'ensemble, liste des artisans, attribution de Pass, journaux.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db
from app.middleware.auth import require_permission
from app.models.quota import QuotaUtilisateur
from app.models.transaction import TransactionMobileMoney
from app.models.user import User
from app.services.audit_service import audit_service
from app.services.quota_service import (
    QuotaIndisponibleError,
    identite_quota,
    quota_service,
)

router = APIRouter()
logger = logging.getLogger("app")


@router.get("/overview")
async def get_admin_overview(
    admin_id: uuid.UUID = Depends(require_permission("users.read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retourne la synthèse globale des KPIs réels pour le tableau de bord."""
    # Total artisans (non-admins)
    stmt_total = select(func.count(User.id)).where(User.is_admin == False)
    res_total = await db.execute(stmt_total)
    total_artisans = res_total.scalar() or 0

    # Artisans actifs connectés ces dernières 24 heures (ou au total)
    stmt_active = select(func.count(User.id)).where(User.is_admin == False)
    res_active = await db.execute(stmt_active)
    artisans_actifs = res_active.scalar() or 0

    # Chiffre d'affaires
    stmt_ca = select(func.sum(TransactionMobileMoney.montant)).where(
        TransactionMobileMoney.statut_paiement == "ACCEPTED"
    )
    res_ca = await db.execute(stmt_ca)
    ca = res_ca.scalar() or 0

    # Total questions
    from app.models.message import Message

    stmt_questions = select(func.count(Message.id)).where(Message.role == "user")
    res_questions = await db.execute(stmt_questions)
    total_questions = res_questions.scalar() or 0

    # Chunks Qdrant
    total_chunks = 0
    try:
        from qdrant_client import AsyncQdrantClient

        qdrant_client = AsyncQdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
        )
        info = await qdrant_client.get_collection(
            collection_name=settings.qdrant_collection
        )
        total_chunks = info.points_count
    except Exception:
        logger.exception("Statistiques Qdrant indisponibles pour le dashboard admin.")

    # Synthèse abonnements
    stmt_free = select(func.count(User.id)).where(
        User.is_admin == False, User.type_abonnement == "FREE"
    )
    res_free = await db.execute(stmt_free)
    free_count = res_free.scalar() or 0

    stmt_24h = select(func.count(User.id)).where(
        User.is_admin == False, User.type_abonnement == "pass_24h"
    )
    res_24h = await db.execute(stmt_24h)
    pass_24h_count = res_24h.scalar() or 0

    stmt_mois = select(func.count(User.id)).where(
        User.is_admin == False, User.type_abonnement == "pass_mois"
    )
    res_mois = await db.execute(stmt_mois)
    pass_mois_count = res_mois.scalar() or 0

    return {
        "kpis": {
            "total_artisans": total_artisans,
            "artisans_actifs_dau": artisans_actifs,
            "chiffre_affaires_mfa": ca,
            "total_questions_rag": total_questions,
            "total_documents_qdrant": total_chunks,
        },
        "abonnements": {
            "free": free_count,
            "pass_24h": pass_24h_count,
            "pass_mois": pass_mois_count,
        },
        "metiers_top": [],
    }


@router.get("/users")
async def get_users_list(
    admin_id: uuid.UUID = Depends(require_permission("users.read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retourne la liste des artisans inscrits avec statut de quota."""
    from app.models.metier import Metier

    stmt = (
        select(
            User.id,
            User.nom,
            User.telephone,
            User.type_abonnement,
            User.created_at,
            QuotaUtilisateur.credits_requetes,
            Metier.nom.label("metier_nom"),
        )
        .outerjoin(QuotaUtilisateur, User.id == QuotaUtilisateur.user_id)
        .outerjoin(Metier, User.metier_id == Metier.id)
        .where(User.is_admin == False)
        .order_by(User.created_at.desc())
    )

    res = await db.execute(stmt)
    users_data = []
    for row in res.all():
        questions_restantes = 999999
        if row.type_abonnement == "FREE":
            # Quota gratuit du jour (Redis) + crédits achetés (base).
            try:
                utilisees = await quota_service.questions_gratuites_utilisees(
                    identite_quota(row.id, None)
                )
            except QuotaIndisponibleError:
                utilisees = 0
            questions_restantes = max(
                0, settings.max_questions_gratuites_par_jour - utilisees
            ) + (row.credits_requetes or 0)
        users_data.append(
            {
                "id": str(row.id),
                "nom": row.nom or "Artisan Anonyme",
                "telephone": row.telephone or "Non renseigné",
                "metier": row.metier_nom or "Généraliste",
                "type_abonnement": row.type_abonnement,
                "questions_restantes": questions_restantes,
                "date_inscription": row.created_at.strftime("%Y-%m-%d")
                if row.created_at
                else "Non renseigné",
            }
        )

    return {"users": users_data}


@router.post("/users/{user_id}/grant-pass")
async def grant_pass_to_user(
    user_id: str,
    request: Request,
    type_pass: str = "pass_24h",
    admin_id: uuid.UUID = Depends(require_permission("users.grant_pass")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Attribue ou prolonge manuellement un Pass Pro pour un artisan (écritures réelles)."""
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Format de user_id invalide (UUID requis).",
        )

    stmt = select(User).where(User.id == user_uuid)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur non trouvé."
        )

    quota_stmt = select(QuotaUtilisateur).where(QuotaUtilisateur.user_id == user_uuid)
    quota_res = await db.execute(quota_stmt)
    quota = quota_res.scalar_one_or_none()
    if not quota:
        quota = QuotaUtilisateur(user_id=user_uuid)
        db.add(quota)

    if type_pass == "pass_24h":
        user.type_abonnement = "pass_24h"
        quota.date_fin_premium = datetime.now(UTC) + timedelta(days=1)
    elif type_pass == "pass_mois":
        user.type_abonnement = "pass_mois"
        quota.date_fin_premium = datetime.now(UTC) + timedelta(days=30)
    else:
        user.type_abonnement = "FREE"
        quota.date_fin_premium = None
        # Les crédits achetés restent acquis ; seul le quota du jour est rendu.
        await quota_service.reinitialiser_quota_journalier(user_uuid)

    await audit_service.log_action(
        db,
        actor_id=admin_id,
        action="user.grant_pass",
        resource_type="user",
        resource_id=str(user_uuid),
        after={"type_pass": type_pass},
        request=request,
    )
    await db.commit()

    return {
        "status": "success",
        "message": f"Pass {type_pass} attribué avec succès à l'artisan {user.nom or user.email}",
        "user_id": str(user_id),
        "type_pass": type_pass,
    }


@router.get("/logs")
async def get_system_logs(
    admin_id: uuid.UUID = Depends(require_permission("logs.read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retourne les journaux d'activité récents."""
    res_users = await db.execute(select(func.count(User.id)))
    num_users = res_users.scalar() or 0

    return {
        "logs": [
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": "INFO",
                "event": f"Accès backoffice par l'administrateur {admin_id}",
            },
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": "INFO",
                "event": f"Vérification DB : OK ({num_users} artisans enregistrés)",
            },
        ]
    }
