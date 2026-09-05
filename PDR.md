# 📘 Plan de Référence du Projet (PDR) — ProsArtisan IA Expert

Ce document constitue la **Fiche de Référence Produit & Architecture (PDR)** pour l'assistant IA **ProsArtisan**, conçu pour accompagner les artisans du BTP et des métiers d'art en Côte d'Ivoire et en Afrique de l'Ouest.

---

## 🎯 1. Vision & Objectifs Produit

ProsArtisan IA est un copilot technique conversationnel accessible via Web & Mobile. Il résout les défis du terrain :
- **Support Métier Précis** : Réponses techniques structurées étape par étape (maçonnerie, électricité, plomberie, charpente, carrelage, mécanique, maroquinerie, etc.).
- **Compréhension Multilingue & Nouchi** : Prise en charge du français, du Nouchi (argot des chantiers ivoiriens), Dioula, Baoulé et Bété.
- **Multimodalité Photo (GPT-4o Vision)** : Analyse de photos de chantier (fissures, installations électriques, défaillances mécaniques).
- **Monétisation Mobile Money Locale** : Paiement ultra-simple via Wave Business & Orange Money (Pass 24H Urgence à 500 F CFA, Pass Mensuel Pro à 3000 F CFA, Pack 50 requêtes à 1500 F CFA).
- **Mode Hors-Ligne & Robustesse** : Mémoire locale et réponses rapides sur réseaux mobiles 3G/4G faibles.

---

## 🏗️ 2. Architecture Technique Global

```mermaid
graph TD
    Client[📱 App Mobile Flutter / Web] -->|HTTP / WebSocket| FastAPI[🚀 Backend Core FastAPI]
    FastAPI -->|Check Quota| QuotaService[⚡ Quota & Freemium Service]
    QuotaService -->|Stockage DB| Postgres[(🐘 PostgreSQL / asyncpg)]
    FastAPI -->|Recherche Vectorielle| RAGService[🔍 RAG & Vector Engine]
    RAGService -->|Recherche Embeddings| Qdrant[(🎯 Vector DB Qdrant)]
    RAGService -->|Synthèse & Vision| OpenAI[🤖 OpenAI GPT-4o / GPT-4o-mini]
    FastAPI -->|Paiement Mobile Money| PaymentService[💳 Service Paiement & Webhooks]
    PaymentService -->|Signature HMAC SHA-256| MobileMoney[💰 Wave / Orange Money API]
```

### Stack Technique
- **Langage & Framework** : Python 3.12, FastAPI, Pydantic v2.
- **Base de Données Relationnelle** : PostgreSQL, SQLAlchemy 2.0 (AsyncIO), Asyncpg, Alembic. Pool de connexions dimensionné (`DB_POOL_SIZE`/`DB_MAX_OVERFLOW`/`DB_POOL_RECYCLE`), `pool_pre_ping` actif.
- **Cache & Rate Limiting** : Redis (compteurs de quota/rate-limit partagés entre workers), avec repli en mémoire locale si Redis est indisponible (dev/tests uniquement).
- **Base Vectorielle & RAG** : Qdrant (`qdrant-client`), Embeddings OpenAI (`text-embedding-3-small`).
- **Intelligence Artificielle** : OpenAI GPT-4o (Vision) & GPT-4o-mini, Whisper API (Vocal).
- **Paiements & Webhooks** : Wave Business API, Orange Money API, Signatures HMAC SHA-256 (obligatoire, aucun contournement).
- **Découpage & Ingestion PDF** : PyPDF, Semantic Chunking (overlap 10-15%).
- **Console d'Administration** : Interface statique HTML/JS/CSS (Template Dastone v2.1.0) montée sur `/admin` dans FastAPI.
- **Résilience** : Mécanisme de démarrage dégradé (repli SQLite autonome, hors production uniquement) si PostgreSQL est injoignable. En production (`APP_ENV=production`) ou avec `DB_REQUIRE_POSTGRES=true`, une base injoignable fait échouer le démarrage plutôt que de basculer silencieusement.

---

## 📁 3. Arborescence du Projet

```text
AssistantIA-prosartisan/
├── app/
│   ├── config.py             # Paramètres centralisés (Pydantic Settings)
│   ├── main.py               # Point d'entrée FastAPI & middlewares CORS
│   ├── db/                   # Connexion asyncpg & initialisation des tables
│   ├── models/               # Modèles ORM (User, Quota, Transaction, Metier)
│   ├── schemas/              # Schémas Pydantic (Chat, Payment, Quota, User)
│   ├── services/             # Logique Métier (RAG, Quota, Payment)
│   └── routers/              # Endpoints API (chat, payment, quota, admin, health)
├── admin_web/                # Back-Office statique (HTML/JS/CSS, base : template Dastone v2.1.0)
├── chat_web/                 # Front-Office chat statique (HTML/JS/CSS)
├── mobile_app_flutter/       # Application mobile Flutter (Android prioritaire)
├── ingestion/
│   ├── pipeline.py           # Pipeline PDF → Chunks sémantiques → Qdrant
│   └── documents/            # Guides et fiches techniques PDF par métier
├── prompts/
│   └── system_prompt.txt     # Prompt système multilingue & garde-fous RAG
├── tests/                    # Test suite Pytest (100% couverture endpoints)
├── AGENTS.md                 # Règles & directives d'ingénierie du projet
├── PDR.md                    # Document de Référence Produit & Architecture
└── requirements.txt          # Dépendances pip du projet
```

---

## 💳 4. Offres & Modèle Économique (Mobile Money)

| Offre | Code | Tarif (FCFA) | Contenu |
| :--- | :--- | :--- | :--- |
| **Pass Gratuit** | `FREE` | **0 F** | 5 questions gratuites par jour |
| **Pass 24H Urgence** | `pass_24h` | **500 F** | Accès illimité pendant 24h chrono |
| **Pass Mensuel Pro** | `pass_mois` | **3 000 F** | Accès illimité pendant 30 jours |
| **Pack 50 Requêtes** | `pack_50_requetes` | **1 500 F** | Crédit de 50 questions sans limite de temps |

---

## 🛡️ 5. Endpoints API Principaux

Sur toutes les routes ci-dessous, l'identité de l'artisan est déduite du JWT (`Authorization: Bearer ...`) quand il est fourni ; en son absence, un compte anonyme partagé est utilisé pour le mode non connecté. Aucune route n'accepte plus un `user_id` fourni par le client (corps, query ou chemin) — voir AGENTS.md §2.

**Authentification** (`/api/auth`)

- `POST /register`, `POST /login` : inscription et connexion par email/mot de passe.
- `POST /google` : connexion/inscription via Google OAuth 2.0.
- `POST /refresh` : renouvelle l'access token à partir d'un refresh token valide.
- `GET /me` : profil de l'artisan connecté (JWT requis).

**Chat & Historique**

- `POST /api/chat` : Pose une question technique (texte + photo `image_url` optionnelle + filtre `metier_id`). Intercepte les quotas épuisés avec `HTTP 402 Payment Required`.
- `POST /api/chat/stream` : équivalent en streaming SSE.
- `POST /api/chat/transcribe` : transcription vocale (Whisper) d'une note audio de chantier.
- `WS /api/chat/ws` : Stream WebSocket en temps réel. Identité déduite d'un JWT optionnel en query param (`?token=...`, un WebSocket ne portant pas d'en-tête `Authorization` côté client), sinon compte anonyme partagé ; quota décrémenté à chaque message comme sur les routes HTTP.
- `GET/POST /api/conversations`, `GET/PATCH/DELETE /api/conversations/{id}` : historique des discussions, strictement cloisonné par propriétaire.

**Paiement Mobile Money** (`/api/payment`)

- `GET /tarifs` : grille tarifaire des Pass et Packs.
- `POST /init` : initialise un paiement Wave ou Orange Money (JWT requis — l'utilisateur ne peut initier un paiement que pour son propre compte).
- `POST /webhook` : webhook sécurisé par signature HMAC SHA-256 (`X-Signature` obligatoire, aucune exception) et idempotent (un webhook rejoué sur une transaction déjà aboutie ne re-crédite pas le Pass).

**Quota**

- `GET /api/quota` : solde de questions et statut d'abonnement de l'artisan courant.

**Back-Office Admin** (`/api/admin`, JWT admin requis)

- `POST /upload-pdf` (ingestion PDF), `GET /stats`, `GET /overview`, `GET /users`, `POST /users/{id}/grant-pass`, `GET /documents`, `DELETE /documents/{id}`, `GET /transactions`, `GET /logs`.

---

## 🧪 6. Procédures de Vérification & Qualité

Pour lancer la suite de tests automatisés :
```bash
.\.venv\Scripts\pytest.exe tests/ -v
```

Pour exécuter le pipeline d'ingestion sémantique :
```bash
python -m ingestion.pipeline --docs-dir ./ingestion/documents --metier-id 1
```
