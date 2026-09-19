"""Tests pour les endpoints d'administration des devis et des calculateurs métiers."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import get_db
from app.main import app
from app.middleware.auth import create_access_token
from app.models.quote import Quote
from app.models.user import User


@pytest.fixture
def admin_user():
    return User(
        id=uuid.uuid4(),
        email="admin_quotes_calc@prosartisan.ci",
        nom="Admin Superviseur",
        telephone="+22507000088",
        is_admin=True,
        role_id=None,
    )


@pytest.mark.asyncio
async def test_admin_list_quotes_endpoint(admin_user):
    """GET /api/admin/quotes retourne la liste paginée et les agrégations financières."""
    quote_1 = Quote(
        id=uuid.uuid4(),
        user_id=admin_user.id,
        numero="DEV-202609-0010",
        titre="Rénovation plomberie",
        client_nom="M. Bamba",
        client_telephone="+22507010203",
        statut="BROUILLON",
        total_ht=100000,
        total_ttc=118000,
    )

    async def custom_mock_db():
        session = MagicMock()
        # Mocking user query, count query, items query, and aggregation query
        user_result = MagicMock(
            scalar_one_or_none=MagicMock(return_value=admin_user),
            scalars=MagicMock(
                return_value=MagicMock(all=MagicMock(return_value=[admin_user]))
            ),
        )
        count_result = MagicMock(scalar_one=MagicMock(return_value=1))
        quotes_result = MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(all=MagicMock(return_value=[quote_1]))
            )
        )
        agg_result = MagicMock(one=MagicMock(return_value=(1, 100000.0, 118000.0)))

        session.execute = AsyncMock(
            side_effect=[user_result, count_result, quotes_result, agg_result]
        )
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    token = create_access_token(data={"sub": str(admin_user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get(
                "/api/admin/quotes",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert res.status_code == 200
            data = res.json()
            assert data["total"] == 1
            assert "stats" in data
            assert data["stats"]["total_montant_ht"] == 100000.0
            assert data["stats"]["total_montant_ttc"] == 118000.0
            assert len(data["quotes"]) == 1
            assert data["quotes"][0]["numero"] == "DEV-202609-0010"
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_admin_get_calculators_stats_endpoint(admin_user):
    """GET /api/admin/calculators/stats retourne les compteurs d'usage des outils."""

    async def custom_mock_db():
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value=admin_user),
            )
        )
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    token = create_access_token(data={"sub": str(admin_user.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get(
                "/api/admin/calculators/stats",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert res.status_code == 200
            data = res.json()
            assert "total_calculator_calls" in data
            assert "by_tool" in data
            assert "calculer_dosage_beton_mortier" in data["by_tool"]
            assert data["available_tools"] == 5
    finally:
        app.dependency_overrides.pop(get_db, None)
