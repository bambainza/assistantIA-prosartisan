"""Régressions : second facteur, rejeu concurrent, pannes et coûts audio."""

import asyncio
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pyotp
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.db import session as session_module
from app.db.session import get_db
from app.main import app
from app.middleware.auth import create_refresh_token, decode_token
from app.models.user import User
from app.routers import auth
from app.services.audio_budget_service import audio_budget
from app.services.audio_service import audio_service
from app.services.cache_service import SharedBackendUnavailableError, cache_service
from app.services.quota_service import quota_service
from app.services.rag_service import ActivationIndisponibleError, rag_service


@pytest.fixture
def auth_session(monkeypatch: pytest.MonkeyPatch) -> Any:
    user = User(
        id=uuid.uuid4(),
        email="regression@example.com",
        is_admin=True,
        totp_enabled=True,
        totp_secret=pyotp.random_base32(),
        auth_provider="local",
        type_abonnement="FREE",
    )
    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: user))
    session.commit = AsyncMock()

    async def database() -> Any:
        yield session

    monkeypatch.setitem(app.dependency_overrides, get_db, database)
    monkeypatch.setattr(
        auth,
        "verify_google_token",
        AsyncMock(
            return_value={
                "sub": "google-subject",
                "email": user.email,
            }
        ),
    )
    return user, session


@pytest.mark.parametrize("endpoint", ["/api/auth/google", "/api/auth/web/google"])
@pytest.mark.parametrize("code", [None, "invalid", "valid"])
async def test_google_admin_exige_totp_avant_jetons(
    monkeypatch: pytest.MonkeyPatch, auth_session: Any, endpoint: Any, code: Any
) -> None:
    user, session = auth_session
    valid = pyotp.TOTP(user.totp_secret).now()
    invalid = "111111" if valid != "111111" else "222222"
    payload = {"credential": "verified-by-mock"}
    if code:
        payload["totp_code"] = valid if code == "valid" else invalid
    issuer = MagicMock(wraps=auth.create_access_token)
    monkeypatch.setattr(auth, "create_access_token", issuer)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(endpoint, json=payload)
    if code == "valid":
        assert response.status_code == 200
        issuer.assert_called_once()
        if "/web/" in endpoint:
            assert "access_token" not in response.json()
            assert "HttpOnly" in response.headers["set-cookie"]
    else:
        assert response.status_code == 401
        issuer.assert_not_called()
        session.commit.assert_not_awaited()
        assert "set-cookie" not in response.headers


async def test_google_liaison_compte_exige_totp_avant_commit(auth_session: Any) -> None:
    user, session = auth_session
    session.execute.side_effect = [
        MagicMock(scalar_one_or_none=lambda: None),
        MagicMock(scalar_one_or_none=lambda: user),
    ]
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/auth/google", json={"credential": "verified"}
        )
    assert response.status_code == 401
    session.commit.assert_not_awaited()
    assert user.google_id is None


async def test_refresh_concurrent_un_seul_gagnant(auth_session: Any) -> None:
    user, session = auth_session
    token = create_refresh_token({"sub": str(user.id)})
    barrier = asyncio.Event()
    arrivals = 0

    async def lookup(*args: Any, **kwargs: Any) -> Any:
        nonlocal arrivals
        arrivals += 1
        if arrivals == 2:
            barrier.set()
        await asyncio.wait_for(barrier.wait(), timeout=3)
        return MagicMock(scalar_one_or_none=lambda: user)

    session.execute.side_effect = lookup
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        responses = await asyncio.gather(
            *[
                client.post("/api/auth/refresh", json={"refresh_token": token})
                for _ in range(2)
            ]
        )
    assert sorted(response.status_code for response in responses) == [200, 401]


async def test_refresh_sans_jti_refuse(auth_session: Any) -> None:
    import jwt

    user, _ = auth_session
    payload = decode_token(create_refresh_token({"sub": str(user.id)}))
    del payload["jti"]
    token = jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/auth/refresh", json={"refresh_token": token})
    assert response.status_code == 401


async def test_refresh_redis_indisponible_503(
    monkeypatch: pytest.MonkeyPatch, auth_session: Any
) -> None:
    user, _ = auth_session
    monkeypatch.setattr(
        cache_service,
        "set_if_absent",
        AsyncMock(side_effect=SharedBackendUnavailableError()),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": create_refresh_token({"sub": str(user.id)})},
        )
    assert response.status_code == 503


async def test_rate_limit_redis_production_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/auth/login", json={})
    assert response.status_code == 503
    assert "content-security-policy" in response.headers
    assert "x-request-id" in response.headers


def test_websocket_redis_production_erreur_controlee(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    consume = AsyncMock(return_value=True)
    monkeypatch.setattr(quota_service, "consume_quota", consume)
    with TestClient(app).websocket_connect("/api/chat/ws") as websocket:
        websocket.send_text("Comment poser un carreau ?")
        assert websocket.receive_json()["type"] == "error"
        websocket.send_json({"type": "ping"})
        assert websocket.receive_json()["type"] == "pong"
    consume.assert_not_awaited()


@pytest.mark.parametrize("kind", ["stt", "tts"])
async def test_budget_audio_concurrent_borne_et_restitue(
    monkeypatch: pytest.MonkeyPatch, kind: Any
) -> None:
    monkeypatch.setattr(settings, "audio_stt_requests_per_day", 1)
    monkeypatch.setattr(settings, "audio_tts_chars_per_day", 1)
    admitted = asyncio.Event()
    release = asyncio.Event()

    async def first() -> Any:
        with pytest.raises(RuntimeError):
            async with audio_budget(kind, None, "192.0.2.1"):
                admitted.set()
                await release.wait()
                raise RuntimeError("fournisseur indisponible")

    task = asyncio.create_task(first())
    await admitted.wait()
    try:
        with pytest.raises(HTTPException) as exc:
            async with audio_budget(kind, None, "192.0.2.1"):
                pytest.fail("Budget dépassé")
        assert exc.value.status_code == 429
        # Une autre IP dispose de son propre budget.
        async with audio_budget(kind, None, "192.0.2.2"):
            pass
    finally:
        release.set()
        await task
    async with audio_budget(kind, None, "192.0.2.1"):
        pass


@pytest.mark.parametrize("kind", ["stt", "tts"])
async def test_route_audio_budget_avant_fournisseur(
    monkeypatch: pytest.MonkeyPatch, kind: Any
) -> None:
    monkeypatch.setattr(settings, "audio_stt_requests_per_day", 1)
    monkeypatch.setattr(settings, "audio_tts_chars_per_day", 1)
    provider = AsyncMock(return_value="parole" if kind == "stt" else b"mp3")
    monkeypatch.setattr(
        audio_service,
        "transcribe_audio" if kind == "stt" else "synthesize_speech",
        provider,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:

        async def request() -> Any:
            if kind == "stt":
                return await client.post(
                    "/api/chat/transcribe",
                    files={"file": ("note.wav", b"RIFF", "audio/wav")},
                )
            return await client.post("/api/chat/synthesize", json={"text": "a"})

        assert (await request()).status_code == 200
        assert (await request()).status_code == 429
    provider.assert_awaited_once()


@pytest.mark.parametrize("kind", ["stt", "tts"])
async def test_route_audio_panne_restitue_budget(
    monkeypatch: pytest.MonkeyPatch, kind: Any
) -> None:
    monkeypatch.setattr(settings, "audio_stt_requests_per_day", 1)
    monkeypatch.setattr(settings, "audio_tts_chars_per_day", 1)
    provider = AsyncMock(
        side_effect=[RuntimeError("panne"), "parole" if kind == "stt" else b"mp3"]
    )
    monkeypatch.setattr(
        audio_service,
        "transcribe_audio" if kind == "stt" else "synthesize_speech",
        provider,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:

        async def request() -> Any:
            if kind == "stt":
                return await client.post(
                    "/api/chat/transcribe",
                    files={"file": ("note.wav", b"RIFF", "audio/wav")},
                )
            return await client.post("/api/chat/synthesize", json={"text": "a"})

        assert (await request()).status_code == 503
        assert (await request()).status_code == 200


@pytest.mark.parametrize(
    "method", ["get_inactive_document_names", "get_inactive_metier_ids"]
)
async def test_activations_panne_db_ne_cache_pas_vide(
    monkeypatch: pytest.MonkeyPatch, method: Any
) -> None:
    context = MagicMock()
    context.__aenter__ = AsyncMock(side_effect=RuntimeError("DB indisponible"))
    monkeypatch.setattr(session_module, "async_session", lambda: context)
    with pytest.raises(ActivationIndisponibleError):
        await getattr(rag_service, method)()
    assert await cache_service.get("prosartisan:rag_config:inactive_docs") is None
    assert await cache_service.get("prosartisan:rag_config:inactive_metiers") is None


@pytest.mark.parametrize("stream", [False, True])
async def test_activations_panne_bloque_meme_cache(
    monkeypatch: pytest.MonkeyPatch, stream: Any
) -> None:
    await cache_service.cache_rag_response(
        "Question", None, {"reponse": "ancienne", "sources": []}
    )
    monkeypatch.setattr(
        rag_service,
        "get_inactive_document_names",
        AsyncMock(side_effect=ActivationIndisponibleError()),
    )
    search = AsyncMock()
    monkeypatch.setattr(rag_service, "search_context", search)
    method = (
        rag_service.generate_response_stream
        if stream
        else rag_service.generate_response
    )
    with pytest.raises(ActivationIndisponibleError):
        await method(question="Question")
    search.assert_not_awaited()


async def test_refresh_revocation_couvre_toute_la_duree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.middleware import auth as auth_middleware

    clock = MagicMock()
    clock.now.return_value.timestamp.return_value = 100.75
    reserve = AsyncMock(return_value=True)
    monkeypatch.setattr(auth_middleware, "datetime", clock)
    monkeypatch.setattr(cache_service, "set_if_absent", reserve)
    assert await auth_middleware.consume_refresh_token(
        {"jti": "last-second", "exp": 102}
    )
    assert reserve.call_args.kwargs["ttl_seconds"] == 2


@pytest.mark.parametrize("kind", ["stt", "tts"])
def test_websocket_budget_audio_avant_fournisseur(
    monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    reserve = AsyncMock(return_value=False)
    refund = AsyncMock()
    provider = AsyncMock()
    monkeypatch.setattr(cache_service, "reserve_budget", reserve)
    monkeypatch.setattr(quota_service, "consume_quota", AsyncMock(return_value=True))
    monkeypatch.setattr(quota_service, "restituer_quota", refund)
    monkeypatch.setattr(
        audio_service,
        "transcribe_audio" if kind == "stt" else "synthesize_speech",
        provider,
    )

    async def tokens() -> Any:
        yield "réponse"

    async def response(**kwargs: Any) -> Any:
        return [], tokens()

    monkeypatch.setattr(rag_service, "generate_response_stream", response)
    with TestClient(app).websocket_connect("/api/chat/ws") as websocket:
        if kind == "stt":
            websocket.send_json({"type": "voice", "audio": "UklGRg==", "format": "wav"})
            assert websocket.receive_json()["type"] == "error"
            refund.assert_awaited_once()
        else:
            websocket.send_json({"content": "question", "voice_output": True})
            messages = [websocket.receive_json() for _ in range(4)]
            assert [message["type"] for message in messages] == [
                "stream",
                "stream_end",
                "error",
                "voice_turn_completed",
            ]
            refund.assert_not_awaited()
        websocket.send_json({"type": "ping"})
        assert websocket.receive_json()["type"] == "pong"
    provider.assert_not_awaited()
    reserve.assert_awaited_once()
