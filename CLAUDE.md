# CLAUDE.md

Ce fichier guide Claude Code pour ce dépôt précis. **Il prévaut sur tout CLAUDE.md hérité d'un dossier parent** (le dossier `GitHub/` racine contient plusieurs autres projets marketplace Laravel/Flutter sans rapport avec celui-ci — ignore leurs instructions ici).

## Vue d'ensemble

**ProsArtisan IA Expert** — assistant IA conversationnel (RAG) pour artisans du BTP et métiers d'art en Côte d'Ivoire (maçonnerie, électricité, plomberie, menuiserie, mécanique...). Multilingue (français + Nouchi, Dioula, Baoulé, Bété), multimodal (photos de chantier via GPT-4o Vision, vocal via Whisper), monétisé en Mobile Money (Wave, Orange Money).

**Ce n'est pas un marketplace** (pas de clients/artisans/fournisseurs mis en relation, pas de J-Code, pas de séquestre) — c'est un copilot technique conversationnel avec freemium par quota de questions.

Documents de référence à consulter en priorité : `AGENTS.md` (règles d'ingénierie et garde-fous obligatoires), `PDR.md` (architecture produit détaillée), `README.md` (setup rapide).

## Stack technique

| Composant | Techno |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic v2 |
| BDD relationnelle | PostgreSQL 16, SQLAlchemy 2.0 (async), asyncpg, Alembic |
| Cache / quotas / rate-limit | Redis 7 (jamais d'état en mémoire par worker) |
| Base vectorielle (RAG) | Qdrant, embeddings OpenAI `text-embedding-3-small` |
| IA | OpenAI GPT-4o / GPT-4o-mini (texte + vision), Whisper (vocal) |
| Paiement | Wave Business API, Orange Money API (webhooks signés HMAC SHA-256) |
| Mobile | Flutter (`mobile_app_flutter/`, Android prioritaire) |
| Web statique | `admin_web/` (back-office, template Dastone v2.1.0), `chat_web/` (front chat) |

## Commandes essentielles

```bash
# Lancer toute la stack (API + Postgres + Redis + Qdrant)
docker compose up -d
curl http://localhost:8000/health

# Dev local sans Docker
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt

# Tests (100% de réussite exigé avant tout commit — voir AGENTS.md §4)
.\.venv\Scripts\pytest.exe tests/ -v
pytest tests/ -q --cov=app                        # avec couverture

# Lint (obligatoire en CI)
ruff check app/ tests/ ingestion/
ruff format --check app/ tests/ ingestion/

# Migrations Alembic (obligatoires pour toute modif de modèle ORM)
alembic revision --autogenerate -m "description"
alembic upgrade head

# Pipeline d'ingestion RAG (PDF/Markdown → chunks → Qdrant)
python -m ingestion.pipeline --docs-dir ./ingestion/documents --metier-id 1

# Flutter
cd mobile_app_flutter && flutter pub get && flutter test && flutter analyze
```

## Architecture

```
routes/api.py (implicite via routers FastAPI)
  → app/routers/          (chat, auth, payment, quota, conversation, admin, health)
      → app/schemas/       (validation Pydantic)
      → app/services/      (logique métier : rag_service, payment_service, quota_service, cache_service, audio_service, chat_history_service)
          → app/models/    (SQLAlchemy ORM async)
      → app/middleware/    (auth JWT, rate_limiter Redis, logging)
```

Séparation stricte imposée : logique métier dans `app/services/`, jamais dans les routers.

## Règles d'or — ne jamais contourner (voir `AGENTS.md` pour le détail complet)

1. **Zéro hallucination RAG** : sans extrait pertinent en base (score < `RAG_MIN_SCORE`), le service court-circuite l'appel LLM et renvoie le message de repli codé (`FALLBACK_MESSAGE` dans `app/services/rag_service.py`), identique mot pour mot à celui de `prompts/system_prompt.txt`.
2. **Identité déduite du JWT, jamais du client** : aucun `user_id` n'est accepté depuis le corps/query/path d'une requête entrante — toujours `get_current_user_id` / `get_optional_user_id`. Mode non connecté → compte anonyme partagé documenté.
3. **Isolation par propriétaire (anti-IDOR)** : toute ressource retrouvée par ID opaque (conversation, transaction, document) doit être filtrée par `WHERE user_id = ...`.
4. **Webhooks Mobile Money** : signature `X-Signature` HMAC SHA-256 obligatoire ; absente ou invalide → `401` systématique, jamais optionnel.
5. **Garde-fous de démarrage en production** (`APP_ENV=production`) : refus de démarrer si `APP_SECRET_KEY`, `JWT_SECRET_KEY`, `MOBILE_MONEY_SECRET_KEY`, `DB_PASSWORD` sont à leur valeur par défaut, si `CORS_ALLOWED_ORIGINS=*`, ou si `APP_DEBUG=true`.
6. **Jamais de secrets en dur** — tout passe par `app.config.settings` / `.env`. Le compte admin seed exige `ADMIN_PASSWORD` en prod (pas de valeur par défaut).
7. **État partagé entre workers** (quotas, rate-limit) → Redis obligatoire, jamais un attribut de classe Python.
8. **Travaux longs hors requête HTTP** (ingestion, appel externe lourd) → `BackgroundTasks` + réponse `202 Accepted` immédiate.
9. **Migrations Alembic obligatoires** pour toute évolution de modèle ORM déjà déployé — `Base.metadata.create_all` ne sert qu'au dev/tests.
10. **Métadonnées d'ingestion obligatoires** : `metier_id`, `secteur_id`, `type_document`, `niveau_expertise` validées à l'ingestion, sinon document rejeté (jamais indexé silencieusement).

## Contexte marché

Côte d'Ivoire, français + langues locales, FCFA (entiers, jamais de décimales), connectivité 3G/4G faible → réponses robustes et rapides attendues.

**Offres freemium** : Gratuit (5 questions/jour), Pass 24H (500 F), Pass Mensuel Pro (3000 F), Pack 50 requêtes (1500 F).
