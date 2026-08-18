"""Configuration centralisée de l'application (pydantic-settings)."""

from urllib.parse import quote_plus

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Paramètres chargés depuis les variables d'environnement ou le fichier .env."""

    # ── Application ──
    app_env: str = "development"
    app_debug: bool = True
    app_secret_key: str = "changeme"

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

    @property
    def database_url(self) -> str:
        password = quote_plus(self.db_password)
        return (
            f"postgresql+asyncpg://{self.db_username}:{password}"
            f"@{self.db_host}:{self.db_port}/{self.db_database}"
        )

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

    # ── Quotas Freemium ──
    max_questions_gratuites_par_jour: int = 5

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
