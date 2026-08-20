"""
Router Auth : Enregistrement, connexion locale, Google OAuth 2.0, rafraîchissement des tokens et profil utilisateur.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db
from app.middleware.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user_id,
    hash_password,
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
    UserProfile,
)

router = APIRouter(prefix="/api/auth", tags=["Authentification"])


async def verify_google_token(token: str) -> dict[str, Any] | None:
    """Valide le token Google ID et retourne le profil de l'utilisateur."""
    # Fallback pour le développement / simulateur local
    if token.startswith("mock_google_"):
        email = token.replace("mock_google_", "")
        return {
            "sub": f"google_{email}",
            "email": email,
            "name": f"Artisan {email.split('@')[0].capitalize()}",
            "picture": "https://www.gravatar.com/avatar/00000000000000000000000000000000?d=mp",
        }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://oauth2.googleapis.com/tokeninfo?id_token={token}",
                timeout=5.0
            )
            if response.status_code == 200:
                return response.json()
    except Exception:
        pass
    return None


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
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
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Connecte un artisan et retourne un token JWT."""
    stmt = select(User).where(User.email == payload.email)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    
    if not user or not user.password_hash or user.auth_provider != "local":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiants incorrects.",
        )
        
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiants incorrects.",
        )
        
    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})
    
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
        if decoded.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token de rafraîchissement requis.",
            )
        user_id_str = decoded.get("sub")
        if not user_id_str:
            raise HTTPException(
                status_code=status.HTTP_418_IM_A_TEAPOT,  # placeholder
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de rafraîchissement invalide ou expiré.",
        ) from e

    user_id = uuid.UUID(user_id_str)
    stmt = select(User).where(User.id == user_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur non trouvé.",
        )

    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": settings.jwt_expiration_minutes * 60,
        "user": user,
    }


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
