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
        # 1. Grainage des Métiers (idempotent par slug - 10 Pôles toutes azimuts)
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
                "description": "Installations électriques bâtiment, solaire photovoltaïque, groupes électrogènes, bobinage et climatisation.",
                "sous_metiers": [
                    {"nom": "Électricité Bâtiment & Domotique", "slug": "electricite-batiment"},
                    {"nom": "Installation Solaire & Photovoltaïque", "slug": "installation-solaire"},
                    {"nom": "Groupes Électrogènes & Groupes de Secours", "slug": "groupes-electrogenes-secours"},
                    {"nom": "Froid & Climatisation", "slug": "climatisation-froid"},
                    {"nom": "Bobinage Moteurs & Transformateurs", "slug": "bobinage-moteurs-transfos"},
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
                    {"nom": "Traitement de l'Eau & Piscines", "slug": "traitement-eau-piscines"},
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
                    {"nom": "Vulcanisation, Pneus & Train Avant", "slug": "vulcanisation-pneus"},
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
                    {"nom": "Boucherie, Charcuterie & Choukouya Braisé", "slug": "boucherie-choukouya-grillades"},
                    {"nom": "Hygiène Alimentaire & Normes HACCP Tropicales", "slug": "hygiene-haccp-tropicale"},
                ],
            },
            {
                "nom": "Métiers d'Art & Artisanat",
                "slug": "metiers-art-maroquinerie",
                "description": "Maroquinerie d'art, travail du cuir, sculpture sur bois, vannerie et confection textile traditionnelle.",
                "sous_metiers": [
                    {"nom": "Maroquinerie & Travail du Cuir", "slug": "maroquinerie-travail-cuir"},
                    {"nom": "Menuiserie Ébénisterie & Sculpture Bois", "slug": "ebenisterie-vannerie-sculpture"},
                    {"nom": "Vannerie, Rotin, Bambou & Tissage Déco", "slug": "vannerie-rotin-bambou"},
                    {"nom": "Bijouterie, Joaillerie & Fonte de Métaux (Bronze/Or)", "slug": "bijouterie-fonte-metaux"},
                    {"nom": "Poterie, Céramique & Décoration Argile", "slug": "poterie-ceramique-argile"},
                    {"nom": "Ferronnerie d'Art & Forge Décorative", "slug": "ferronnerie-art-forge"},
                ],
            },
            {
                "nom": "Métiers du Textile, Habillement & Mode",
                "slug": "textile-habillement-mode",
                "description": "Couture artisanale, confection wax, tissage traditionnel pagne Baoulé/Kente/Sénoufo, broderie et teinturerie batik.",
                "sous_metiers": [
                    {"nom": "Couture & Confection Homme/Femme (Wax/Pagne)", "slug": "couture-confection-habillement"},
                    {"nom": "Tissage Traditionnel (Pagne Baoulé, Kente, Sénoufo)", "slug": "tissage-traditionnel-pagnes"},
                    {"nom": "Modélisme, Stylisme & Patronage", "slug": "modelisme-stylisme-patronage"},
                    {"nom": "Teinturerie Artisanale, Batiks & Bogolan", "slug": "teinturerie-batik-bogolan"},
                    {"nom": "Broderie Artisanale & Industrielle", "slug": "broderie-artisanale"},
                ],
            },
            {
                "nom": "Métiers de la Beauté, Coiffure & Soins",
                "slug": "beaute-coiffure-soins",
                "description": "Coiffure mixte, tresses et nattes africaines, soins corporels et cosmétique artisanale au karité.",
                "sous_metiers": [
                    {"nom": "Coiffure Mixte, Coupe & Barbe", "slug": "coiffure-mixte-coupe"},
                    {"nom": "Tresses Africaines, Nattes & Coiffures Traditionnelles", "slug": "tresses-nattes-africaines"},
                    {"nom": "Soins Esthétiques, Manucure & Onglerie", "slug": "soins-esthetiques-onglerie"},
                    {"nom": "Cosmétique Artisanale (Beurre de Karité, Savon Noir)", "slug": "cosmetique-artisanale-karite"},
                ],
            },
            {
                "nom": "Métiers de l'Électronique, Numérique & Réparation",
                "slug": "electronique-reparation-services",
                "description": "Réparation smartphones, maintenance informatique, TV, petit électroménager et serrurerie.",
                "sous_metiers": [
                    {"nom": "Réparation Smartphones, Tablettes & Connectique", "slug": "reparation-smartphones-tablettes"},
                    {"nom": "Maintenance Informatique, PC & Réseaux Locaux", "slug": "maintenance-informatique-pc"},
                    {"nom": "Dépannage Téléviseurs, Audio & Électroménager", "slug": "depannage-tv-electromenager"},
                    {"nom": "Serrurerie, Clés Minutes & Sécurité", "slug": "serrurerie-cles-minutes"},
                ],
            },
            {
                "nom": "Métiers Ruraux, Environnement & Recyclage",
                "slug": "rural-environnement-recyclage",
                "description": "Pépinières, espaces verts, pisciculture, recyclage plastiques/métaux et éco-matériaux de construction.",
                "sous_metiers": [
                    {"nom": "Pépinières, Paysagisme & Espaces Verts", "slug": "pepinieres-espaces-verts"},
                    {"nom": "Pisciculture Artisanale & Élevage Volaille", "slug": "pisciculture-elevage-artisanal"},
                    {"nom": "Recyclage Plastiques, Métaux & Déchets", "slug": "recyclage-plastiques-metaux"},
                    {"nom": "Éco-Construction & Briques de Terre Compressée (BTC)", "slug": "eco-construction-btc"},
                ],
            },
        ]

        # Insertion ou mise à jour idempotente par slug
        for item in metiers_data:
            sous_items: list[dict] = item.pop("sous_metiers")
            stmt = select(Metier).where(Metier.slug == item["slug"])
            existing_metier = (await session.execute(stmt)).scalar_one_or_none()
            if existing_metier is None:
                metier = Metier(is_active=True, **item)
                session.add(metier)
                await session.flush()
            else:
                existing_metier.nom = item["nom"]
                existing_metier.description = item["description"]
                if getattr(existing_metier, "is_active", None) is None:
                    existing_metier.is_active = True
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
