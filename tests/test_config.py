"""Tests pour la validation de configuration (garde-fous production)."""

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.main import docs_urls

_CONFIG_PROD_FORTE = {
    "app_env": "production",
    "app_debug": False,
    "app_secret_key": "s3cret-app-key-quarante-caracteres-mini-xx",
    "jwt_secret_key": "s3cret-jwt-key-quarante-caracteres-mini-xxx",
    "mobile_money_secret_key": "hmac-mobile-money-quarante-caracteres-xx",
    "db_password": "un-mot-de-passe-postgres-solide",
    "cors_allowed_origins": "https://app.prosartisan.ci",
    "vapid_private_key": "propre-cle-vapid-generee-pour-la-production-xx",
    "mistral_api_key": "cle-mistral-de-production-valide",
    "gemini_api_key": "AIza-placeholder",
}


def test_dev_tolere_les_valeurs_par_defaut() -> None:
    settings = Settings(_env_file=None, app_env="development")
    assert settings.is_production is False


def test_prod_rejette_les_secrets_faibles() -> None:
    with pytest.raises(ValidationError, match="Configuration de production invalide"):
        Settings(_env_file=None, app_env="production", app_debug=False)


def test_prod_rejette_cors_joker() -> None:
    config = {**_CONFIG_PROD_FORTE, "cors_allowed_origins": "*"}
    with pytest.raises(ValidationError, match="CORS_ALLOWED_ORIGINS"):
        Settings(_env_file=None, **config)


def test_prod_rejette_app_debug_actif() -> None:
    config = {**_CONFIG_PROD_FORTE, "app_debug": True}
    with pytest.raises(ValidationError, match="APP_DEBUG"):
        Settings(_env_file=None, **config)


def test_prod_rejette_la_cle_vapid_de_dev() -> None:
    config = {**_CONFIG_PROD_FORTE, "vapid_private_key": ""}
    with pytest.raises(ValidationError, match="VAPID_PRIVATE_KEY"):
        Settings(_env_file=None, **config)


def test_prod_rejette_l_absence_de_cle_ia() -> None:
    """Sans clé IA, la production servirait des réponses et devis factices."""
    config = {
        **_CONFIG_PROD_FORTE,
        "mistral_api_key": "sk-placeholder",
        "gemini_api_key": "AIza-placeholder",
    }
    with pytest.raises(ValidationError, match="MISTRAL_API_KEY ou GEMINI_API_KEY"):
        Settings(_env_file=None, **config)


def test_prod_rejette_une_cle_ia_d_exemple() -> None:
    config = {
        **_CONFIG_PROD_FORTE,
        "mistral_api_key": "votre_cle_mistral",
        "gemini_api_key": "",
    }
    with pytest.raises(ValidationError, match="MISTRAL_API_KEY ou GEMINI_API_KEY"):
        Settings(_env_file=None, **config)


def test_prod_accepte_gemini_seul() -> None:
    config = {
        **_CONFIG_PROD_FORTE,
        "mistral_api_key": "sk-placeholder",
        "gemini_api_key": "AIzaSy-cle-gemini-de-production",
    }
    assert Settings(_env_file=None, **config).is_production is True


def test_gemini_prioritaire_par_defaut() -> None:
    settings = Settings(_env_file=None, app_env="development")
    assert settings.llm_provider == "gemini"


def test_seuil_rag_par_defaut_n_est_plus_permissif() -> None:
    """0.15 laissait passer presque tout extrait (similarités mistral-embed élevées)."""
    settings = Settings(_env_file=None, app_env="development")
    assert settings.rag_min_score >= 0.5
    assert settings.rag_lexical_min_score >= 0.5


def test_prod_accepte_une_configuration_complete() -> None:
    settings = Settings(_env_file=None, **_CONFIG_PROD_FORTE)
    assert settings.is_production is True


def test_docs_masques_en_production() -> None:
    """Swagger UI/ReDoc/openapi.json doivent être désactivés en production."""
    assert docs_urls(is_production=True) == (None, None, None)


def test_docs_actifs_hors_production() -> None:
    """Swagger UI/ReDoc restent accessibles en développement/test."""
    assert docs_urls(is_production=False) == ("/docs", "/redoc", "/openapi.json")
