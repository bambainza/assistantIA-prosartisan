"""Le repli SQLite du dev doit pouvoir créer et grainer une base neuve, deux fois.

Régressions couvertes : rôle RBAC neuf dont la collection `permissions` était
lue paresseusement (MissingGreenlet en async) et colonnes JSONB mappées en
`Text` sous SQLite (liste Python non enregistrable).
"""

import os
import subprocess
import sys

SCRIPT = """
import asyncio
from app.db.init_db import init_db, seed_data

async def main():
    await init_db()
    await seed_data()

asyncio.run(main())
"""


def test_seed_sqlite_neuve_puis_relance(tmp_path):
    env = {
        **os.environ,
        "APP_ENV": "development",
        "DB_PORT": "1",  # PostgreSQL injoignable -> repli SQLite
        "DB_REQUIRE_POSTGRES": "false",
        "DB_SQLITE_PATH": str(tmp_path / "seed.db"),
        "REDIS_PORT": "1",
        "QDRANT_PORT": "1",
    }
    for _ in range(2):  # le grainage est idempotent
        result = subprocess.run(
            [sys.executable, "-c", SCRIPT],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
            check=False,
        )
        assert result.returncode == 0, result.stderr[-2000:]
