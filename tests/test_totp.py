"""Tests pour l'authentification à deux facteurs (TOTP) des comptes admin.

Régression sécurité : un compte admin avec `totp_enabled=True` ne doit
JAMAIS pouvoir se connecter sans code TOTP valide, même avec le bon mot de
passe — ces tests échoueraient sans le garde-fou ajouté dans
`app.routers.auth.login`.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pyotp
import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import get_db
from app.main import app
from app.middleware.auth import create_access_token, hash_password
from app.models.user import User
from tests.conftest import mock_get_db


@pytest.fixture
def admin_user_no_totp():
    return User(
        id=uuid.uuid4(),
        email="totp_admin@prosartisan.ci",
        nom="Admin TOTP",
        password_hash=hash_password("adminpass123"),
        auth_provider="local",
        is_admin=True,
        type_abonnement="FREE",
        totp_enabled=False,
        totp_secret=None,
    )


@pytest.fixture
def totp_secret():
    return pyotp.random_base32()


@pytest.fixture
def admin_user_with_totp(totp_secret):
    return User(
        id=uuid.uuid4(),
        email="totp_admin2@prosartisan.ci",
        nom="Admin TOTP Actif",
        password_hash=hash_password("adminpass123"),
        auth_provider="local",
        is_admin=True,
        type_abonnement="FREE",
        totp_enabled=True,
        totp_secret=totp_secret,
    )


def _single_return_db(value):
    async def custom_mock_db():
        session = MagicMock()
        session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=value))
        )
        session.commit = AsyncMock()
        yield session

    return custom_mock_db


@pytest.mark.asyncio
async def test_totp_setup_refuse_non_admin():
    """Un compte non-admin ne peut pas activer la 2FA (réservée au back-office)."""
    non_admin = User(
        id=uuid.uuid4(), email="artisan_totp@prosartisan.ci", is_admin=False
    )
    app.dependency_overrides[get_db] = _single_return_db(non_admin)
    token = create_access_token(data={"sub": str(non_admin.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/api/auth/totp/setup", headers={"Authorization": f"Bearer {token}"}
            )
        assert res.status_code == 403
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_totp_setup_puis_enable_admin(admin_user_no_totp):
    """Un admin peut générer un secret TOTP puis l'activer avec un code valide."""
    app.dependency_overrides[get_db] = _single_return_db(admin_user_no_totp)
    token = create_access_token(data={"sub": str(admin_user_no_totp.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res_setup = await client.post(
                "/api/auth/totp/setup", headers={"Authorization": f"Bearer {token}"}
            )
            assert res_setup.status_code == 200
            secret = res_setup.json()["secret"]
            assert "otpauth://" in res_setup.json()["otpauth_uri"]

            valid_code = pyotp.TOTP(secret).now()
            res_enable = await client.post(
                "/api/auth/totp/enable",
                headers={"Authorization": f"Bearer {token}"},
                json={"code": valid_code},
            )
        assert res_enable.status_code == 204
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_totp_enable_refuse_code_invalide(admin_user_no_totp):
    """Un code TOTP incorrect ne peut pas activer la 2FA."""
    admin_user_no_totp.totp_secret = pyotp.random_base32()
    app.dependency_overrides[get_db] = _single_return_db(admin_user_no_totp)
    token = create_access_token(data={"sub": str(admin_user_no_totp.id)})
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/api/auth/totp/enable",
                headers={"Authorization": f"Bearer {token}"},
                json={"code": "000000"},
            )
        assert res.status_code == 400
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_login_admin_avec_totp_sans_code_refuse(admin_user_with_totp):
    """Un admin avec 2FA activée ne peut pas se connecter sans code TOTP."""
    app.dependency_overrides[get_db] = _single_return_db(admin_user_with_totp)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/api/auth/login",
                json={
                    "email": admin_user_with_totp.email,
                    "password": "adminpass123",
                },
            )
        assert res.status_code == 401
        assert "requis" in res.json()["detail"]
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_login_admin_avec_totp_code_invalide_refuse(admin_user_with_totp):
    """Un admin avec 2FA activée ne peut pas se connecter avec un mauvais code TOTP."""
    app.dependency_overrides[get_db] = _single_return_db(admin_user_with_totp)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/api/auth/login",
                json={
                    "email": admin_user_with_totp.email,
                    "password": "adminpass123",
                    "totp_code": "000000",
                },
            )
        assert res.status_code == 401
        assert "invalide" in res.json()["detail"]
    finally:
        app.dependency_overrides[get_db] = mock_get_db


@pytest.mark.asyncio
async def test_login_admin_avec_totp_code_valide_reussit(
    admin_user_with_totp, totp_secret
):
    """Un admin avec 2FA activée se connecte avec succès en fournissant le bon code."""
    app.dependency_overrides[get_db] = _single_return_db(admin_user_with_totp)
    try:
        valid_code = pyotp.TOTP(totp_secret).now()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/api/auth/login",
                json={
                    "email": admin_user_with_totp.email,
                    "password": "adminpass123",
                    "totp_code": valid_code,
                },
            )
        assert res.status_code == 200
        assert "access_token" in res.json()
    finally:
        app.dependency_overrides[get_db] = mock_get_db
