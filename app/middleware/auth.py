"""Middleware d'authentification JWT pour FastAPI.

Fournit la dépendance `get_current_user` qui décode le token JWT
depuis le header Authorization et retourne l'utilisateur authentifié.
Fournit aussi `get_optional_user` pour les routes accessibles en mode anonyme.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.db.session import get_db
from app.models.user import User

# ── JWT token management ──
ALGORITHM = settings.jwt_algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.jwt_expiration_minutes
REFRESH_TOKEN_EXPIRE_DAYS = 30

# Security scheme
bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """Hash un mot de passe en clair avec bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Vérifie un mot de passe contre son hash bcrypt."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except Exception:
        return False


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """Crée un token JWT d'accès."""
    to_encode = data.copy()
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=ALGORITHM)


def create_refresh_token(data: dict[str, Any]) -> str:
    """Crée un token JWT de rafraîchissement (longue durée)."""
    to_encode = data.copy()
    expire = datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Décode et valide un token JWT. Lève une exception si invalide."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_user_id_from_token(token: str) -> uuid.UUID:
    """Extrait le user_id d'un token JWT décodé."""
    payload = decode_token(token)
    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide : identifiant utilisateur manquant.",
        )
    return uuid.UUID(user_id_str)


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> uuid.UUID:
    """Dépendance FastAPI : extrait et valide le user_id depuis le JWT.

    Retourne le UUID de l'utilisateur authentifié.
    Lève HTTP 401 si le token est absent ou invalide.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return get_user_id_from_token(credentials.credentials)


async def get_optional_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> uuid.UUID | None:
    """Dépendance FastAPI : extrait le user_id si un JWT valide est fourni.

    Retourne None si pas de token (mode anonyme).
    Utile pour les routes accessibles en mode connecté ET déconnecté.
    """
    if credentials is None:
        return None
    try:
        return get_user_id_from_token(credentials.credentials)
    except HTTPException:
        return None


async def get_current_admin_user_id(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> uuid.UUID:
    """Dépendance FastAPI : extrait et valide le user_id de l'admin depuis le JWT.

    Retourne le UUID de l'admin.
    Lève HTTP 403 si l'utilisateur n'a pas les privilèges admin.
    """
    stmt = select(User).where(User.id == user_id, User.is_admin == True)
    res = await db.execute(stmt)
    admin = res.scalar_one_or_none()
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès interdit : privilèges administrateur requis.",
        )
    return user_id
