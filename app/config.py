"""Configuration centralisée de l'application (pydantic-settings)."""

from urllib.parse import quote_plus

from pydantic import model_validator
from pydantic_settings import BaseSettings

# Valeurs de secret livrées par défaut : interdites en production.
_SECRETS_FAIBLES = {
    "changeme",
    "changeme_in_production",
    "placeholder",
    "placeholder_hmac_secret",
    "placeholder_webhook_secret",
    "dev_secret_key_change_in_production",
    "dev_jwt_secret_change_in_production",
    "",
}


class Settings(BaseSettings):
    """Paramètres chargés depuis les variables d'environnement ou le fichier .env."""

    # ── Application ──
    app_env: str = "development"
    app_debug: bool = True
    app_secret_key: str = "changeme"
    cors_allowed_origins: str = "*"
    rate_limit_requests_per_minute: int = 60

    # ── JWT ──
    jwt_secret_key: str = "changeme"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 1440  # 24h

    # ── Base de données PostgreSQL ──
    db_host: str = "db"
    db_port: int = 5432
    db_database: str = "prosartisan"
    db_username: str = "prosartisan"
    db_password: str = "changeme_in_production"

    # Comportement du moteur de base de données
    db_require_postgres: bool = (
        False  # True => aucun repli SQLite (toujours vrai en prod)
    )
    db_echo: bool = False  # journalise le SQL brut
    db_connect_timeout: int = 5  # secondes (sonde TCP + handshake asyncpg)
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_recycle: int = 1800  # recycle les connexions inactives après 30 min
    db_sqlite_path: str = "./prosartisan.db"  # utilisé uniquement en repli autonome

    @property
    def database_url(self) -> str:
        password = quote_plus(self.db_password)
        return (
            f"postgresql+asyncpg://{self.db_username}:{password}"
            f"@{self.db_host}:{self.db_port}/{self.db_database}"
        )

    @property
    def postgres_obligatoire(self) -> bool:
        """Le repli SQLite est interdit en production ou si explicitement demandé."""
        return self.db_require_postgres or self.is_production

    # ── Redis ──
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: str = "changeme_in_production"

    @property
    def redis_url(self) -> str:
        password = quote_plus(self.redis_password)
        return f"redis://:{password}@{self.redis_host}:{self.redis_port}/0"

    # ── Qdrant ──
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333
    qdrant_collection: str = "connaissances_prosartisan"

    # ── LLM (OpenAI) & Vision / Audio ──
    openai_api_key: str = "sk-placeholder"
    llm_model: str = "gpt-4o-mini"
    llm_vision_model: str = "gpt-4o"
    whisper_model: str = "whisper-1"
    llm_temperature: float = 0.2
    embedding_model: str = "text-embedding-3-small"

    # ── Stockage Fichiers ──
    upload_dir: str = "./uploads"

    # ── Paiement Mobile Money ──
    wave_api_key: str = "wave_sk_live_placeholder"
    mobile_money_secret_key: str = "placeholder_hmac_secret"
    webhook_secret: str = "placeholder_webhook_secret"

    # ── Compte administrateur initial (seed) ──
    admin_email: str = "admin@prosartisan.ci"
    admin_password: str | None = None  # requis en production, sinon pas de seed admin

    # ── Quotas Freemium ──
    max_questions_gratuites_par_jour: int = 5

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    @model_validator(mode="after")
    def _verifier_secrets_production(self) -> "Settings":
        """Refuse de démarrer en production avec des secrets/CORS non configurés."""
        if not self.is_production:
            return self

        erreurs: list[str] = []
        if self.app_secret_key in _SECRETS_FAIBLES:
            erreurs.append("APP_SECRET_KEY")
        if self.jwt_secret_key in _SECRETS_FAIBLES:
            erreurs.append("JWT_SECRET_KEY")
        if self.mobile_money_secret_key in _SECRETS_FAIBLES:
            erreurs.append("MOBILE_MONEY_SECRET_KEY")
        if self.db_password in _SECRETS_FAIBLES:
            erreurs.append("DB_PASSWORD")
        if self.cors_allowed_origins.strip() == "*":
            erreurs.append("CORS_ALLOWED_ORIGINS (le joker '*' est interdit)")
        if self.app_debug:
            erreurs.append("APP_DEBUG (doit être false)")

        if erreurs:
            raise ValueError(
                "Configuration de production invalide — variables à définir : "
                + ", ".join(erreurs)
            )
        return self


settings = Settings()
