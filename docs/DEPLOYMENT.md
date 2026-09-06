# 🚀 Guide de Déploiement Cloud & Production — ProsArtisan IA

Ce guide décrit les procédures opérationnelles pour déployer la plateforme **ProsArtisan IA** en environnement de production hautement disponible, sécurisé et conforme aux garde-fous de l'architecture.

---

## 📋 Prérequis & Variables d'Environnement Obligatoires

En production (`APP_ENV=production`), l'application refuse de démarrer si les variables suivantes ne sont pas configurées avec des clés cryptographiques robustes (voir `app/config.py` et `AGENTS.md §2`) :

| Variable d'Environnement | Description | Recommandation |
| :--- | :--- | :--- |
| `APP_ENV` | Environnement d'exécution | `production` |
| `APP_DEBUG` | Mode de débogage | `false` |
| `APP_SECRET_KEY` | Clé secrète de chiffrement applicatif | Chaîne aléatoire 32+ octets (`openssl rand -hex 32`) |
| `JWT_SECRET_KEY` | Signature des jetons JWT | Clé secrète dédiée (`openssl rand -hex 32`) |
| `MOBILE_MONEY_SECRET_KEY` | Clé secrète HMAC Webhooks Wave / OM | Clé partagée avec les opérateurs |
| `DB_REQUIRE_POSTGRES` | Refuse le démarrage si PostgreSQL est absent | `true` |
| `DB_HOST`, `DB_PORT` | Hôte et port PostgreSQL | Serveur Cloud SQL / RDS / Conteneur |
| `DB_DATABASE`, `DB_USERNAME`, `DB_PASSWORD` | Identifiants PostgreSQL | Mot de passe complexe non par défaut |
| `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD` | Instance Redis (Cache & Rate-limit) | Instance managée ou conteneur avec mot de passe |
| `QDRANT_HOST`, `QDRANT_PORT` | Base vectorielle Qdrant | Port 6333 |
| `OPENAI_API_KEY` | Clé API OpenAI (Modèles GPT & Embeddings) | Clé de production `sk-...` |
| `CORS_ALLOWED_ORIGINS` | Origines autorisées (CORS) | `https://prosartisan.ci` (interdiction stricte de `*`) |

---

## 🐳 Option 1 : Déploiement Serveur Dédié / VPS via Docker Compose & SSL Caddy

Cette méthode déploie l'ensemble de la stack (API FastAPI, PostgreSQL 16, Redis 7, Qdrant et Caddy SSL automatique) sur une machine virtuelle Linux (Ubuntu 22.04 / 24.04).

### 1. Cloner le Référentiel et Configurer l'Environnement

```bash
git clone https://github.com/bambainza/assistantIA-prosartisan.git /opt/prosartisan
cd /opt/prosartisan
cp .env.example .env.prod
# Éditer .env.prod avec les vrais secrets de production
nano .env.prod
```

### 2. Démarrer la Stack de Production

```bash
# Lancement des conteneurs en tâche de fond avec le compose de production
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

### 3. Exécuter l'Ingestion Initiale du Corpus RAG

```bash
docker compose -f docker-compose.prod.yml exec app python -m ingestion.pipeline --docs-dir ./ingestion/documents
```

---

## ☁️ Option 2 : Déploiement Serverless sur Google Cloud Run

Pour un déploiement scalable sans gestion d'infrastructure :

1. **Créer les secrets dans Google Secret Manager** :

   ```bash
   gcloud secrets create app-secret-key --data-file=<(openssl rand -hex 32)
   gcloud secrets create jwt-secret-key --data-file=<(openssl rand -hex 32)
   gcloud secrets create mobile-money-secret-key --data-file=<(openssl rand -hex 32)
   ```

2. **Construire et pousser l'image Docker** :

   ```bash
   gcloud builds submit --tag gcr.io/$PROJECT_ID/prosartisan-api:latest .
   ```

3. **Déployer sur Cloud Run** :

   ```bash
   gcloud run services replace cloudrun.yaml --region europe-west1
   ```

---

## ☁️ Option 3 : Déploiement 1-Clic sur Render

Utiliser le fichier `render.yaml` situé à la racine du projet :

1. Connecter le référentiel GitHub sur [Render Dashboard](https://dashboard.render.com).
2. Choisir **New > Blueprint**.
3. Sélectionner la branche `main` : Render provisionne automatiquement le service FastAPI, PostgreSQL et Redis.

---

## 🔄 Pipeline CI/CD GitHub Actions

Le projet est configuré avec 2 workflows GitHub Actions dans `.github/workflows/` :

- **`ci.yml` (Intégration Continue)** :
  - Exécuté sur chaque `push` et `pull_request`.
  - Lance les linters et formatteurs `ruff check` et `ruff format`.
  - Exécute la suite de tests backend `pytest` avec PostgreSQL, Redis et Qdrant éphémères.
  - Exécute `flutter analyze` et `flutter test` sur l'application mobile.
  - Vérifie la compilation de l'image Docker.

- **`cd.yml` (Déploiement Continu)** :
  - Déclenché lors d'un `push` sur la branche `main` ou de la publication d'un tag `v*`.
  - Construit et publie l'image multi-architecture vers `ghcr.io`.
  - Déclenche le webhook de déploiement sécurisé.
  - Valide automatiquement la disponibilité de l'application via le healthcheck `/api/health`.
