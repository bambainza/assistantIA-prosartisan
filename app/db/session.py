"""Session async SQLAlchemy + engine PostgreSQL (avec fallback SQLite si injoignable)."""

import socket
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import UUID

from app.config import settings

# Compilation de l'extension UUID PostgreSQL en CHAR(36) sur SQLite
@compiles(UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(36)"

def create_app_engine():
    pg_host = settings.db_host
    pg_port = settings.db_port
    
    # Test de connexion rapide au port PostgreSQL
    try:
        with socket.create_connection((pg_host, pg_port), timeout=1.0):
            use_postgres = True
    except (socket.timeout, ConnectionRefusedError, OSError):
        use_postgres = False

    if use_postgres:
        url = settings.database_url
    else:
        url = "sqlite+aiosqlite:///./prosartisan.db"
        print(f"[AVERTISSEMENT] PostgreSQL injoignable sur {pg_host}:{pg_port}. Mode autonome SQLite actif : {url}")
        
    return create_async_engine(
        url,
        echo=settings.app_debug,
        pool_pre_ping=True if use_postgres else False,
    )

engine = create_app_engine()

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    """Dépendance FastAPI : fournit une session DB par requête."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
