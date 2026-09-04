"""Moteur et session async SQLAlchemy.

PostgreSQL est la cible normale. Un repli SQLite autonome est disponible pour
le développement local et les tests, mais il est **désactivé** dès que
``DB_REQUIRE_POSTGRES=true`` ou ``APP_ENV=production`` : dans ce cas une
connexion PostgreSQL injoignable lève une erreur explicite au démarrage
plutôt que de basculer silencieusement sur SQLite.
"""

import logging
import socket

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.config import settings

logger = logging.getLogger(__name__)


# Compilation de l'extension UUID PostgreSQL en CHAR(36) sur SQLite
@compiles(UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(36)"


def _postgres_port_ouvert(host: str, port: int, timeout: float) -> bool:
    """Sonde TCP rapide : le port PostgreSQL accepte-t-il une connexion ?"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError as exc:
        logger.warning("PostgreSQL injoignable sur %s:%s (%s).", host, port, exc)
        return False


def _construire_moteur():
    """Construit le moteur async : PostgreSQL si possible, sinon repli SQLite."""
    # Sonde TCP courte (max 2 s) ; le handshake asyncpg garde db_connect_timeout.
    probe_timeout = min(float(settings.db_connect_timeout), 2.0)
    postgres_disponible = _postgres_port_ouvert(
        settings.db_host, settings.db_port, probe_timeout
    )

    if not postgres_disponible and settings.postgres_obligatoire:
        raise RuntimeError(
            f"Connexion PostgreSQL requise mais {settings.db_host}:{settings.db_port} "
            "est injoignable. Vérifiez DB_HOST / DB_PORT / le pare-feu, ou démarrez "
            "la base (`docker compose up -d db`). Le repli SQLite est désactivé "
            "(DB_REQUIRE_POSTGRES=true ou APP_ENV=production)."
        )

    if postgres_disponible:
        logger.info(
            "Moteur PostgreSQL : %s:%s/%s",
            settings.db_host,
            settings.db_port,
            settings.db_database,
        )
        return create_async_engine(
            settings.database_url,
            echo=settings.db_echo,
            pool_pre_ping=True,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_recycle=settings.db_pool_recycle,
            connect_args={"timeout": settings.db_connect_timeout},
        )

    sqlite_url = f"sqlite+aiosqlite:///{settings.db_sqlite_path}"
    logger.warning(
        "PostgreSQL indisponible : bascule en mode autonome SQLite (%s). "
        "Les données ne sont pas partagées et ne doivent pas servir en production.",
        sqlite_url,
    )
    return create_async_engine(sqlite_url, echo=settings.db_echo)


engine = _construire_moteur()

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def check_database_connection() -> bool:
    """Exécute un ``SELECT 1`` réel. Retourne ``True`` si la base répond."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("Vérification de connexion à la base échouée : %s", exc)
        return False


async def get_db() -> AsyncSession:
    """Dépendance FastAPI : fournit une session DB par requête."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
