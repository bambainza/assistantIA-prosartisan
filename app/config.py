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
    "BXOGEmSclzlZTkj7aufE7jUK2_-4XZvBW6GEFvR0X4E",  # clé VAPID de dev
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
    # Nombre de reverse proxies de confiance devant l'API (Caddy, Render,
    # Cloud Run...). 0 = connexion directe : l'IP TCP est utilisée telle quelle.
    # N > 0 : l'IP client est la N-ième entrée en partant de la droite de
    # `X-Forwarded-For` (les entrées plus à gauche sont falsifiables par le
    # client et ne sont jamais utilisées). Sans ce réglage derrière un proxy,
    # tous les utilisateurs partagent l'IP du proxy (rate-limit et quota
    # anonyme communs à tout le service).
    trusted_proxy_hops: int = 0

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
    # Dimension des vecteurs de la collection (doit correspondre à embedding_model :
    # 1024 pour mistral-embed).
    qdrant_vector_size: int = 1024
    # Score de similarité minimal (cosinus) pour qu'un extrait retrouvé soit
    # considéré pertinent. En dessous, on déclenche le repli "zéro hallucination"
    # plutôt que de laisser le LLM broder sur un contexte hors sujet.
    rag_min_score: float = 0.15

    # ── LLM (Mistral) & Vision / Audio ──
    mistral_api_key: str = "sk-placeholder"
    google_client_id: str = ""
    llm_model: str = "mistral-small-latest"
    # Modèle utilisé pour l'analyse de photos de chantier (vision) — depuis les
    # familles Mistral 3.x/Magistral, la vision est intégrée nativement, plus
    # besoin d'un modèle multimodal séparé et surtaxé comme l'ancien Pixtral.
    llm_vision_model: str = "mistral-medium-latest"
    stt_model: str = "voxtral-mini-latest"
    tts_model: str = "voxtral-mini-tts-2603"
    # Identifiant de la voix Voxtral TTS. Par défaut : "Marie - Neutral", une
    # voix française prête à l'emploi (préréglage Mistral, pas de clonage
    # requis — voir `GET /v1/audio/voices?type=preset` pour la liste complète,
    # dont 6 voix "fr_marie_*" à différents tons). Sans valeur, la synthèse
    # vocale échoue explicitement plutôt que d'utiliser une voix arbitraire.
    tts_voice_id: str | None = "5a271406-039d-46fe-835b-fbbb00eaf08d"
    llm_temperature: float = 0.2
    embedding_model: str = "mistral-embed"

    # ── Stockage Fichiers ──
    upload_dir: str = "./uploads"

    # ── Paiement Mobile Money ──
    wave_api_key: str = "wave_sk_live_placeholder"
    mobile_money_secret_key: str = "placeholder_hmac_secret"
    webhook_secret: str = "placeholder_webhook_secret"

    # Mode de paiement : "demo" (simulateur local reproduisant fidèlement les
    # parcours officiels Wave Checkout et Orange Money WebPay : mêmes formats de
    # requêtes, de webhooks et de signatures) ou "live" (API officielles).
    payment_mode: str = "demo"
    # En production, le mode démo refuse tout paiement (503) — sinon n'importe
    # qui obtiendrait un Pass gratuit — sauf activation explicite (bêta fermée).
    payment_demo_in_production: bool = False
    # URL publique de l'API : base des URLs de retour et de notification
    # transmises aux opérateurs (success/error/return/cancel/notif).
    public_base_url: str = "http://localhost:8000"
    # Fenêtre anti-rejeu des webhooks signés (écart max. horodatage / horloge).
    payment_webhook_tolerance_seconds: int = 300

    # Wave Checkout API (https://docs.wave.com/checkout)
    wave_api_base: str = "https://api.wave.com"
    # Secret de signature des webhooks (en-tête `Wave-Signature`).
    wave_webhook_secret: str = "placeholder_wave_webhook_secret"

    # Orange Money WebPay (https://developer.orange.com/apis/om-webpay)
    orange_api_base: str = "https://api.orange.com"
    # "/orange-money-webpay/dev/v1" (bac à sable) ; en production CI :
    # "/orange-money-webpay/ci/v1".
    orange_webpay_path: str = "/orange-money-webpay/dev/v1"
    orange_client_id: str = ""
    orange_client_secret: str = ""
    orange_merchant_key: str = ""
    # "OUV" en bac à sable, "XOF" en production.
    orange_currency: str = "OUV"

    @property
    def payment_demo_mode(self) -> bool:
        return self.payment_mode.lower() != "live"

    # ── Compte administrateur initial (seed) ──
    admin_email: str = "admin@prosartisan.ci"
    admin_password: str | None = None  # requis en production, sinon pas de seed admin

    # ── Quotas Freemium ──
    max_questions_gratuites_par_jour: int = 5

    # ── Notifications Push (Firebase Cloud Messaging — mobile, API HTTP v1) ──
    # Chemin vers le fichier JSON du compte de service Firebase (Console Firebase
    # > Paramètres du projet > Comptes de service > Générer une nouvelle clé
    # privée). Jamais commité — voir .gitignore. Non configuré => le provider
    # push est un no-op journalisé (voir app/services/notification_service.py).
    fcm_service_account_path: str = ""

    # ── Notifications Web Push (VAPID — chat_web) ──
    # Paire de clés de développement générée localement (aucun compte tiers
    # requis pour le Web Push, contrairement à FCM/Sentry). Fonctionnelle
    # telle quelle en dev/test ; DOIT être régénérée en production (voir
    # `_verifier_secrets_production` ci-dessous) — sinon tous les déploiements
    # partageraient la même identité VAPID.
    vapid_private_key: str = "BXOGEmSclzlZTkj7aufE7jUK2_-4XZvBW6GEFvR0X4E"
    vapid_public_key: str = "BIKIhCN4RidtYT6C2gr5pwtkLw7cyeA3tf91OD19OjJzeWe5mX7o7FERIu62i8MesAoSTpyj8X8GMPnPTTt1Orw"
    vapid_claims_email: str = "contact@prosartisan.ci"

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
        if self.vapid_private_key in _SECRETS_FAIBLES:
            erreurs.append("VAPID_PRIVATE_KEY")
        if self.cors_allowed_origins.strip() == "*":
            erreurs.append("CORS_ALLOWED_ORIGINS (le joker '*' est interdit)")
        if self.app_debug:
            erreurs.append("APP_DEBUG (doit être false)")
        if self.payment_mode.lower() not in {"demo", "live"}:
            erreurs.append("PAYMENT_MODE (demo ou live)")
        if not self.payment_demo_mode:
            # Paiements réels : identifiants opérateurs et URL publique HTTPS.
            if (
                self.wave_api_key in _SECRETS_FAIBLES
                or "placeholder" in self.wave_api_key
            ):
                erreurs.append("WAVE_API_KEY")
            if (
                self.wave_webhook_secret in _SECRETS_FAIBLES
                or "placeholder" in self.wave_webhook_secret
            ):
                erreurs.append("WAVE_WEBHOOK_SECRET")
            for nom, valeur in (
                ("ORANGE_CLIENT_ID", self.orange_client_id),
                ("ORANGE_CLIENT_SECRET", self.orange_client_secret),
                ("ORANGE_MERCHANT_KEY", self.orange_merchant_key),
            ):
                if not valeur:
                    erreurs.append(nom)
            if not self.public_base_url.startswith("https://"):
                erreurs.append("PUBLIC_BASE_URL (HTTPS requis)")

        if erreurs:
            raise ValueError(
                "Configuration de production invalide — variables à définir : "
                + ", ".join(erreurs)
            )
        return self


settings = Settings()
