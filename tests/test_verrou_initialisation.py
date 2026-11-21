"""`init_db` est sérialisé entre workers par un verrou consultatif PostgreSQL.

Régression : au démarrage avec deux workers uvicorn, les deux grainaient en même
temps les nouvelles permissions RBAC ; l'un échouait sur `ix_permissions_code`
(`UniqueViolationError`) et uvicorn devait le relancer.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.config import settings
from app.db import init_db as module_init

# ── Ordre des opérations (sans base réelle) ──────────────────────────────


class _Connexion:
    def __init__(self, journal: list[str], dialecte: str) -> None:
        self.journal = journal
        self.dialect = SimpleNamespace(name=dialecte)

    async def execute(self, requete, parametres=None) -> None:
        sql = str(requete)
        if "pg_advisory_lock" in sql:
            assert parametres == {"cle": module_init.CLE_VERROU_INITIALISATION}
            self.journal.append("verrou")
        elif "pg_advisory_unlock" in sql:
            self.journal.append("liberation")
        else:
            self.journal.append("extension")

    async def run_sync(self, _fonction) -> None:
        self.journal.append("tables")


class _Moteur:
    def __init__(self, dialecte: str) -> None:
        self.journal: list[str] = []
        self.dialect = SimpleNamespace(name=dialecte)

    @asynccontextmanager
    async def connect(self):
        yield _Connexion(self.journal, self.dialect.name)

    @asynccontextmanager
    async def begin(self):
        yield _Connexion(self.journal, self.dialect.name)


@pytest.fixture
def moteur(monkeypatch: pytest.MonkeyPatch):
    def _installer(dialecte: str, *, echec_grainage: bool = False) -> _Moteur:
        faux = _Moteur(dialecte)

        async def _grainer() -> None:
            faux.journal.append("grainage")
            if echec_grainage:
                raise RuntimeError("grainage interrompu")

        async def _connexion_ok() -> bool:
            return True

        monkeypatch.setattr(module_init, "engine", faux)
        monkeypatch.setattr(module_init, "seed_data", _grainer)
        monkeypatch.setattr(module_init, "check_database_connection", _connexion_ok)
        return faux

    return _installer


@pytest.mark.asyncio
async def test_tables_et_grainage_sous_verrou_postgresql(moteur) -> None:
    faux = moteur("postgresql")
    await module_init.init_db()
    assert faux.journal == [
        "verrou",
        "extension",
        "tables",
        "grainage",
        "liberation",
    ]


@pytest.mark.asyncio
async def test_verrou_libere_si_le_grainage_echoue(moteur, monkeypatch) -> None:
    monkeypatch.setattr(settings, "db_require_postgres", True)
    faux = moteur("postgresql", echec_grainage=True)
    with pytest.raises(RuntimeError, match="grainage interrompu"):
        await module_init.init_db()
    assert faux.journal[0] == "verrou" and faux.journal[-1] == "liberation"


@pytest.mark.asyncio
async def test_sqlite_sans_verrou(moteur) -> None:
    faux = moteur("sqlite")
    await module_init.init_db()
    assert faux.journal == ["tables", "grainage"]


def test_cle_tient_dans_un_bigint_postgresql() -> None:
    assert 0 < module_init.CLE_VERROU_INITIALISATION < 2**63


# ── Démarrages concurrents sur un PostgreSQL réel ────────────────────────

DEMARRAGE = """
import asyncio
from app.db.init_db import init_db

asyncio.run(init_db())
"""

NB_PROCESSUS = 4


@pytest.mark.skipif(
    os.getenv("RUN_SHARED_BACKEND_TESTS") != "1",
    reason="Nécessite un PostgreSQL réel explicitement sélectionné.",
)
@pytest.mark.asyncio
async def test_demarrages_concurrents_sur_base_neuve() -> None:
    import asyncpg

    connexion = {
        "host": settings.db_host,
        "port": settings.db_port,
        "user": settings.db_username,
        "password": settings.db_password,
    }
    base = f"prosartisan_verrou_{uuid.uuid4().hex[:12]}"
    admin = await asyncpg.connect(database=settings.db_database, **connexion)
    await admin.execute(f'CREATE DATABASE "{base}"')
    try:
        env = {
            **os.environ,
            "APP_ENV": "testing",
            "DB_REQUIRE_POSTGRES": "true",
            "DB_DATABASE": base,
        }
        processus = [
            await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                DEMARRAGE,
                env=env,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            for _ in range(NB_PROCESSUS)
        ]
        sorties = await asyncio.wait_for(
            asyncio.gather(*(p.communicate() for p in processus)), timeout=180
        )
        for p, (_out, err) in zip(processus, sorties, strict=True):
            assert p.returncode == 0, err.decode(errors="replace")[-3000:]

        neuve = await asyncpg.connect(database=base, **connexion)
        try:
            nb = await neuve.fetchval("SELECT count(*) FROM permissions")
        finally:
            await neuve.close()
        assert nb == len(module_init._PERMISSIONS_CATALOG)
    finally:
        await admin.execute(f'DROP DATABASE IF EXISTS "{base}" WITH (FORCE)')
        await admin.close()
