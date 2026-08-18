"""
Service de gestion des Quotas Freemium & Premium.

Supervise le nombre de questions quotidiennes gratuites (Redis / DB)
et vérifie si un abonnement Pass 24H ou Pass Mensuel est actif.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.quota import QuotaUtilisateur
from app.models.user import User


class QuotaService:
    """Service de vérification et décrémentation des quotas artisans."""

    async def get_user_quota_info(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Retourne le statut de quota d'un utilisateur."""
        try:
            stmt = select(QuotaUtilisateur).where(QuotaUtilisateur.user_id == user_id)
            res = await db.execute(stmt)
            quota_obj = res.scalar_one_or_none()

            if not quota_obj:
                # Création automatique du quota par défaut
                quota_obj = QuotaUtilisateur(
                    user_id=user_id,
                    requetes_restantes_gratuites=settings.max_questions_gratuites_par_jour,
                )
                db.add(quota_obj)
                await db.commit()

            now = datetime.now(timezone.utc)
            is_premium = (
                quota_obj.date_fin_premium is not None
                and quota_obj.date_fin_premium.replace(tzinfo=timezone.utc) > now
            )

            return {
                "statut": "premium" if is_premium else "freemium",
                "restantes": 999999 if is_premium else quota_obj.requetes_restantes_gratuites,
                "date_fin_premium": quota_obj.date_fin_premium.isoformat() if quota_obj.date_fin_premium else None,
                "is_allowed": is_premium or quota_obj.requetes_restantes_gratuites > 0,
            }
        except Exception:
            # Fallback local sans base de données PostgreSQL
            return {
                "statut": "freemium",
                "restantes": 5,
                "date_fin_premium": None,
                "is_allowed": True,
            }

    async def consume_quota(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> bool:
        """Décrémente de 1 le quota gratuit si l'utilisateur n'est pas premium."""
        try:
            quota_info = await self.get_user_quota_info(db, user_id)
            if not quota_info["is_allowed"]:
                return False

            if quota_info["statut"] == "premium":
                return True

            stmt = select(QuotaUtilisateur).where(QuotaUtilisateur.user_id == user_id)
            res = await db.execute(stmt)
            quota_obj = res.scalar_one_or_none()

            if quota_obj and quota_obj.requetes_restantes_gratuites > 0:
                quota_obj.requetes_restantes_gratuites -= 1
                await db.commit()
                return True

            return True
        except Exception:
            return True


quota_service = QuotaService()
