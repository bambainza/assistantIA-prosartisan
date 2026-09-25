"""Une question n'est pas perdue quand le fournisseur IA échoue après le décompte."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app
from app.models.quota import QuotaUtilisateur
from app.services.quota_service import identite_quota, quota_service
from app.services.rag_service import rag_service


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
