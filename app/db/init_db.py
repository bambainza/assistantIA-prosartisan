"""Initialisation de la base de données (création des tables + seed)."""

import logging

from sqlalchemy import select, text

from app.config import settings
from app.db.session import async_session, check_database_connection, engine
from app.models.base import Base
from app.models.metier import Metier, SousMetier
from app.models.user import User

logger = logging.getLogger(__name__)

# Mot de passe admin utilisé uniquement hors production quand aucun n'est fourni.
_DEV_ADMIN_PASSWORD = "dev_admin_password"


async def seed_data() -> None:
    """Remplit la base avec des données initiales (métiers, sous-métiers, admin)."""
    async with async_session() as session:
        # 1. Grainage des Métiers (idempotent par slug)
        metiers_data = [
            {
                "nom": "Bâtiment & Construction",
                "slug": "batiment-construction",
                "description": "Travaux de gros œuvre, maçonnerie, béton armé, charpente, VRD et second œuvre.",
                "sous_metiers": [
                    {"nom": "Maçonnerie, Fondations & Gros œuvre", "slug": "maconnerie-gros-oeuvre"},
                    {"nom": "Ferraillage, Coffrage & Étayage", "slug": "ferraillage-coffrage-etayage"},
                    {"nom": "Terrassement, VRD & Puisards", "slug": "terrassement-vrd-puisards"},
                    {"nom": "Charpente, Couverture & Toiture", "slug": "charpente-couverture"},
                    {"nom": "Étanchéité & Dalles Tropicales", "slug": "etancheite-dalles-tropicales"},
                    {"nom": "Carrelage & Revêtement de Sol", "slug": "carrelage-revetement"},
                    {"nom": "Plâtrerie, Staff & Faux-Plafonds", "slug": "platrerie-staff-plafonds"},
                    {"nom": "Peinture Bâtiment & Ravalement", "slug": "peinture-ravalement"},
                    {"nom": "Topographie & Implantation Chantier", "slug": "topographie-implantation"},
                    {"nom": "Sécurité Chantier & Gestion Déchets", "slug": "securite-chantier-epi"},
                ],
            },
            {
                "nom": "Électricité & Énergie",
                "slug": "electricite-energie",
                "description": "Installations électriques bâtiment, solaire photovoltaïque, groupes électrogènes et climatisation.",
                "sous_metiers": [
                    {"nom": "Électricité Bâtiment & Domotique", "slug": "electricite-batiment"},
                    {"nom": "Installation Solaire & Photovoltaïque", "slug": "installation-solaire"},
                    {"nom": "Groupes Électrogènes & Groupes de Secours", "slug": "groupes-electrogenes-secours"},
                    {"nom": "Froid & Climatisation", "slug": "climatisation-froid"},
                ],
            },
            {
                "nom": "Plomberie & Sanitaire",
                "slug": "plomberie-sanitaire",
                "description": "Tuyauterie, réseaux d'eau potable, assainissement autonome, fosses septiques et forages.",
                "sous_metiers": [
                    {"nom": "Plomberie Sanitaire & Réseaux d'Eau", "slug": "plomberie-sanitaire-spec"},
                    {"nom": "Assainissement Autonome & Fosses Septiques", "slug": "assainissement-fosses-septiques"},
                    {"nom": "Forages d'Eau & Pompes Immergées", "slug": "forages-pompes-immergees"},
                ],
            },
            {
                "nom": "Mécanique & Automobile",
                "slug": "mecanique-automobile",
                "description": "Entretien, réparation mécanique diesel/essence, électricité auto, tôlerie, motos Jakarta et engins BTP.",
                "sous_metiers": [
                    {"nom": "Mécanique Auto Essence & Diesel", "slug": "mecanique-auto"},
                    {"nom": "Électricité & Diagnostic Électronique Auto", "slug": "electricite-diagnostic-auto"},
                    {"nom": "Tôlerie, Carrosserie & Peinture Auto", "slug": "tolerie-peinture-auto"},
                    {"nom": "Motos, Tricycles & Deux-Roues (Jakarta)", "slug": "motos-tricycles-deux-roues"},
                    {"nom": "Engins Lourds & Machinerie BTP", "slug": "engins-lourds-machinerie-btp"},
                ],
            },
            {
                "nom": "Métiers de Bouche & Restauration",
                "slug": "metiers-bouche-restauration",
                "description": "Restauration traditionnelle (maquis, allocodromes), street-food garba, boulangerie, transformation agro-alimentaire et hygiène HACCP.",
                "sous_metiers": [
                    {"nom": "Restauration Traditionnelle & Maquis", "slug": "restauration-maquis"},
                    {"nom": "Street-Food Locale (Garba, Alloco, Beignets)", "slug": "street-food-garba-alloco"},
                    {"nom": "Boulangerie & Pâtisserie Artisanale", "slug": "boulangerie-patisserie-artisanale"},
                    {"nom": "Transformation Agro-Alimentaire (Attiéké, Fumage Chorkor)", "slug": "transformation-agroalimentaire-attieke"},
                    {"nom": "Boissons & Jus Locaux Artisanaux (Bissap, Gnamakoudji)", "slug": "boissons-jus-locaux"},
                    {"nom": "Hygiène Alimentaire & Normes HACCP Tropicales", "slug": "hygiene-haccp-tropicale"},
                ],
            },
            {
                "nom": "Métiers d'Art & Artisanat",
                "slug": "metiers-art-maroquinerie",
                "description": "Maroquinerie d'art, travail du cuir, sculpture sur bois, vannerie et confection textile traditionnelle.",
                "sous_metiers": [
                    {"nom": "Maroquinerie & Travail du Cuir", "slug": "maroquinerie-travail-cuir"},
                    {"nom": "Menuiserie Ébénisterie & Vannerie (Chaises Baoulé)", "slug": "ebenisterie-vannerie-sculpture"},
                    {"nom": "Couture & Confection Textile (Pagne Baoulé, Wax)", "slug": "couture-confection-textile"},
                ],
            },
        ]

        # Insertion ou mise à jour idempotente par slug
        for item in metiers_data:
            sous_items: list[dict] = item.pop("sous_metiers")
            stmt = select(Metier).where(Metier.slug == item["slug"])
            existing_metier = (await session.execute(stmt)).scalar_one_or_none()
            if existing_metier is None:
                metier = Metier(**item)
                session.add(metier)
                await session.flush()
            else:
                existing_metier.nom = item["nom"]
                existing_metier.description = item["description"]
                metier = existing_metier

            for sm in sous_items:
                sm_stmt = select(SousMetier).where(SousMetier.slug == sm["slug"])
                existing_sm = (await session.execute(sm_stmt)).scalar_one_or_none()
                if existing_sm is None:
                    session.add(SousMetier(metier_id=metier.id, **sm))
                else:
                    existing_sm.nom = sm["nom"]
                    existing_sm.metier_id = metier.id
        await session.commit()

        # 2. Grainage de l'administrateur par défaut
        admin_email = settings.admin_email
        admin_stmt = select(User).where(User.email == admin_email)
        admin_result = await session.execute(admin_stmt)
        if admin_result.scalar_one_or_none() is None:
            admin_password = settings.admin_password
            if not admin_password:
                if settings.is_production:
                    logger.warning(
                        "Aucun ADMIN_PASSWORD défini : compte administrateur non créé. "
                        "Définissez ADMIN_EMAIL et ADMIN_PASSWORD puis relancez."
                    )
                    admin_password = None
                else:
                    admin_password = _DEV_ADMIN_PASSWORD
                    logger.info(
                        "ADMIN_PASSWORD absent (hors production) : "
                        "utilisation du mot de passe de développement par défaut."
                    )

            if admin_password:
                import uuid

                from app.middleware.auth import hash_password

                admin_user = User(
                    id=uuid.uuid4(),
                    email=admin_email,
                    nom="Administrateur ProsArtisan",
                    telephone="+22500000000",
                    password_hash=hash_password(admin_password),
                    is_admin=True,
                    auth_provider="local",
                    type_abonnement="FREE",
                )
                session.add(admin_user)

        await session.commit()


async def init_db() -> None:
    """Crée les tables SQLAlchemy et injecte les données initiales.

    En production (ou si ``DB_REQUIRE_POSTGRES=true``) une base injoignable
    fait échouer le démarrage ; sinon l'erreur est seulement journalisée.
    """
    try:
        if not await check_database_connection():
            raise RuntimeError("la base de données ne répond pas (SELECT 1 a échoué)")

        async with engine.begin() as conn:
            if conn.dialect.name == "postgresql":
                # Active l'extension UUID si nécessaire
                await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "pgcrypto"'))
            await conn.run_sync(Base.metadata.create_all)

        await seed_data()
    except Exception as e:
        if settings.postgres_obligatoire:
            raise
        logger.warning("Base de données non initialisée (%s).", e)


async def drop_db() -> None:
    """Supprime toutes les tables (usage test uniquement)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
