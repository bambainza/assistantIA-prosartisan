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
        # 1. Grainage des Métiers
        result = await session.execute(select(Metier))
        if result.scalars().first() is None:
            metiers_data = [
                {
                    "nom": "Bâtiment & Construction",
                    "slug": "batiment-construction",
                    "description": "Travaux de gros œuvre, maçonnerie, béton armé et charpente.",
                    "sous_metiers": [
                        {
                            "nom": "Maçonnerie & Gros œuvre",
                            "slug": "maconnerie-gros-oeuvre",
                        },
                        {
                            "nom": "Charpente & Couverture",
                            "slug": "charpente-couverture",
                        },
                        {
                            "nom": "Carrelage & Revêtement",
                            "slug": "carrelage-revetement",
                        },
                    ],
                },
                {
                    "nom": "Électricité & Énergie",
                    "slug": "electricite-energie",
                    "description": "Installations électriques, domotique et solaires.",
                    "sous_metiers": [
                        {"nom": "Électricité Bâtiment", "slug": "electricite-batiment"},
                        {
                            "nom": "Installation Solaire & Photovoltaïque",
                            "slug": "installation-solaire",
                        },
                    ],
                },
                {
                    "nom": "Plomberie & Sanitaire",
                    "slug": "plomberie-sanitaire",
                    "description": "Tuyauterie, installations sanitaires et climatisation.",
                    "sous_metiers": [
                        {
                            "nom": "Plomberie Sanitaire",
                            "slug": "plomberie-sanitaire-spec",
                        },
                        {"nom": "Climatisation & Froid", "slug": "climatisation-froid"},
                    ],
                },
                {
                    "nom": "Mécanique & Automobile",
                    "slug": "mecanique-automobile",
                    "description": "Entretien, réparation mécanique et tôlerie.",
                    "sous_metiers": [
                        {"nom": "Mécanique Auto & Diesel", "slug": "mecanique-auto"},
                        {
                            "nom": "Tôlerie & Peinture Auto",
                            "slug": "tolerie-peinture-auto",
                        },
                    ],
                },
            ]

            for item in metiers_data:
                sous_items: list[dict] = item.pop("sous_metiers")
                metier = Metier(**item)
                session.add(metier)
                await session.flush()
                for sm in sous_items:
                    session.add(SousMetier(metier_id=metier.id, **sm))

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
