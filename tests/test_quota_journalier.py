"""Tests du quota gratuit journalier (Redis), des crédits achetés et de l'IP cliente."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.db.session import get_db
from app.main import app
from app.middleware.auth import create_access_token, create_refresh_token
from app.middleware.client_ip import get_client_ip
from app.models.quota import QuotaUtilisateur
from app.services.cache_service import cache_service
from app.services.quota_service import (
    QuotaIndisponibleError,
    cle_quota_journalier,
    identite_quota,
    quota_service,
)


def _db_avec_quota(quota: QuotaUtilisateur | None, rowcount: int = 0) -> MagicMock:
    """Session simulée : SELECT renvoie `quota`, UPDATE renvoie `rowcount`."""
    session = MagicMock()
    session.execute = AsyncMock(
        return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=quota), rowcount=rowcount
        )
    )
    session.commit = AsyncMock()
    return session


# ── Quota journalier ──


@pytest.mark.asyncio
async def test_quota_gratuit_limite_par_jour():
    db = _db_avec_quota(None)
    user_id = uuid.uuid4()
    for _ in range(settings.max_questions_gratuites_par_jour):
        assert await quota_service.consume_quota(db, user_id) is True
    assert await quota_service.consume_quota(db, user_id) is False


@pytest.mark.asyncio
async def test_quota_gratuit_recharge_le_lendemain():
    """La clé est datée : un nouveau jour repart d'un compteur vierge."""
    identite = identite_quota(uuid.uuid4(), None)
    hier = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")
    await cache_service.set(
        cle_quota_journalier(identite, hier),
        str(settings.max_questions_gratuites_par_jour),
    )
    assert await quota_service.questions_gratuites_utilisees(identite) == 0


@pytest.mark.asyncio
async def test_quota_anonyme_compte_par_ip():
    """Deux visiteurs anonymes d'IP différentes ont chacun leur quota."""
    db = _db_avec_quota(None)
    for _ in range(settings.max_questions_gratuites_par_jour):
        assert await quota_service.consume_quota(db, None, "10.0.0.1") is True
    assert await quota_service.consume_quota(db, None, "10.0.0.1") is False
    assert await quota_service.consume_quota(db, None, "10.0.0.2") is True


@pytest.mark.asyncio
async def test_credits_achetes_consommes_apres_le_quota_gratuit():
    user_id = uuid.uuid4()
    quota = QuotaUtilisateur(user_id=user_id, credits_requetes=3)
    for _ in range(settings.max_questions_gratuites_par_jour):
        assert await quota_service.consume_quota(_db_avec_quota(quota), user_id)

    # UPDATE ... WHERE credits_requetes > 0 a touché une ligne → autorisé
    db = _db_avec_quota(quota, rowcount=1)
    assert await quota_service.consume_quota(db, user_id) is True
    db.commit.assert_awaited()

    # Plus aucun crédit (aucune ligne mise à jour) → refusé
    assert await quota_service.consume_quota(_db_avec_quota(quota), user_id) is False


@pytest.mark.asyncio
async def test_pass_premium_ne_consomme_pas_le_quota():
    user_id = uuid.uuid4()
    quota = QuotaUtilisateur(
        user_id=user_id,
        credits_requetes=0,
        date_fin_premium=datetime.now(UTC) + timedelta(hours=2),
    )
    db = _db_avec_quota(quota)
    for _ in range(settings.max_questions_gratuites_par_jour + 3):
        assert await quota_service.consume_quota(db, user_id) is True
    assert (
        await quota_service.questions_gratuites_utilisees(identite_quota(user_id, None))
        == 0
    )


@pytest.mark.asyncio
async def test_info_quota_additionne_gratuit_et_credits():
    user_id = uuid.uuid4()
    quota = QuotaUtilisateur(user_id=user_id, credits_requetes=50)
    db = _db_avec_quota(quota)
    await quota_service.consume_quota(db, user_id)

    info = await quota_service.get_user_quota_info(db, user_id)

    gratuites = settings.max_questions_gratuites_par_jour - 1
    assert info["statut"] == "freemium"
    assert info["gratuites_restantes_jour"] == gratuites
    assert info["credits"] == 50
    assert info["restantes"] == gratuites + 50
    assert info["is_allowed"] is True


@pytest.mark.asyncio
async def test_redis_indispensable_en_production(monkeypatch):
    """En production sans Redis, le quota lève une erreur au lieu d'un compteur par worker."""
    monkeypatch.setattr(settings, "app_env", "production")
    with pytest.raises(QuotaIndisponibleError):
        await quota_service.consume_quota(_db_avec_quota(None), uuid.uuid4())


@pytest.mark.asyncio
async def test_chat_renvoie_503_si_quota_indisponible(monkeypatch):
    async def _indisponible(**kwargs):
        raise QuotaIndisponibleError("redis down")

    monkeypatch.setattr(quota_service, "consume_quota", _indisponible)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/chat", json={"question": "Dosage béton ?"})

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_chat_anonyme_refuse_au_dela_du_quota_journalier():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(settings.max_questions_gratuites_par_jour):
            ok = await client.post("/api/chat", json={"question": "Dosage béton ?"})
            assert ok.status_code == 200
        refus = await client.post("/api/chat", json={"question": "Dosage béton ?"})

    assert refus.status_code == 402


@pytest.mark.asyncio
async def test_chat_question_trop_longue_rejetee():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/chat", json={"question": "x" * 5000})

    assert response.status_code == 422


# ── Tokens ──


@pytest.mark.asyncio
async def test_refresh_token_refuse_comme_token_d_acces():
    """Un refresh token (30 jours) ne doit jamais ouvrir une route protégée."""
    refresh = create_refresh_token(data={"sub": str(uuid.uuid4())})
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/payment/init",
            json={"type_pass": "pass_24h"},
            headers={"Authorization": f"Bearer {refresh}"},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_token_d_acces_accepte():
    token = create_access_token(data={"sub": str(uuid.uuid4())})
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/quota", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200


# ── IP cliente derrière proxy ──


def _connexion(ip: str, xff: str | None = None) -> MagicMock:
    conn = MagicMock()
    conn.client.host = ip
    conn.headers = {"x-forwarded-for": xff} if xff is not None else {}
    return conn


def test_ip_directe_sans_proxy_de_confiance(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_hops", 0)
    assert get_client_ip(_connexion("172.18.0.5", "1.2.3.4")) == "172.18.0.5"


def test_ip_derriere_un_proxy(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_hops", 1)
    assert get_client_ip(_connexion("172.18.0.5", "1.2.3.4")) == "1.2.3.4"


def test_ip_falsifiee_a_gauche_ignoree(monkeypatch):
    """Seule l'entrée ajoutée par le proxy de confiance (à droite) est retenue."""
    monkeypatch.setattr(settings, "trusted_proxy_hops", 1)
    assert get_client_ip(_connexion("10.0.0.1", "6.6.6.6, 1.2.3.4")) == "1.2.3.4"


def test_ip_en_tete_absent_repli_sur_ip_tcp(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_hops", 2)
    assert get_client_ip(_connexion("10.0.0.1", "1.2.3.4")) == "10.0.0.1"


# ── Admin : retour au plan gratuit ──


@pytest.mark.asyncio
async def test_admin_retour_free_conserve_les_credits_achetes():
    from app.models.user import User

    user_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    user = User(id=user_id, email="a@b.ci", type_abonnement="pass_mois")
    admin = User(id=admin_id, email="admin@b.ci", is_admin=True)
    quota = QuotaUtilisateur(user_id=user_id, credits_requetes=42)

    identite = identite_quota(user_id, None)
    await cache_service.set(cle_quota_journalier(identite), "5")

    async def custom_db():
        session = MagicMock()
        results = iter([admin, user, quota])
        session.execute = AsyncMock(
            side_effect=lambda *a, **k: MagicMock(
                scalar_one_or_none=MagicMock(return_value=next(results, None))
            )
        )
        session.commit = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        yield session

    from tests.conftest import mock_get_db

    app.dependency_overrides[get_db] = custom_db
    try:
        token = create_access_token(data={"sub": str(admin_id)})
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/admin/users/{user_id}/grant-pass?type_pass=FREE",
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        app.dependency_overrides[get_db] = mock_get_db

    assert response.status_code == 200, response.text
    assert quota.credits_requetes == 42
    assert await quota_service.questions_gratuites_utilisees(identite) == 0
