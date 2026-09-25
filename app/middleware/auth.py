"""Middleware d'authentification JWT pour FastAPI.

Fournit la dépendance `get_current_user` qui décode le token JWT
depuis le header Authorization et retourne l'utilisateur authentifié.
Fournit aussi `get_optional_user` pour les routes accessibles en mode anonyme.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt
from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.session import get_db
from app.models.role import Role
from app.models.user import User
from app.services.cache_service import cache_service

# ── JWT token management ──
ALGORITHM = settings.jwt_algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.jwt_expiration_minutes
REFRESH_TOKEN_EXPIRE_DAYS = 30

# Security scheme
bearer_scheme = HTTPBearer(auto_error=False)
ADMIN_SESSION_COOKIE = "prosartisan_admin_session"


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
    """Crée un token JWT de rafraîchissement (longue durée), avec un identifiant
    unique (`jti`) permettant de le révoquer individuellement (logout, rotation)."""
    to_encode = data.copy()
    expire = datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh", "jti": str(uuid.uuid4())})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=ALGORITHM)


def _revoked_jti_cache_key(jti: str) -> str:
    return f"prosartisan:revoked_jti:{jti}"


_REVOKED_TOKENS_COUNTER_KEY = "prosartisan:security:revoked_tokens_total"
_SECURITY_COUNTER_TTL_SECONDS = 30 * 86400


async def revoke_refresh_token(payload: dict[str, Any]) -> None:
    """Ajoute le `jti` d'un refresh token décodé à la liste noire (Redis, TTL =
    durée de vie restante du token). Un token sans `jti` (ancien format, avant
    l'introduction de la révocation) ne peut pas être révoqué individuellement."""
    jti = payload.get("jti")
    if not jti:
        return
    exp = payload.get("exp")
    now = datetime.now(UTC).timestamp()
    ttl_seconds = max(int(exp - now), 1) if exp else REFRESH_TOKEN_EXPIRE_DAYS * 86400
    await cache_service.set(_revoked_jti_cache_key(jti), "1", ttl_seconds=ttl_seconds)
    await cache_service.increment(
        _REVOKED_TOKENS_COUNTER_KEY, _SECURITY_COUNTER_TTL_SECONDS
    )


async def is_refresh_token_revoked(payload: dict[str, Any]) -> bool:
    """Vérifie si le `jti` d'un refresh token décodé a été révoqué (logout, rotation)."""
    jti = payload.get("jti")
    if not jti:
        return False
    return await cache_service.get(_revoked_jti_cache_key(jti)) is not None


def decode_token(token: str) -> dict[str, Any]:
    """Décode et valide un token JWT. Lève une exception si invalide."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
        return payload
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_user_id_from_token(token: str) -> uuid.UUID:
    """Extrait le user_id d'un token JWT **d'accès** décodé.

    Seuls les tokens `type == "access"` ouvrent les routes protégées : un
    refresh token (30 jours, révocable uniquement via `/auth/refresh` et
    `/auth/logout`) ne doit jamais servir d'identifiant d'accès, sinon un
    token volé resterait utilisable après la déconnexion.
    """
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token d'accès requis.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide : identifiant utilisateur manquant.",
        )
    try:
        return uuid.UUID(user_id_str)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide : identifiant utilisateur malformé.",
        ) from exc


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    admin_session: str | None = Cookie(default=None, alias=ADMIN_SESSION_COOKIE),
) -> uuid.UUID:
    """Dépendance FastAPI : extrait et valide le user_id depuis le JWT.

    Retourne le UUID de l'utilisateur authentifié.
    Lève HTTP 401 si le token est absent ou invalide.
    """
    token = credentials.credentials if credentials is not None else admin_session
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return get_user_id_from_token(token)


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


def require_permission(
    permission_code: str,
) -> Callable[..., Coroutine[Any, Any, uuid.UUID]]:
    """Fabrique une dépendance FastAPI exigeant une permission RBAC précise.

    Un compte `is_admin=True` sans rôle assigné conserve l'accès complet
    (compatibilité descendante avec les comptes admin créés avant l'introduction
    du RBAC). Un compte avec un rôle assigné n'a accès qu'aux permissions
    explicitement accordées à ce rôle.
    """

    async def _dependency(
        user_id: uuid.UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_db),
    ) -> uuid.UUID:
        stmt = (
            select(User)
            .options(selectinload(User.role).selectinload(Role.permissions))
            .where(User.id == user_id)
        )
        res = await db.execute(stmt)
        user = res.scalar_one_or_none()
        if not user or not user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Accès interdit : privilèges administrateur requis.",
            )
        if user.role is None:
            # Admin hérité sans rôle RBAC assigné : accès complet par compatibilité.
            return user_id
        permission_codes = {p.code for p in user.role.permissions}
        if permission_code not in permission_codes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission_code}' requise pour cette action.",
            )
        return user_id

    return _dependency
