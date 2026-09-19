"""Tests pour le module de devis et facturation pro-forma (QuoteService & Router)."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import get_db
from app.main import app
from app.middleware.auth import create_access_token
from app.models.quote import Quote
from app.models.user import User
from app.schemas.quote import QuoteItem
from app.services.quote_service import quote_service

_USER_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_OTHER_USER_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def make_mock_db(session):
    async def _mock_db():
        yield session

    return _mock_db


@pytest.fixture
def auth_headers():
    token = create_access_token({"sub": str(_USER_ID), "role": "artisan"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def other_auth_headers():
    token = create_access_token({"sub": str(_OTHER_USER_ID), "role": "artisan"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_user():
    return User(
        id=_USER_ID,
        nom="Kouamé Jean",
        telephone="0700112233",
        email="kouame@prosartisan.ci",
        is_admin=False,
    )


@pytest.fixture
def sample_quote():
    now = datetime.now(UTC).replace(tzinfo=None)
    return Quote(
        id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        user_id=_USER_ID,
        numero="DEV-202609-0001",
        titre="Rénovation tableau électrique",
        client_nom="M. Koffi",
        client_telephone="0500112233",
        client_adresse="Cocody 2 Plateaux",
        metier_id=2,
        statut="BROUILLON",
        items=[
            {
                "description": "Disjoncteurs 20A",
                "quantite": 3.0,
                "unite": "unité",
                "prix_unitaire": 6000,
                "total": 18000,
                "type_item": "FOURNITURE",
            },
            {
                "description": "Main d'œuvre",
                "quantite": 1.0,
                "unite": "forfait",
                "prix_unitaire": 30000,
                "total": 30000,
                "type_item": "MAIN_D_OEUVRE",
            },
        ],
        total_ht=48000,
        remise_pct=0.0,
        tva_pct=0.0,
        total_ttc=48000,
        acompte_demande_pct=30.0,
        montant_acompte=14400,
        mode_paiement="Wave / Orange Money",
        delai_jours=2,
        notes="Garantie intervention 6 mois.",
        date_emission=now,
        date_validite=now + timedelta(days=30),
        created_at=now,
        updated_at=now,
    )


# ── 1. TESTS UNITAIRES SERVICE ───────────────────────────────────────────────


def test_quote_service_calculate_totals():
    """Vérifie le calcul complet : lignes, remise 10%, TVA 18%, acompte 40%."""
    items = [
        QuoteItem(
            description="Ciment",
            quantite=10,
            unite="sac",
            prix_unitaire=5000,
            total=50000,
        ),
        QuoteItem(
            description="Sable",
            quantite=1,
            unite="voyage",
            prix_unitaire=30000,
            total=30000,
        ),
    ]
    res = quote_service.calculate_totals(
        items=items,
        remise_pct=10.0,
        tva_pct=18.0,
        acompte_pct=40.0,
    )
    assert res["total_ht"] == 80000
    assert res["montant_remise"] == 8000  # 80 000 * 10%
    # Total après remise = 72 000
    assert res["montant_tva"] == 12960  # 72 000 * 18%
    assert res["total_ttc"] == 84960
    assert res["montant_acompte"] == 33984  # 84 960 * 40%
    assert res["solde_restant"] == 84960 - 33984


@pytest.mark.asyncio
async def test_quote_service_extract_mock():
    """Vérifie l'extraction déterministe depuis un texte d'artisan."""
    res = await quote_service.extract_quote_from_text(
        description_brute="J'ai posé 3 disjoncteurs et 40m de câble pour Koffi",
        client_nom="M. Koffi",
    )
    assert "électricité" in res.titre.lower() or "électrique" in res.titre.lower()
    assert res.client_nom == "M. Koffi"
    assert len(res.items) >= 2
    assert any(it.type_item == "MAIN_D_OEUVRE" for it in res.items)


def test_quote_service_generate_whatsapp_text(sample_quote):
    """Vérifie la génération du texte WhatsApp avec émojis et totaux formatés."""
    text = quote_service.generate_whatsapp_text(
        quote=sample_quote,
        artisan_nom="Kouamé Jean",
        artisan_phone="0700112233",
    )
    assert "DEV-202609-0001" in text
    assert "M. Koffi" in text
    assert "48 000 F CFA" in text
    assert "14 400 F CFA" in text
    assert "0700112233" in text


def test_quote_service_generate_html(sample_quote, sample_user):
    """Vérifie la génération du document HTML du devis."""
    html = quote_service.generate_quote_html(sample_quote, sample_user)
    assert "DEV-202609-0001" in html
    assert "Kouamé Jean" in html
    assert "M. Koffi" in html
    assert "Bon pour Accord" in html


# ── 2. TESTS ROUTER FASTAPI (AVEC MOCK DB) ───────────────────────────────────


@pytest.mark.asyncio
async def test_extract_quote_endpoint(auth_headers):
    """POST /api/quotes/extract analyse la demande et renvoie la proposition de devis."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "description_brute": "Réparation d'une fuite sous évier et changement robinet",
            "client_nom": "Mme Bamba",
        }
        response = await client.post(
            "/api/quotes/extract", json=payload, headers=auth_headers
        )

    assert response.status_code == 200
    data = response.json()
    assert data["client_nom"] == "Mme Bamba"
    assert len(data["items"]) > 0


@pytest.mark.asyncio
async def test_create_quote_endpoint(auth_headers, sample_user):
    """POST /api/quotes crée et persiste un nouveau devis."""
    session = MagicMock()
    session.execute = AsyncMock(
        side_effect=[
            MagicMock(scalar=MagicMock(return_value=0)),  # count pour numéro
            MagicMock(scalar_one_or_none=MagicMock(return_value=sample_user)),  # user
        ]
    )
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.refresh = AsyncMock()

    app.dependency_overrides[get_db] = make_mock_db(session)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "titre": "Pose de carrelage terrasse",
            "client_nom": "M. Touré",
            "client_telephone": "0708091011",
            "client_adresse": "Riviera Palmeraie",
            "items": [
                {
                    "description": "Carreaux 60x60 Grès cérame",
                    "quantite": 35.0,
                    "unite": "m²",
                    "prix_unitaire": 9000,
                    "type_item": "FOURNITURE",
                },
                {
                    "description": "Pose et double encollage",
                    "quantite": 35.0,
                    "unite": "m²",
                    "prix_unitaire": 3000,
                    "type_item": "MAIN_D_OEUVRE",
                },
            ],
            "remise_pct": 5.0,
            "acompte_demande_pct": 30.0,
        }
        response = await client.post("/api/quotes", json=payload, headers=auth_headers)

    assert response.status_code == 201
    data = response.json()
    assert data["client_nom"] == "M. Touré"
    assert data["total_ht"] == (35 * 9000) + (35 * 3000)  # 420 000
    assert data["remise_pct"] == 5.0
    assert data["total_ttc"] == 399000  # 420 000 - 5%
    assert data["whatsapp_share_url"] is not None


@pytest.mark.asyncio
async def test_list_quotes_endpoint(auth_headers, sample_quote, sample_user):
    """GET /api/quotes liste les devis de l'artisan connecté."""
    session = MagicMock()
    session.execute = AsyncMock(
        side_effect=[
            MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=[sample_quote]))
                )
            ),
            MagicMock(scalar_one_or_none=MagicMock(return_value=sample_user)),
        ]
    )
    app.dependency_overrides[get_db] = make_mock_db(session)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/quotes", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["numero"] == "DEV-202609-0001"


@pytest.mark.asyncio
async def test_get_quote_by_id_success(auth_headers, sample_quote, sample_user):
    """GET /api/quotes/{id} retourne les détails du devis."""
    session = MagicMock()
    session.execute = AsyncMock(
        side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=sample_quote)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=sample_user)),
        ]
    )
    app.dependency_overrides[get_db] = make_mock_db(session)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/api/quotes/{sample_quote.id}", headers=auth_headers
        )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(sample_quote.id)
    assert data["total_ttc"] == 48000


@pytest.mark.asyncio
async def test_get_quote_anti_idor_autre_utilisateur(other_auth_headers):
    """GET /api/quotes/{id} retourne 404 pour un devis appartenant à autrui."""
    session = MagicMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    app.dependency_overrides[get_db] = make_mock_db(session)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        fake_id = uuid.uuid4()
        response = await client.get(
            f"/api/quotes/{fake_id}", headers=other_auth_headers
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_quote_status(auth_headers, sample_quote, sample_user):
    """PATCH /api/quotes/{id}/status met à jour le statut (ex: ACCEPTE)."""
    session = MagicMock()
    session.execute = AsyncMock(
        side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=sample_quote)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=sample_user)),
        ]
    )
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    app.dependency_overrides[get_db] = make_mock_db(session)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {"statut": "ACCEPTE"}
        response = await client.patch(
            f"/api/quotes/{sample_quote.id}/status",
            json=payload,
            headers=auth_headers,
        )

    assert response.status_code == 200
    assert response.json()["statut"] == "ACCEPTE"


@pytest.mark.asyncio
async def test_render_quote_html(auth_headers, sample_quote, sample_user):
    """GET /api/quotes/{id}/html renvoie une page HTML imprimable."""
    session = MagicMock()
    session.execute = AsyncMock(
        side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=sample_quote)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=sample_user)),
        ]
    )
    app.dependency_overrides[get_db] = make_mock_db(session)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/api/quotes/{sample_quote.id}/html",
            headers=auth_headers,
        )

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "DEV-202609-0001" in response.text
