"""Tests pour l'authentification (JWT, Google OAuth 2.0)."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.db.session import get_db
from app.main import app
from app.middleware.auth import (
    ADMIN_SESSION_COOKIE,
    CSRF_COOKIE,
    WEB_ACCESS_COOKIE,
    WEB_REFRESH_COOKIE,
    create_access_token,
    create_refresh_token,
    hash_password,
)
from app.models.user import User


@pytest.mark.asyncio
async def test_register_user_success():
    """POST /api/auth/register crée un nouvel utilisateur avec succès."""
    payload = {
        "email": "test_artisan@example.com",
        "password": "strongpassword123",
        "nom": "Koffi Justin",
        "telephone": "+22501020304",
    }

    async def custom_mock_db():
        session = MagicMock()
        # Simuler qu'aucun utilisateur n'existe avec cet email
        session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )
        session.commit = AsyncMock()
        session.add = MagicMock()
        session.refresh = AsyncMock()
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/auth/register", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "test_artisan@example.com"
        assert data["nom"] == "Koffi Justin"
        assert "id" in data
    finally:
        from tests.conftest import mock_get_db

        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_register_user_already_exists():
    """POST /api/auth/register échoue si l'utilisateur existe déjà."""
    payload = {
        "email": "existing@example.com",
        "password": "password123",
    }

    mock_user = User(id=uuid.uuid4(), email="existing@example.com")

    async def custom_mock_db():
        session = MagicMock()
        # Simuler qu'un utilisateur existe
        session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_user))
        )
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/auth/register", json=payload)

        assert response.status_code == 400
        assert "existe déjà" in response.json()["detail"]
    finally:
        from tests.conftest import mock_get_db

        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_login_success():
    """POST /api/auth/login connecte l'utilisateur et retourne un token JWT."""
    payload = {"email": "test@example.com", "password": "mypassword"}

    mock_user = User(
        id=uuid.uuid4(),
        email="test@example.com",
        nom="Test User",
        password_hash=hash_password("mypassword"),
        auth_provider="local",
        type_abonnement="FREE",
        created_at=datetime.now(UTC),
    )

    async def custom_mock_db():
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_user))
        )
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/auth/login", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["email"] == "test@example.com"
    finally:
        from tests.conftest import mock_get_db

        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_web_login_garde_les_jetons_dans_des_cookies_httponly():
    """Le navigateur ne reçoit jamais les JWT dans un JSON lisible."""
    mock_user = User(
        id=uuid.uuid4(),
        email="web@example.com",
        nom="Web User",
        password_hash=hash_password("mypassword"),
        auth_provider="local",
        type_abonnement="FREE",
        created_at=datetime.now(UTC),
    )

    async def custom_mock_db():
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_user))
        )
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/auth/web/login",
                json={"email": "web@example.com", "password": "mypassword"},
            )

        assert response.status_code == 200
        assert "access_token" not in response.json()
        assert "refresh_token" not in response.json()
        cookies = response.headers.get_list("set-cookie")
        assert any(
            WEB_ACCESS_COOKIE in value and "HttpOnly" in value for value in cookies
        )
        assert any(
            WEB_REFRESH_COOKIE in value and "HttpOnly" in value for value in cookies
        )
        assert any(
            CSRF_COOKIE in value and "HttpOnly" not in value for value in cookies
        )
    finally:
        from tests.conftest import mock_get_db

        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_web_session_exige_csrf_sur_une_mutation():
    """Une session cookie ne peut pas effectuer de mutation cross-site."""
    access_token = create_access_token(data={"sub": str(uuid.uuid4())})
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set(WEB_ACCESS_COOKIE, access_token)
        client.cookies.set(CSRF_COOKIE, "csrf-test")
        rejected = await client.post("/api/auth/web/logout")
        accepted = await client.post(
            "/api/auth/web/logout", headers={"X-CSRF-Token": "csrf-test"}
        )

    assert rejected.status_code == 403
    assert accepted.status_code == 204


@pytest.mark.asyncio
async def test_login_incorrect_password():
    """POST /api/auth/login échoue si le mot de passe est faux."""
    payload = {"email": "test@example.com", "password": "wrongpassword"}

    mock_user = User(
        id=uuid.uuid4(),
        email="test@example.com",
        password_hash=hash_password("mypassword"),
        auth_provider="local",
    )

    async def custom_mock_db():
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_user))
        )
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/auth/login", json=payload)

        assert response.status_code == 401
        assert "incorrects" in response.json()["detail"]
    finally:
        from tests.conftest import mock_get_db

        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_google_auth_new_user(monkeypatch):
    """POST /api/auth/google crée un nouvel utilisateur si l'email n'existe pas."""
    payload = {"credential": "valid-provider-token"}

    async def mock_verify_google_token(token: str):
        assert token == "valid-provider-token"
        return {
            "sub": "google-123",
            "email": "google_user@example.com",
            "name": "Google User",
            "picture": None,
        }

    monkeypatch.setattr(
        "app.routers.auth.verify_google_token", mock_verify_google_token
    )

    async def custom_mock_db():
        session = MagicMock()
        # Simuler qu'aucun utilisateur n'est trouvé
        session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )
        session.commit = AsyncMock()
        session.add = MagicMock()
        session.refresh = AsyncMock()
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/auth/google", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["email"] == "google_user@example.com"
        assert data["user"]["auth_provider"] == "google"
    finally:
        from tests.conftest import mock_get_db

        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_google_auth_rejette_un_ancien_jeton_mock(monkeypatch):
    """Le préfixe historique de test ne doit jamais authentifier un compte."""
    provider_get = AsyncMock(return_value=MagicMock(status_code=400))
    monkeypatch.setattr("httpx.AsyncClient.get", provider_get)
    monkeypatch.setattr(settings, "google_client_id", "client-id-test")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/auth/google",
            json={"credential": "mock_google_admin@example.com"},
        )

    assert response.status_code == 400
    provider_get.assert_awaited_once()


@pytest.mark.asyncio
async def test_google_auth_config_n_expose_que_identifiant_public(monkeypatch):
    monkeypatch.setattr(
        settings, "google_client_id", "public.apps.googleusercontent.com"
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/auth/google/config")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": True,
        "client_id": "public.apps.googleusercontent.com",
    }


@pytest.mark.asyncio
async def test_login_admin_rejette_les_anciens_mots_de_passe_universels():
    """Un administrateur doit toujours valider son propre hash."""
    mock_user = User(
        id=uuid.uuid4(),
        email="admin-secure@example.com",
        password_hash=hash_password("mot-de-passe-reel"),
        auth_provider="local",
        is_admin=True,
    )

    async def custom_mock_db():
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_user))
        )
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for password in ("admin123", "dev_admin_password", "admin"):
                response = await client.post(
                    "/api/auth/login",
                    json={"email": mock_user.email, "password": password},
                )
                assert response.status_code == 401
    finally:
        from tests.conftest import mock_get_db

        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_login_admin_emet_cookie_httponly_et_deconnexion_le_supprime():
    """La session du back-office ne doit pas être lisible par JavaScript."""
    mock_user = User(
        id=uuid.uuid4(),
        email="cookie-admin@example.com",
        password_hash=hash_password("mot-de-passe-fort"),
        auth_provider="local",
        is_admin=True,
        type_abonnement="FREE",
    )

    async def custom_mock_db():
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_user))
        )
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            login_response = await client.post(
                "/api/auth/login",
                json={
                    "email": mock_user.email,
                    "password": "mot-de-passe-fort",
                },
            )
            cookie_header = login_response.headers["set-cookie"]
            assert f"{ADMIN_SESSION_COOKIE}=" in cookie_header
            assert "HttpOnly" in cookie_header
            assert "SameSite=strict" in cookie_header

            logout_response = await client.post("/api/auth/session/logout")
            assert logout_response.status_code == 204
            assert f"{ADMIN_SESSION_COOKIE}=" in logout_response.headers["set-cookie"]
            assert "Max-Age=0" in logout_response.headers["set-cookie"]
    finally:
        from tests.conftest import mock_get_db

        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_get_me_protected():
    """GET /api/auth/me retourne les informations de l'utilisateur connecté."""
    user_id = uuid.uuid4()
    access_token = create_access_token(data={"sub": str(user_id)})

    mock_user = User(
        id=user_id,
        email="me@example.com",
        nom="Me",
        auth_provider="local",
        type_abonnement="premium",
        created_at=datetime.now(UTC),
    )

    async def custom_mock_db():
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_user))
        )
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    try:
        transport = ASGITransport(app=app)
        headers = {"Authorization": f"Bearer {access_token}"}
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/auth/me", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "me@example.com"
        assert data["type_abonnement"] == "premium"
        # Un User non encore inséré expose is_admin=None ; le schéma doit
        # renvoyer un booléen valide (False) et non provoquer une 500.
        assert data["is_admin"] is False
    finally:
        from tests.conftest import mock_get_db

        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_refresh_token_success():
    """POST /api/auth/refresh échange un refresh token valide contre de nouveaux jetons."""
    user_id = uuid.uuid4()
    refresh_token = create_refresh_token(data={"sub": str(user_id)})
    mock_user = User(
        id=user_id,
        email="r@example.com",
        auth_provider="local",
        type_abonnement="FREE",
    )

    async def custom_mock_db():
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_user))
        )
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/auth/refresh", json={"refresh_token": refresh_token}
            )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
    finally:
        from tests.conftest import mock_get_db

        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_refresh_rejette_un_access_token():
    """Un access token présenté à /refresh est refusé (mauvais type), sans 418 ni 500."""
    access_token = create_access_token(data={"sub": str(uuid.uuid4())})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/auth/refresh", json={"refresh_token": access_token}
        )

    assert response.status_code == 401
    assert "rafraîchissement requis" in response.json()["detail"]


@pytest.mark.asyncio
async def test_refresh_rejette_un_token_invalide():
    """Un jeton illisible renvoie 401 (et pas une 500)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/auth/refresh", json={"refresh_token": "pas-un-jwt"}
        )

    assert response.status_code == 401
    assert "invalide ou expiré" in response.json()["detail"]


@pytest.mark.asyncio
async def test_logout_revoque_le_refresh_token():
    """Régression sécurité : après /logout, le refresh token révoqué ne doit
    plus jamais permettre de renouveler l'accès (sans ce garde-fou, un
    attaquant en possession d'un refresh token volé pourrait continuer à
    l'utiliser après que la victime se soit "déconnectée")."""
    user_id = uuid.uuid4()
    refresh_token = create_refresh_token(data={"sub": str(user_id)})
    mock_user = User(id=user_id, email="logout@example.com", auth_provider="local")

    async def custom_mock_db():
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_user))
        )
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res_logout = await client.post(
                "/api/auth/logout", json={"refresh_token": refresh_token}
            )
            assert res_logout.status_code == 204

            res_refresh = await client.post(
                "/api/auth/refresh", json={"refresh_token": refresh_token}
            )
        assert res_refresh.status_code == 401
        assert "révoqué" in res_refresh.json()["detail"]
    finally:
        from tests.conftest import mock_get_db

        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_refresh_token_rotation_usage_unique():
    """Un refresh token déjà utilisé une fois (rotation) ne peut pas resservir."""
    user_id = uuid.uuid4()
    refresh_token = create_refresh_token(data={"sub": str(user_id)})
    mock_user = User(
        id=user_id,
        email="rotate@example.com",
        auth_provider="local",
        type_abonnement="FREE",
    )

    async def custom_mock_db():
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_user))
        )
        yield session

    app.dependency_overrides[get_db] = custom_mock_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res_first = await client.post(
                "/api/auth/refresh", json={"refresh_token": refresh_token}
            )
            assert res_first.status_code == 200

            # Rejouer le MÊME refresh token (déjà consommé) doit échouer.
            res_replay = await client.post(
                "/api/auth/refresh", json={"refresh_token": refresh_token}
            )
        assert res_replay.status_code == 401
        assert "révoqué" in res_replay.json()["detail"]
    finally:
        from tests.conftest import mock_get_db

        app.dependency_overrides[get_db] = mock_get_db
