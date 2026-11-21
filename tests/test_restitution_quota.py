"""Une question n'est pas perdue quand le fournisseur IA échoue après le décompte."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app
from app.models.quota import QuotaUtilisateur
from app.services.cache_service import cache_service
from app.services.quota_service import identite_quota, quota_service
from app.services.rag_service import (
    FALLBACK_MESSAGE,
    RechercheIndisponibleError,
    rag_service,
)


def _db(quota: QuotaUtilisateur | None = None) -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock(
        return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=quota), rowcount=1
        )
    )
    session.commit = AsyncMock()
    return session


async def _utilisees(user_id=None, ip=None) -> int:
    return await quota_service.questions_gratuites_utilisees(
        identite_quota(user_id, ip)
    )


@pytest.mark.asyncio
async def test_question_gratuite_rendue():
    db, user_id = _db(), uuid.uuid4()
    await quota_service.consume_quota(db, user_id)
    await quota_service.consume_quota(db, user_id)

    await quota_service.restituer_quota(db, user_id)

    assert await _utilisees(user_id) == 1


@pytest.mark.asyncio
async def test_credit_achete_rendu_au_dela_du_quota_gratuit():
    quota = QuotaUtilisateur(user_id=uuid.uuid4(), credits_requetes=3)
    db = _db(quota)
    for _ in range(settings.max_questions_gratuites_par_jour + 1):
        assert await quota_service.consume_quota(db, quota.user_id)

    db.execute.reset_mock()
    await quota_service.restituer_quota(db, quota.user_id)

    maj = db.execute.await_args_list[-1].args[0]
    assert str(maj).startswith("UPDATE quotas_utilisateurs")
    assert "credits_requetes + " in str(maj)
    db.commit.assert_awaited()
    assert await _utilisees(quota.user_id) == settings.max_questions_gratuites_par_jour


@pytest.mark.asyncio
async def test_pass_premium_rien_a_rendre():
    quota = QuotaUtilisateur(
        user_id=uuid.uuid4(),
        credits_requetes=0,
        date_fin_premium=(datetime.now(UTC) + timedelta(hours=5)).replace(tzinfo=None),
    )
    db = _db(quota)

    await quota_service.restituer_quota(db, quota.user_id)

    assert await _utilisees(quota.user_id) == 0
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_compteur_jamais_negatif():
    """Compteur expiré entre le décompte et la panne : rien n'est rendu."""
    await quota_service.restituer_quota(_db(), None, "10.9.9.9")

    assert await _utilisees(ip="10.9.9.9") == 0


@pytest.mark.asyncio
async def test_chat_panne_ia_503_et_question_rendue(monkeypatch):
    async def _panne(**kwargs):
        raise RuntimeError("Mistral 429")

    monkeypatch.setattr(rag_service, "generate_response", _panne)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/chat", json={"question": "Dosage béton ?"})

    assert response.status_code == 503
    assert "indisponible" in response.json()["detail"]
    assert await _utilisees(ip="127.0.0.1") == 0


@pytest.mark.asyncio
async def test_stream_panne_ia_evenement_erreur_et_question_rendue(monkeypatch):
    async def _flux_en_panne():
        raise RuntimeError("Mistral 429")
        yield ""  # pragma: no cover - générateur asynchrone

    async def _prepare(**kwargs):
        return [], _flux_en_panne()

    monkeypatch.setattr(rag_service, "generate_response_stream", _prepare)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat/stream", json={"question": "Dosage béton ?"}
        )

    assert "event: error" in response.text
    assert await _utilisees(ip="127.0.0.1") == 0


# ── Panne de la recherche documentaire (Qdrant / embedding) ──


@pytest.fixture
def recherche_en_panne(monkeypatch):
    """Mode réel (clé Mistral « valide ») avec un Qdrant injoignable."""
    monkeypatch.setattr(settings, "mistral_api_key", "sk-test-reel")

    async def _embedding(text):
        return [0.0] * settings.qdrant_vector_size

    async def _qdrant_en_panne(**kwargs):
        raise ConnectionError("Qdrant injoignable")

    monkeypatch.setattr(rag_service, "get_embedding", _embedding)
    monkeypatch.setattr(rag_service.qdrant_client, "query_points", _qdrant_en_panne)


@pytest.mark.asyncio
async def test_panne_recherche_leve_et_ne_met_rien_en_cache(recherche_en_panne):
    """Une panne n'est pas une absence d'information : ni repli, ni cache."""
    with pytest.raises(RechercheIndisponibleError):
        await rag_service.generate_response(question="Dosage béton ?", metier_id=1)

    version = await rag_service._config_version()
    assert (
        await cache_service.get_cached_rag_response("Dosage béton ?", 1, version)
        is None
    )


@pytest.mark.asyncio
async def test_panne_recherche_stream_leve_avant_le_flux(recherche_en_panne):
    with pytest.raises(RechercheIndisponibleError):
        await rag_service.generate_response_stream(question="Dosage béton ?")


@pytest.mark.asyncio
async def test_chat_panne_recherche_503_et_question_rendue(recherche_en_panne):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/chat", json={"question": "Dosage béton ?"})
        stream = await client.post(
            "/api/chat/stream", json={"question": "Dosage béton ?"}
        )

    assert response.status_code == 503
    assert stream.status_code == 503
    assert await _utilisees(ip="127.0.0.1") == 0


@pytest.mark.asyncio
async def test_recherche_aboutie_sans_resultat_reste_un_repli_en_cache(monkeypatch):
    """Recherche réussie mais vide : le repli zéro hallucination est inchangé."""
    monkeypatch.setattr(settings, "mistral_api_key", "sk-test-reel")

    async def _vide(**kwargs):
        return []

    monkeypatch.setattr(rag_service, "search_context", _vide)

    res = await rag_service.generate_response(question="Question hors corpus ?")

    assert res["reponse"] == FALLBACK_MESSAGE
    version = await rag_service._config_version()
    cached = await cache_service.get_cached_rag_response(
        "Question hors corpus ?", None, version
    )
    assert cached is not None and cached["reponse"] == FALLBACK_MESSAGE


@pytest.mark.asyncio
async def test_mode_mock_sans_qdrant_repli_non_mis_en_cache(monkeypatch):
    """Dev/tests sans Qdrant : repli servi, mais jamais figé dans le cache."""

    async def _qdrant_en_panne(**kwargs):
        raise ConnectionError("Qdrant injoignable")

    monkeypatch.setattr(rag_service.qdrant_client, "query_points", _qdrant_en_panne)

    res = await rag_service.generate_response(question="Dosage béton ?")

    assert res["reponse"] == FALLBACK_MESSAGE
    version = await rag_service._config_version()
    assert (
        await cache_service.get_cached_rag_response("Dosage béton ?", None, version)
        is None
    )
