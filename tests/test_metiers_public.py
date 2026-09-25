"""Liste publique des métiers : sans authentification, champs publics uniquement."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.metier import Metier
from app.services.parametres_service import parametres_service


@pytest.mark.asyncio
async def test_metiers_actifs_publics(monkeypatch):
    async def _actifs(db):
        return [
            Metier(
                id=13, nom="Bâtiment & Construction", slug="batiment", is_active=True
            ),
            Metier(
                id=2, nom="Électricité & Énergie", slug="electricite", is_active=True
            ),
        ]

    monkeypatch.setattr(parametres_service, "list_metiers_actifs", _actifs)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/metiers")

    assert response.status_code == 200
    assert response.json() == [
        {"id": 13, "nom": "Bâtiment & Construction", "slug": "batiment"},
        {"id": 2, "nom": "Électricité & Énergie", "slug": "electricite"},
    ]


def test_requete_ne_garde_que_les_metiers_actifs():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(scalars=lambda: MagicMock(all=list)))
    asyncio.run(parametres_service.list_metiers_actifs(db))

    sql = str(db.execute.await_args.args[0])
    assert "metiers.is_active IS true" in sql
    assert "ORDER BY metiers.id" in sql
