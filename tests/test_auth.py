"""Tests pour l'authentification (JWT, Google OAuth 2.0)."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import get_db
from app.main import app
from app.middleware.auth import create_access_token, hash_password
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
async def test_google_auth_new_user():
    """POST /api/auth/google crée un nouvel utilisateur si l'email n'existe pas."""
    payload = {"credential": "mock_google_google_user@example.com"}

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
