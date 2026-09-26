# CLAUDE.md

Ce fichier guide Claude Code pour ce dépôt précis. **Il prévaut sur tout CLAUDE.md hérité d'un dossier parent** (le dossier `GitHub/` racine contient plusieurs autres projets marketplace Laravel/Flutter sans rapport avec celui-ci — ignore leurs instructions ici).

## Vue d'ensemble

**ProsArtisan IA Expert** — assistant IA conversationnel (RAG) pour artisans du BTP et métiers d'art en Côte d'Ivoire (maçonnerie, électricité, plomberie, menuiserie, mécanique...). Multilingue (français + Nouchi, Dioula, Baoulé, Bété), multimodal (photos de chantier via la vision Mistral, vocal via Voxtral), monétisé en Mobile Money (Wave, Orange Money).

**Ce n'est pas un marketplace** (pas de clients/artisans/fournisseurs mis en relation, pas de J-Code, pas de séquestre) — c'est un copilot technique conversationnel avec freemium par quota de questions.

Documents de référence à consulter en priorité : `AGENTS.md` (règles d'ingénierie et garde-fous obligatoires), `PDR.md` (architecture produit détaillée), `README.md` (setup rapide).

## Stack technique

| Composant | Techno |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic v2 |
| BDD relationnelle | PostgreSQL 16, SQLAlchemy 2.0 (async), asyncpg, Alembic |
| Cache / quotas / rate-limit | Redis 7 (jamais d'état en mémoire par worker) |
| Base vectorielle (RAG) | Qdrant, embeddings Mistral `mistral-embed` |
| IA | Mistral Small / Medium (texte + vision), Voxtral (vocal STT/TTS) |
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
  → app/routers/          (chat, auth, payment, quota, conversation, media, health, admin/ découpé par domaine)
      → app/schemas/       (validation Pydantic)
      → app/services/      (logique métier : rag_service, payment_service, quota_service, cache_service, audio_service, chat_history_service, audit_service)
          → app/models/    (SQLAlchemy ORM async, dont role.py pour le RBAC et audit_log.py pour le journal d'audit)
      → app/middleware/    (auth JWT + RBAC, rate_limiter Redis, logging, security_headers)
```

Séparation stricte imposée : logique métier dans `app/services/`, jamais dans les routers.

## Règles d'or — ne jamais contourner (voir `AGENTS.md` pour le détail complet)

1. **Zéro hallucination RAG** : sans extrait pertinent en base (score < `RAG_MIN_SCORE`), le service court-circuite l'appel LLM et renvoie le message de repli codé (`FALLBACK_MESSAGE` dans `app/services/rag_service.py`), identique mot pour mot à celui de `prompts/system_prompt.txt`.
2. **Identité déduite du JWT, jamais du client** : aucun `user_id` n'est accepté depuis le corps/query/path d'une requête entrante — toujours `get_current_user_id` / `get_optional_user_id`. Seul un token `type=access` est accepté (refresh token en `Bearer` → `401`). Mode non connecté → aucun historique serveur (plus de compte anonyme partagé ; `/api/conversations` exige le JWT, `conversation_id` anonyme → `401`) ; quota anonyme compté par IP.
2 bis. **Sessions navigateur** : `chat_web` passe par `/api/auth/web/*` et des cookies access/refresh `HttpOnly`; aucun JWT dans `localStorage`. Les mutations cookie exigent `X-CSRF-Token`, tandis que Flutter conserve le Bearer. Le Markdown LLM est assaini par liste blanche avant toute insertion DOM et la CSP du chat interdit les attributs de script inline.
3. **Isolation par propriétaire (anti-IDOR)** : toute ressource retrouvée par ID opaque (conversation, transaction, document) doit être filtrée par `WHERE user_id = ...`.
4. **Webhooks Mobile Money** : Wave → `Wave-Signature` (HMAC SHA-256 de `t + corps`, anti-rejeu) ; Orange Money → `notif_token` puis confirmation `transactionstatus` ; générique → `X-Signature`. Non authentifié → `401` systématique, jamais optionnel. Crédit unique (idempotent) et seulement si le montant confirmé = montant de la transaction. `PAYMENT_MODE=demo` (défaut) = simulateur fidèle des parcours officiels, désactivé en production sauf `PAYMENT_DEMO_IN_PRODUCTION=true`.
5. **Garde-fous de démarrage en production** (`APP_ENV=production`) : refus de démarrer si `APP_SECRET_KEY`, `JWT_SECRET_KEY`, `MOBILE_MONEY_SECRET_KEY`, `DB_PASSWORD`, `VAPID_PRIVATE_KEY` sont à leur valeur par défaut, si `CORS_ALLOWED_ORIGINS=*`, ou si `APP_DEBUG=true`.
6. **Jamais de secrets en dur** — tout passe par `app.config.settings` / `.env`. Le compte admin seed exige `ADMIN_PASSWORD` en prod (pas de valeur par défaut).
7. **État partagé entre workers** (quotas, rate-limit) → Redis obligatoire, jamais un attribut de classe Python. Quota = Pass premium → compteur Redis journalier (`INCR` atomique) → crédits achetés (`credits_requetes`, décrément SQL atomique) ; Redis injoignable en prod → `503`. Réponse IA en échec après décompte → question rendue (`quota_service.restituer_quota`). `metier_id` jamais codé en dur dans un client (`GET /api/metiers`). IP cliente via `get_client_ip` (`TRUSTED_PROXY_HOPS`), jamais `request.client.host`.
7 bis. **Photos hors base & coûts IA** : photo validée (`media_service.prepare_chat_image`) avant quota, stockée sur disque, référence `media:<nom>` en base, URL signée côté client. Contrôles gratuits (taille, propriété, débit, quota) avant tout appel facturé (STT, vision), WebSocket compris. `generate_response` et `generate_response_stream` partagent `RAGService._prepare` ; (dés)activer un métier/document → `rag_service.invalidate_activation_cache()`.
8. **Travaux longs hors requête HTTP** (ingestion, appel externe lourd) → `BackgroundTasks` + réponse `202 Accepted` immédiate.
9. **Migrations Alembic obligatoires** pour toute évolution de modèle ORM déjà déployé — `Base.metadata.create_all` ne sert qu'au dev/tests. Tout nouveau modèle est importé dans `app/models/__init__.py` (sinon les scripts `app/scripts/` échouent à résoudre les relations). Horodatages en UTC naïf (`UTCNaiveDateTime`, appliqué via `Base.type_annotation_map`) ; un échec de migration au démarrage du conteneur l'arrête.
10. **Métadonnées d'ingestion obligatoires** : `metier_id`, `secteur_id`, `type_document`, `niveau_expertise` validées à l'ingestion, sinon document rejeté (jamais indexé silencieusement). Fiche à enjeu santé/sécurité : `ingestion/documents_a_valider/` jusqu'à relecture par un professionnel.
11. **RBAC & journal d'audit** : toute route admin sensible protégée par une permission dédiée doit utiliser `require_permission(...)` (pas seulement `get_current_admin_user_id`), et toute mutation admin doit écrire une entrée via `audit_service.log_action(...)` avant son `commit()`. Un admin `is_admin=True` sans rôle assigné garde l'accès complet (compatibilité descendante) — ne jamais restreindre ce cas silencieusement.
11 bis. **Suppressions tierces** : attendre la confirmation Qdrant avant audit de succès, commit local et invalidation du cache ; une panne renvoie `503`, jamais un faux succès. Préférer une opération idempotente par filtre.
12. **2FA & refresh tokens** : un admin avec `totp_enabled=True` doit toujours fournir un code TOTP valide à la connexion. Les refresh tokens sont à usage unique (rotation via `jti` + liste noire) — `/auth/refresh` révoque l'ancien token à chaque renouvellement, `/auth/logout` permet une révocation explicite.
13. **Notifications** : toujours passer par `notification_service.notify(...)` (écrit l'entrée in-app avant toute tentative de canal externe) — jamais d'appel direct à un provider externe (FCM...) depuis un router.
14. **Diffusion de masse en tâche de fond** : toute diffusion vers potentiellement tous les artisans (composer de notifications, publication d'actualité) s'exécute via `BackgroundTasks` avec sa propre session DB — jamais dans la requête HTTP d'origine.
15. **Documentation vérifiée avant chaque commit et push** : pour toute implémentation ou modification, même mineure, relire et mettre à jour systématiquement `PDR.md` (produit/architecture/API) ainsi que `AGENTS.md`, `CLAUDE.md` et `.agents/rules/project_rules.md` avant chaque `git commit`, puis vérifier à nouveau leur cohérence avant chaque `git push`. Mettre également à jour `.env.example`, `README.md` et les manifests de déploiement concernés si la configuration ou l'exploitation change. Le commit et le push sont interdits tant que ce contrôle n'est pas terminé. Si aucun changement documentaire supplémentaire n'est nécessaire, le compte rendu doit confirmer explicitement que la relecture a été effectuée et que les fichiers restent à jour.

## Contexte marché

Côte d'Ivoire, français + langues locales, FCFA (entiers, jamais de décimales), connectivité 3G/4G faible → réponses robustes et rapides attendues.

**Offres freemium** : Gratuit (5 questions/jour), Pass 24H (500 F), Pass Mensuel Pro (3000 F), Pack 50 requêtes (1500 F).
