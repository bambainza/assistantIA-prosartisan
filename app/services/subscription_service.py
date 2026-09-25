"""Service métier : Gestion du catalogue des packages et du cycle de vie des abonnements artisans."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metier import Metier
from app.models.package import Package
from app.models.quota import QuotaUtilisateur
from app.models.subscription import UserSubscription
from app.models.user import User
from app.schemas.package import (
    PackageCreate,
    PackageUpdate,
    SubscriptionAssignRequest,
)


class SubscriptionService:
    """Gestionnaire des packages commerciaux et des souscriptions utilisateurs."""

    async def list_packages(
        self, db: AsyncSession, only_active: bool = False
    ) -> list[dict[str, Any]]:
        """Liste tous les packages avec le nombre d'abonnés actifs pour chacun."""
        stmt = select(Package).order_by(Package.prix.asc())
        if only_active:
            stmt = stmt.where(Package.est_actif == True)
        res = await db.execute(stmt)
        packages = res.scalars().all()

        now = datetime.now(UTC).replace(tzinfo=None)
        result = []
        for pkg in packages:
            # Compter les souscriptions actives
            count_stmt = select(func.count(UserSubscription.id)).where(
                UserSubscription.package_id == pkg.id,
                UserSubscription.statut == "ACTIVE",
                or_(
                    UserSubscription.date_fin.is_(None),
                    UserSubscription.date_fin > now,
                ),
            )
            count_res = await db.execute(count_stmt)
            active_count = count_res.scalar() or 0

            result.append(
                {
                    "id": pkg.id,
                    "code": pkg.code,
                    "nom": pkg.nom,
                    "description": pkg.description,
                    "prix": pkg.prix,
                    "devise": pkg.devise,
                    "type_package": pkg.type_package,
                    "duree_jours": pkg.duree_jours,
                    "quota_requetes": pkg.quota_requetes,
                    "auto_renouvelable": pkg.auto_renouvelable,
                    "est_actif": pkg.est_actif,
                    "is_active": pkg.est_actif,
                    "fonctionnalites": pkg.fonctionnalites or [],
                    "features": pkg.fonctionnalites or [],
                    "created_at": pkg.created_at,
                    "updated_at": pkg.updated_at,
                    "abonnements_actifs_count": active_count,
                }
            )
        return result

    async def get_package_by_id_or_code(
        self,
        db: AsyncSession,
        package_id: uuid.UUID | None = None,
        code: str | None = None,
    ) -> Package | None:
        """Retrouve une formule par son identifiant unique ou son slug/code."""
        if package_id:
            stmt = select(Package).where(Package.id == package_id)
            res = await db.execute(stmt)
            return res.scalar_one_or_none()
        if code:
            stmt = select(Package).where(Package.code == code)
            res = await db.execute(stmt)
            return res.scalar_one_or_none()
        return None

    async def create_package(self, db: AsyncSession, payload: PackageCreate) -> Package:
        """Crée une nouvelle offre commerciale dans le catalogue."""
        existing = await self.get_package_by_id_or_code(db, code=payload.code)
        if existing:
            raise ValueError(f"Un package avec le code '{payload.code}' existe déjà.")

        pkg = Package(
            id=uuid.uuid4(),
            code=payload.code,
            nom=payload.nom,
            description=payload.description,
            prix=payload.prix,
            devise=payload.devise,
            type_package=payload.type_package,
            duree_jours=payload.duree_jours,
            quota_requetes=payload.quota_requetes,
            auto_renouvelable=payload.auto_renouvelable,
            est_actif=payload.est_actif,
            fonctionnalites=payload.fonctionnalites or [],
        )
        db.add(pkg)
        await db.commit()
        await db.refresh(pkg)
        return pkg

    async def update_package(
        self, db: AsyncSession, package_id: uuid.UUID, payload: PackageUpdate
    ) -> Package:
        """Met à jour les caractéristiques d'une offre commerciale."""
        pkg = await self.get_package_by_id_or_code(db, package_id=package_id)
        if not pkg:
            raise ValueError("Package introuvable.")

        if payload.nom is not None:
            pkg.nom = payload.nom
        if payload.description is not None:
            pkg.description = payload.description
        if payload.prix is not None:
            pkg.prix = payload.prix
        if payload.type_package is not None:
            pkg.type_package = payload.type_package
        if payload.duree_jours is not None:
            pkg.duree_jours = payload.duree_jours
        if payload.quota_requetes is not None:
            pkg.quota_requetes = payload.quota_requetes
        if payload.auto_renouvelable is not None:
            pkg.auto_renouvelable = payload.auto_renouvelable
        if payload.est_actif is not None:
            pkg.est_actif = payload.est_actif
        if payload.fonctionnalites is not None:
            pkg.fonctionnalites = payload.fonctionnalites

        await db.commit()
        await db.refresh(pkg)
        return pkg

    async def toggle_package(
        self, db: AsyncSession, package_id: uuid.UUID, active: bool | None = None
    ) -> Package:
        """Active ou désactive une formule dans le catalogue."""
        pkg = await self.get_package_by_id_or_code(db, package_id=package_id)
        if not pkg:
            raise ValueError("Package introuvable.")
        if active is not None:
            pkg.est_actif = active
        else:
            pkg.est_actif = not pkg.est_actif
        await db.commit()
        await db.refresh(pkg)
        return pkg

    async def delete_package(
        self, db: AsyncSession, package_id: uuid.UUID, force: bool = False
    ) -> dict[str, Any]:
        """Supprime définitivement un package du catalogue.

        Par sécurité, si force=False, vérifie qu'aucun abonnement actif n'utilise ce package.
        """
        pkg = await self.get_package_by_id_or_code(db, package_id=package_id)
        if not pkg:
            raise ValueError("Package introuvable.")

        now = datetime.now(UTC).replace(tzinfo=None)
        count_stmt = select(func.count(UserSubscription.id)).where(
            UserSubscription.package_id == pkg.id,
            UserSubscription.statut == "ACTIVE",
            or_(
                UserSubscription.date_fin.is_(None),
                UserSubscription.date_fin > now,
            ),
        )
        count_res = await db.execute(count_stmt)
        active_count = count_res.scalar() or 0

        if active_count > 0 and not force:
            raise ValueError(
                f"Impossible de supprimer le package '{pkg.nom}' car il compte actuellement {active_count} abonnement(s) actif(s). "
                "Veuillez plutôt le désactiver pour bloquer les nouvelles souscriptions sans impacter les artisans en cours."
            )

        nom = pkg.nom
        await db.delete(pkg)
        await db.commit()

        return {
            "status": "success",
            "message": f"Package '{nom}' supprimé avec succès du catalogue.",
            "package_id": str(package_id),
            "nom": nom,
            "active_subscriptions_affected": active_count,
        }

    async def list_subscriptions(
        self,
        db: AsyncSession,
        status_filter: str | None = None,
        package_code: str | None = None,
        query: str | None = None,
    ) -> list[dict[str, Any]]:
        """Liste l'ensemble des inscrits et souscriptions avec filtres avancés."""
        now = datetime.now(UTC).replace(tzinfo=None)

        stmt = (
            select(
                UserSubscription,
                User,
                Package,
                Metier.nom.label("metier_nom"),
            )
            .join(User, UserSubscription.user_id == User.id)
            .join(Package, UserSubscription.package_id == Package.id)
            .outerjoin(Metier, User.metier_id == Metier.id)
            .order_by(UserSubscription.created_at.desc())
        )

        if package_code and package_code != "ALL":
            stmt = stmt.where(Package.code == package_code)

        if query:
            pattern = f"%{query.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(User.nom).like(pattern),
                    func.lower(User.email).like(pattern),
                    User.telephone.like(f"%{query.strip()}%"),
                )
            )

        res = await db.execute(stmt)
        rows = res.all()

        results = []
        for sub, user, pkg, metier_nom in rows:
            # Vérifier expiration automatique
            is_active = sub.est_actif
            current_status = sub.statut
            if sub.statut == "ACTIVE" and sub.date_fin and sub.date_fin < now:
                current_status = "EXPIRED"
                is_active = False

            if status_filter and status_filter != "ALL":
                if status_filter == "ACTIVE" and not is_active:
                    continue
                if status_filter == "EXPIRED" and is_active:
                    continue

            results.append(
                {
                    "id": sub.id,
                    "user_id": user.id,
                    "user_nom": user.nom or "Artisan Anonyme",
                    "user_telephone": user.telephone or "Non renseigné",
                    "user_email": user.email,
                    "user_metier": metier_nom or "Généraliste",
                    "package_id": pkg.id,
                    "package_code": pkg.code,
                    "package_nom": pkg.nom,
                    "package_prix": pkg.prix,
                    "package_type": pkg.type_package,
                    "statut": current_status,
                    "date_debut": sub.date_debut,
                    "date_fin": sub.date_fin,
                    "jours_restants": sub.jours_restants,
                    "quota_initial": sub.quota_initial,
                    "quota_consomme": sub.quota_consomme,
                    "quota_restant": sub.quota_restant,
                    "renouvellement_auto": sub.renouvellement_auto,
                    "est_actif": is_active,
                }
            )
        return results

    async def assign_subscription(
        self, db: AsyncSession, payload: SubscriptionAssignRequest
    ) -> UserSubscription:
        """Assigne ou renouvelle manuellement un abonnement pour un artisan."""
        # 1. Vérifier utilisateur
        user_stmt = select(User).where(User.id == payload.user_id)
        user_res = await db.execute(user_stmt)
        user = user_res.scalar_one_or_none()
        if not user:
            raise ValueError(f"Utilisateur introuvable pour ID : {payload.user_id}")

        # 2. Vérifier package
        pkg = await self.get_package_by_id_or_code(
            db, package_id=payload.package_id, code=payload.package_code
        )
        if not pkg:
            raise ValueError("Package introuvable.")

        # 3. Calcul de durée et quotas
        now = datetime.now(UTC).replace(tzinfo=None)
        duree_jours = (
            payload.duree_jours if payload.duree_jours is not None else pkg.duree_jours
        )
        date_fin = (now + timedelta(days=duree_jours)) if duree_jours else None

        quota_initial = (
            payload.quota_initial
            if payload.quota_initial is not None
            else pkg.quota_requetes
        )

        # 4. Désactiver les anciens abonnements actifs
        old_subs_stmt = select(UserSubscription).where(
            UserSubscription.user_id == user.id,
            UserSubscription.statut == "ACTIVE",
        )
        old_res = await db.execute(old_subs_stmt)
        for old_sub in old_res.scalars().all():
            old_sub.statut = "EXPIRED"

        # 5. Créer la nouvelle souscription
        sub = UserSubscription(
            id=uuid.uuid4(),
            user_id=user.id,
            package_id=pkg.id,
            statut="ACTIVE",
            date_debut=now,
            date_fin=date_fin,
            quota_initial=quota_initial,
            quota_consomme=0,
            renouvellement_auto=payload.renouvellement_auto,
        )
        db.add(sub)

        # 6. Synchroniser User et QuotaUtilisateur
        user.type_abonnement = pkg.code

        quota_stmt = select(QuotaUtilisateur).where(QuotaUtilisateur.user_id == user.id)
        q_res = await db.execute(quota_stmt)
        quota = q_res.scalar_one_or_none()
        if not quota:
            quota = QuotaUtilisateur(user_id=user.id)
            db.add(quota)

        if date_fin:
            quota.date_fin_premium = date_fin
        else:
            quota.date_fin_premium = None

        if quota_initial is not None and pkg.type_package == "CREDITS":
            quota.credits_requetes = quota_initial

        await db.commit()
        await db.refresh(sub)
        return sub

    async def extend_subscription(
        self, db: AsyncSession, subscription_id: uuid.UUID, additional_days: int
    ) -> UserSubscription:
        """Prolonge un abonnement existant de X jours."""
        stmt = select(UserSubscription).where(UserSubscription.id == subscription_id)
        res = await db.execute(stmt)
        sub = res.scalar_one_or_none()
        if not sub:
            raise ValueError("Abonnement introuvable.")

        now = datetime.now(UTC).replace(tzinfo=None)
        sub_end = (
            sub.date_fin.replace(tzinfo=None)
            if (sub.date_fin and sub.date_fin.tzinfo)
            else sub.date_fin
        )
        base_date = sub_end if (sub_end and sub_end > now) else now
        sub.date_fin = base_date + timedelta(days=additional_days)
        sub.statut = "ACTIVE"

        # Synchroniser QuotaUtilisateur
        quota_stmt = select(QuotaUtilisateur).where(
            QuotaUtilisateur.user_id == sub.user_id
        )
        q_res = await db.execute(quota_stmt)
        quota = q_res.scalar_one_or_none()
        if quota:
            quota.date_fin_premium = sub.date_fin

        await db.commit()
        await db.refresh(sub)
        return sub

    async def cancel_subscription(
        self, db: AsyncSession, subscription_id: uuid.UUID
    ) -> UserSubscription:
        """Résilie un abonnement et repasse l'artisan en formule gratuite."""
        stmt = select(UserSubscription).where(UserSubscription.id == subscription_id)
        res = await db.execute(stmt)
        sub = res.scalar_one_or_none()
        if not sub:
            raise ValueError("Abonnement introuvable.")

        sub.statut = "CANCELED"
        sub.renouvellement_auto = False

        # Repasser l'utilisateur en FREE
        user_stmt = select(User).where(User.id == sub.user_id)
        user_res = await db.execute(user_stmt)
        user = user_res.scalar_one_or_none()
        if user:
            user.type_abonnement = "FREE"

        # Réinitialiser quota premium
        quota_stmt = select(QuotaUtilisateur).where(
            QuotaUtilisateur.user_id == sub.user_id
        )
        q_res = await db.execute(quota_stmt)
        quota = q_res.scalar_one_or_none()
        if quota:
            quota.date_fin_premium = None

        await db.commit()
        await db.refresh(sub)
        return sub

    async def get_subscription_kpis(self, db: AsyncSession) -> dict[str, Any]:
        """Calcule les indicateurs clés de performance des souscriptions."""
        now = datetime.now(UTC).replace(tzinfo=None)
        in_7_days = now + timedelta(days=7)

        # 1. Total artisans inscrits
        users_count_stmt = select(func.count(User.id)).where(User.is_admin == False)
        users_count = (await db.execute(users_count_stmt)).scalar() or 0

        # 2. Total souscriptions créées
        total_subs_stmt = select(func.count(UserSubscription.id))
        total_subs = (await db.execute(total_subs_stmt)).scalar() or 0

        # 3. Abonnements actifs
        active_subs_stmt = (
            select(UserSubscription, Package)
            .join(Package, UserSubscription.package_id == Package.id)
            .where(
                UserSubscription.statut == "ACTIVE",
                or_(
                    UserSubscription.date_fin.is_(None),
                    UserSubscription.date_fin > now,
                ),
            )
        )
        active_res = await db.execute(active_subs_stmt)
        active_rows = active_res.all()
        active_count = len(active_rows)

        # 4. Expirant sous 7 jours
        expiring_stmt = select(func.count(UserSubscription.id)).where(
            UserSubscription.statut == "ACTIVE",
            UserSubscription.date_fin > now,
            UserSubscription.date_fin <= in_7_days,
        )
        expiring_count = (await db.execute(expiring_stmt)).scalar() or 0

        # 5. MRR Estimé (F CFA) et Répartition
        mrr = 0
        repartition: dict[str, int] = {}
        for sub, pkg in active_rows:
            repartition[pkg.nom] = repartition.get(pkg.nom, 0) + 1
            if pkg.duree_jours == 30:
                mrr += pkg.prix
            elif pkg.duree_jours == 365:
                mrr += int(pkg.prix / 12)
            elif pkg.duree_jours == 1:
                mrr += pkg.prix * 4  # Approximation estimation mensuelle
            elif pkg.prix > 0:
                mrr += pkg.prix

        return {
            "total_inscrits": users_count,
            "total_abonnements": total_subs,
            "abonnements_actifs": active_count,
            "abonnements_expires": max(0, total_subs - active_count),
            "expirant_bientot": expiring_count,
            "chiffre_affaires_mrr": mrr,
            "repartition_packages": repartition,
        }


subscription_service = SubscriptionService()
