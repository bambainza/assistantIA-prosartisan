"""
Router Auth : Enregistrement, connexion locale, Google OAuth 2.0, rafraîchissement des tokens et profil utilisateur.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db
from app.middleware.auth import (
    ADMIN_SESSION_COOKIE,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user_id,
    hash_password,
    is_refresh_token_revoked,
    revoke_refresh_token,
    verify_password,
)
from app.models.quota import QuotaUtilisateur
from app.models.user import User
from app.schemas.auth import (
    GoogleAuthRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
    TotpCodeRequest,
    TotpSetupResponse,
    UserProfile,
)
from app.services.cache_service import cache_service
from app.services.totp_service import totp_service

# Compteur "glissant" (30 jours) des tentatives de connexion échouées, exposé
# au dashboard sécurité admin (voir app.routers.admin.get_security_stats).
_SECURITY_COUNTER_TTL_SECONDS = 30 * 86400
_LOGIN_FAILED_COUNTER_KEY = "prosartisan:security:login_failed_total"

router = APIRouter(prefix="/api/auth", tags=["Authentification"])


@router.get("/google/config")
async def google_auth_config() -> dict[str, str | bool]:
    """Expose uniquement l'identifiant OAuth public requis par Google GIS."""
    return {
        "enabled": bool(settings.google_client_id),
        "client_id": settings.google_client_id,
    }


async def verify_google_token(token: str) -> dict[str, Any] | None:
    """Valide le token Google ID et retourne le profil de l'utilisateur."""
    if not settings.google_client_id:
        return None
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": token},
                timeout=5.0,
            )
            if response.status_code == 200:
                profile = response.json()
                valid_issuers = {"accounts.google.com", "https://accounts.google.com"}
                if (
                    profile.get("aud") == settings.google_client_id
                    and profile.get("iss") in valid_issuers
                    and str(profile.get("email_verified", "")).lower() == "true"
                ):
                    return profile
    except Exception:
        pass
    return None


@router.post(
    "/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED
)
async def register(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Enregistre un nouvel artisan avec son email et mot de passe."""
    # Vérifier si l'email existe déjà
    stmt = select(User).where(User.email == payload.email)
    res = await db.execute(stmt)
    existing_user = res.scalar_one_or_none()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Un compte avec cette adresse email existe déjà.",
        )

    # Si téléphone fourni, vérifier s'il existe déjà
    if payload.telephone:
        stmt_tel = select(User).where(User.telephone == payload.telephone)
        res_tel = await db.execute(stmt_tel)
        existing_tel = res_tel.scalar_one_or_none()
        if existing_tel:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ce numéro de téléphone est déjà associé à un autre compte.",
            )

    new_user = User(
        id=uuid.uuid4(),
        email=payload.email,
        telephone=payload.telephone,
        nom=payload.nom,
        password_hash=hash_password(payload.password),
        auth_provider="local",
        type_abonnement="FREE",
    )
    db.add(new_user)

    # Créer le quota par défaut
    new_quota = QuotaUtilisateur(
        user_id=new_user.id,
        requetes_restantes_gratuites=settings.max_questions_gratuites_par_jour,
    )
    db.add(new_quota)

    await db.commit()
    await db.refresh(new_user)

    return new_user


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Connecte un artisan et retourne un token JWT."""
    email_clean = payload.email.strip().lower()
    stmt = select(User).where(func.lower(User.email) == email_clean)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user or not user.password_hash or user.auth_provider != "local":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiants incorrects.",
        )

    if not verify_password(payload.password, user.password_hash):
        await cache_service.increment(
            _LOGIN_FAILED_COUNTER_KEY, _SECURITY_COUNTER_TTL_SECONDS
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiants incorrects.",
        )

    if user.is_admin and user.totp_enabled:
        if not payload.totp_code:
            await cache_service.increment(
                _LOGIN_FAILED_COUNTER_KEY, _SECURITY_COUNTER_TTL_SECONDS
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Code d'authentification à deux facteurs requis.",
            )
        if not totp_service.verify_code(user.totp_secret or "", payload.totp_code):
            await cache_service.increment(
                _LOGIN_FAILED_COUNTER_KEY, _SECURITY_COUNTER_TTL_SECONDS
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Code d'authentification à deux facteurs invalide.",
            )

    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    if user.is_admin:
        response.set_cookie(
            key=ADMIN_SESSION_COOKIE,
            value=access_token,
            max_age=settings.jwt_expiration_minutes * 60,
            httponly=True,
            secure=settings.is_production,
            samesite="strict",
            path="/",
        )
    else:
        response.delete_cookie(key=ADMIN_SESSION_COOKIE, path="/")

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": settings.jwt_expiration_minutes * 60,
        "user": user,
    }


@router.post("/google", response_model=TokenResponse)
async def google_auth(
    payload: GoogleAuthRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """S'enregistre ou se connecte via Google OAuth 2.0."""
    google_profile = await verify_google_token(payload.credential)
    if not google_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token Google invalide ou expiré.",
        )

    google_id = google_profile.get("sub")
    email = google_profile.get("email")
    nom = google_profile.get("name")
    picture = google_profile.get("picture")

    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossible de récupérer l'adresse email de Google.",
        )

    # 1. Tenter de trouver l'utilisateur par google_id
    stmt = select(User).where(User.google_id == google_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user:
        # 2. Sinon, tenter de trouver par email
        stmt_email = select(User).where(User.email == email)
        res_email = await db.execute(stmt_email)
        user = res_email.scalar_one_or_none()

        if user:
            # Lier le compte Google
            user.google_id = google_id
            user.avatar_url = picture
            if not user.nom:
                user.nom = nom
            await db.commit()
        else:
            # 3. Créer un nouvel utilisateur
            user = User(
                id=uuid.uuid4(),
                email=email,
                nom=nom,
                avatar_url=picture,
                google_id=google_id,
                auth_provider="google",
                type_abonnement="FREE",
            )
            db.add(user)

            # Créer le quota
            quota = QuotaUtilisateur(
                user_id=user.id,
                requetes_restantes_gratuites=settings.max_questions_gratuites_par_jour,
            )
            db.add(quota)
            await db.commit()
            await db.refresh(user)

    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": settings.jwt_expiration_minutes * 60,
        "user": user,
    }


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Renouvelle le token d'accès avec un token de rafraîchissement valide."""
    try:
        decoded = decode_token(payload.refresh_token)
    except HTTPException as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de rafraîchissement invalide ou expiré.",
        ) from exc

    if decoded.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de rafraîchissement requis.",
        )

    if await is_refresh_token_revoked(decoded):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de rafraîchissement révoqué (déconnexion effectuée).",
        )

    user_id_str = decoded.get("sub")
    try:
        user_id = uuid.UUID(user_id_str) if user_id_str else None
    except (ValueError, TypeError):
        user_id = None

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de rafraîchissement invalide : identifiant manquant.",
        )

    stmt = select(User).where(User.id == user_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur non trouvé.",
        )

    # Rotation : l'ancien refresh token est révoqué dès qu'il a servi une fois,
    # même s'il n'était pas encore expiré (usage unique — limite le rejeu en
    # cas de vol du token).
    await revoke_refresh_token(decoded)

    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": settings.jwt_expiration_minutes * 60,
        "user": user,
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def logout(payload: RefreshRequest) -> None:
    """Révoque le refresh token fourni : il ne pourra plus servir à renouveler l'accès."""
    try:
        decoded = decode_token(payload.refresh_token)
    except HTTPException:
        # Un token déjà invalide/expiré n'a pas besoin d'être révoqué explicitement.
        return
    await revoke_refresh_token(decoded)
    return


@router.post(
    "/session/logout", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
async def session_logout(response: Response) -> None:
    """Ferme la session navigateur HttpOnly du back-office."""
    response.delete_cookie(
        key=ADMIN_SESSION_COOKIE,
        path="/",
        secure=settings.is_production,
        httponly=True,
        samesite="strict",
    )


@router.post("/totp/setup", response_model=TotpSetupResponse)
async def totp_setup(
    current_user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Génère un nouveau secret TOTP à provisionner (QR code côté client).

    La 2FA n'est activée qu'après confirmation d'un code valide via
    `/totp/enable` : générer un secret seul ne suffit pas à l'activer.
    """
    stmt = select(User).where(User.id == current_user_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable."
        )
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La 2FA est réservée aux comptes administrateur.",
        )

    secret = totp_service.generate_secret()
    user.totp_secret = secret
    user.totp_enabled = False
    await db.commit()

    return {
        "secret": secret,
        "otpauth_uri": totp_service.get_provisioning_uri(secret, user.email or ""),
    }


@router.post(
    "/totp/enable", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
async def totp_enable(
    payload: TotpCodeRequest,
    current_user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Confirme un code TOTP valide pour activer définitivement la 2FA."""
    stmt = select(User).where(User.id == current_user_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if not user or not user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Aucun secret TOTP en attente : lancez /totp/setup d'abord.",
        )
    if not totp_service.verify_code(user.totp_secret, payload.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Code TOTP invalide.",
        )
    user.totp_enabled = True
    await db.commit()


@router.post(
    "/totp/disable", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
async def totp_disable(
    payload: TotpCodeRequest,
    current_user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Désactive la 2FA après confirmation d'un dernier code valide."""
    stmt = select(User).where(User.id == current_user_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if not user or not user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La 2FA n'est pas activée sur ce compte.",
        )
    if not totp_service.verify_code(user.totp_secret or "", payload.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Code TOTP invalide.",
        )
    user.totp_enabled = False
    user.totp_secret = None
    await db.commit()


@router.get("/me", response_model=UserProfile)
async def get_me(
    current_user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retourne le profil de l'artisan actuellement connecté."""
    stmt = select(User).where(User.id == current_user_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profil introuvable.",
        )
    return user
