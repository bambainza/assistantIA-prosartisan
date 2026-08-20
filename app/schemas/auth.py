"""Schémas Pydantic : Authentification (Register, Login, Token, Google OAuth)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

# ── Profil Utilisateur ──


class UserProfile(BaseModel):
    """Informations publiques de l'utilisateur connecté."""

    id: uuid.UUID
    email: str | None = None
    nom: str | None = None
    telephone: str | None = None
    avatar_url: str | None = None
    auth_provider: str = "local"
    type_abonnement: str = "FREE"
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── Inscription ──


class RegisterRequest(BaseModel):
    """Corps de requête pour l'inscription par email/mot de passe."""

    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    nom: str | None = None
    telephone: str | None = None


class RegisterResponse(BaseModel):
    """Réponse après inscription réussie."""

    id: uuid.UUID
    email: str
    nom: str | None = None
    message: str = "Inscription réussie"


# ── Connexion ──


class LoginRequest(BaseModel):
    """Corps de requête pour la connexion par email/mot de passe."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Réponse contenant les tokens JWT."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # secondes
    user: UserProfile


class RefreshRequest(BaseModel):
    """Corps de requête pour rafraîchir un token."""

    refresh_token: str


# ── Google OAuth ──


class GoogleAuthRequest(BaseModel):
    """Corps de requête pour l'authentification Google OAuth 2.0."""

    credential: str  # Google ID Token (JWT from Google Sign-In)
