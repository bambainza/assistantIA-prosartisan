"""
Service de gestion des Quotas Freemium & Premium.

Trois sources de droits, vérifiées dans cet ordre :

1. **Pass premium actif** (Pass 24H / Mensuel) : `date_fin_premium` en base.
2. **Quota gratuit journalier** (`MAX_QUESTIONS_GRATUITES_PAR_JOUR`) : compteur
   Redis atomique par jour UTC (= heure d'Abidjan, GMT sans heure d'été) et par
   identité — l'utilisateur du JWT, ou l'IP cliente pour un visiteur non
   connecté (un quota commun à tous les anonymes serait épuisé en 5 questions
   pour tout le service). La clé expire seule : aucune tâche de remise à zéro.
3. **Crédits achetés** (Pack 50, forfaits CREDITS) : `credits_requetes` en
   base, décrémenté par un `UPDATE ... WHERE credits_requetes > 0` atomique.

Redis étant la source de vérité du quota journalier (AGENTS.md — état partagé
entre workers), son indisponibilité en production lève `QuotaIndisponibleError`
(HTTP 503) au lieu d'accorder ou de refuser des questions à l'aveugle.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.quota import QuotaUtilisateur
from app.services.cache_service import cache_service

logger = logging.getLogger(__name__)

# Une clé journalière vit un peu plus d'un jour pour couvrir la fin de journée.
_DAILY_KEY_TTL_SECONDS = 2 * 86400

# Valeur conventionnelle de `restantes` pour un Pass illimité (contrat API existant).
ILLIMITE = 999999


class QuotaIndisponibleError(RuntimeError):
    """Le compteur partagé du quota journalier (Redis) est injoignable."""


def identite_quota(user_id: uuid.UUID | None, client_ip: str | None) -> str:
    """Identité de comptage : l'utilisateur connecté, sinon l'IP (hachée) du visiteur."""
    if user_id is not None:
        return f"user:{user_id}"
    ip_hash = hashlib.sha256((client_ip or "unknown").encode("utf-8")).hexdigest()
    return f"anon:{ip_hash[:32]}"


def cle_quota_journalier(identite: str, jour: str | None = None) -> str:
    jour = jour or datetime.now(UTC).strftime("%Y-%m-%d")
    return f"prosartisan:quota:jour:{jour}:{identite}"


class QuotaService:
    """Service de vérification et décrémentation des quotas artisans."""

    async def _charger_quota(
        self, db: AsyncSession, user_id: uuid.UUID
    ) -> QuotaUtilisateur | None:
        stmt = select(QuotaUtilisateur).where(QuotaUtilisateur.user_id == user_id)
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    def _fin_premium_active(quota_obj: QuotaUtilisateur | None) -> datetime | None:
        if quota_obj is None or quota_obj.date_fin_premium is None:
            return None
        fin = quota_obj.date_fin_premium.replace(tzinfo=UTC)
        return fin if fin > datetime.now(UTC) else None

    async def questions_gratuites_utilisees(self, identite: str) -> int:
        """Nombre de questions gratuites déjà consommées aujourd'hui (lecture seule)."""
        try:
            valeur = await cache_service.get(cle_quota_journalier(identite))
        except RuntimeError as exc:
            raise QuotaIndisponibleError(str(exc)) from exc
        return int(valeur) if valeur else 0

    async def reinitialiser_quota_journalier(self, user_id: uuid.UUID) -> None:
        """Rend à l'utilisateur son quota gratuit du jour (action admin)."""
        try:
            await cache_service.delete(
                cle_quota_journalier(identite_quota(user_id, None))
            )
        except RuntimeError as exc:
            raise QuotaIndisponibleError(str(exc)) from exc

    async def get_user_quota_info(
        self,
        db: AsyncSession,
        user_id: uuid.UUID | None,
        client_ip: str | None = None,
    ) -> dict[str, Any]:
        """Retourne le statut de quota d'un utilisateur (ou d'un visiteur anonyme)."""
        quota_obj = await self._charger_quota(db, user_id) if user_id else None
        fin_premium = self._fin_premium_active(quota_obj)

        if fin_premium is not None:
            return {
                "statut": "premium",
                "restantes": ILLIMITE,
                "gratuites_restantes_jour": settings.max_questions_gratuites_par_jour,
                "credits": quota_obj.credits_requetes if quota_obj else 0,
                "date_fin_premium": fin_premium.isoformat(),
                "is_allowed": True,
            }

        utilisees = await self.questions_gratuites_utilisees(
            identite_quota(user_id, client_ip)
        )
        gratuites = max(0, settings.max_questions_gratuites_par_jour - utilisees)
        credits = quota_obj.credits_requetes if quota_obj else 0
        return {
            "statut": "freemium",
            "restantes": gratuites + credits,
            "gratuites_restantes_jour": gratuites,
            "credits": credits,
            "date_fin_premium": None,
            "is_allowed": gratuites + credits > 0,
        }

    async def _consommer_credit(self, db: AsyncSession, user_id: uuid.UUID) -> bool:
        """Décrémente atomiquement un crédit acheté ; False si aucun crédit restant."""
        stmt = (
            update(QuotaUtilisateur)
            .where(
                QuotaUtilisateur.user_id == user_id,
                QuotaUtilisateur.credits_requetes > 0,
            )
            .values(credits_requetes=QuotaUtilisateur.credits_requetes - 1)
        )
        res = await db.execute(stmt)
        await db.commit()
        return res.rowcount == 1

    async def consume_quota(
        self,
        db: AsyncSession,
        user_id: uuid.UUID | None,
        client_ip: str | None = None,
    ) -> bool:
        """Consomme une question : Pass premium, puis quota du jour, puis crédits achetés.

        Retourne False si aucun droit ne reste (HTTP 402 côté router). Lève
        `QuotaIndisponibleError` si le compteur partagé est injoignable.
        """
        if user_id is not None:
            quota_obj = await self._charger_quota(db, user_id)
            if self._fin_premium_active(quota_obj) is not None:
                return True

        cle = cle_quota_journalier(identite_quota(user_id, client_ip))
        try:
            # INCR atomique : deux requêtes simultanées ne peuvent pas obtenir
            # la même "dernière" question gratuite.
            utilisees = await cache_service.increment(cle, _DAILY_KEY_TTL_SECONDS)
        except RuntimeError as exc:
            logger.error("Compteur de quota indisponible (%s).", exc)
            raise QuotaIndisponibleError(str(exc)) from exc

        if utilisees <= settings.max_questions_gratuites_par_jour:
            return True

        if user_id is None:
            return False
        return await self._consommer_credit(db, user_id)

    async def restituer_quota(
        self,
        db: AsyncSession,
        user_id: uuid.UUID | None,
        client_ip: str | None = None,
    ) -> None:
        """Rend la question consommée quand la réponse n'a pas pu être produite.

        Appelé si le fournisseur IA (ou la transcription vocale) échoue après
        `consume_quota` : l'artisan ne doit pas perdre une question pour une
        panne qui n'est pas de son fait. Pass premium : rien à rendre. Sinon le
        compteur du jour est décrémenté ; si la question avait dépassé le quota
        gratuit, c'est un crédit acheté qui avait été pris et il est recrédité.
        Jamais bloquant : un échec est journalisé, la réponse d'erreur part.
        """
        try:
            if user_id is not None:
                quota_obj = await self._charger_quota(db, user_id)
                if self._fin_premium_active(quota_obj) is not None:
                    return

            cle = cle_quota_journalier(identite_quota(user_id, client_ip))
            restant = await cache_service.increment(cle, _DAILY_KEY_TTL_SECONDS, -1)
            if restant < 0:
                # Compteur expiré entre-temps (changement de jour) : rien à rendre.
                await cache_service.increment(cle, _DAILY_KEY_TTL_SECONDS, 1)
                return
            if restant + 1 > settings.max_questions_gratuites_par_jour and user_id:
                await db.execute(
                    update(QuotaUtilisateur)
                    .where(QuotaUtilisateur.user_id == user_id)
                    .values(credits_requetes=QuotaUtilisateur.credits_requetes + 1)
                )
                await db.commit()
        except Exception:
            logger.exception("Restitution de quota impossible (user=%s).", user_id)


quota_service = QuotaService()
