# 🚀 ProsArtisan — IA Expert pour Artisans

Assistant IA conversationnel dédié aux **artisans professionnels** (maçons, électriciens, menuisiers, maroquiniers…).
Fournit des réponses techniques précises via **RAG** (Retrieval-Augmented Generation), avec un modèle économique **freemium** monétisé par **Mobile Money**.

## 🏗️ Architecture

| Service | Stack | Port |
|---------|-------|------|
| **app** | Python 3.12 / FastAPI | 8000 |
| **db** | PostgreSQL 16 | 5432 |
| **redis** | Redis 7 | 6379 |
| **qdrant** | Qdrant (base vectorielle) | 6333 |

## 📋 Prérequis

- [Docker](https://docs.docker.com/get-docker/) & Docker Compose
- Python >= 3.12 (pour le développement local sans Docker)

## 🛠️ Installation

1. **Cloner le dépôt** :
   ```bash
   git clone https://github.com/bambainza/assistantIA-prosartisan.git
   cd assistantIA-prosartisan
   ```

2. **Configurer l'environnement** :
   ```bash
   cp .env.example .env
   # Éditez .env avec vos clés (Mistral, Wave, etc.)
   ```

   Pour activer Google Sign-In, renseignez également `GOOGLE_CLIENT_ID` avec
   l'identifiant OAuth Web public créé dans Google Cloud Console.

3. **Lancer avec Docker** :
   ```bash
   docker compose up -d
   ```

4. **Vérifier** :
   ```bash
   curl http://localhost:8000/health
   # → {"status": "ok", "service": "ProsArtisan IA Expert", "version": "0.1.0"}
   ```

5. **Documentation API interactive** :
   Ouvrez [http://localhost:8000/docs](http://localhost:8000/docs) (Swagger UI)

## 🧪 Tests

```bash
# Avec Docker
docker compose exec app pytest tests/ -v

# En local (venv)
python -m venv .venv
source .venv/bin/activate  # Windows : .venv\Scripts\activate
pip install -r requirements.txt
pytest tests/ -v
```

## 📁 Structure du Projet

```
app/                    # Code source FastAPI
├── models/             # Modèles SQLAlchemy (ORM)
├── schemas/            # Schémas Pydantic (validation)
├── routers/            # Routes API (REST + WebSocket) ; admin/ découpé par domaine
├── services/           # Logique métier (quotas, paiement, IA)
├── middleware/          # Auth JWT, rate limiting, IP client (proxies), en-têtes sécurité
├── db/                 # Session & init DB
├── scripts/            # Scripts d'exploitation (reprise des photos Base64)
└── main.py             # Point d'entrée
ingestion/              # Pipeline RAG (PDF → Qdrant)
admin_web/              # Back-office statique (js/ : un script par domaine)
chat_web/               # Front chat (PWA)
prompts/                # Prompt système IA
migrations/             # Alembic (migrations BDD)
tests/                  # Tests pytest
docs/                   # Cahier des charges
```

## 🔑 Variables d'Environnement

Consultez [`.env.example`](.env.example) pour la liste complète. Derrière un reverse proxy (Caddy, Render, Cloud Run), renseignez `TRUSTED_PROXY_HOPS=1` : sans cela, tous les utilisateurs partagent la même limite de débit et le même quota anonyme.

Après mise à jour du code, appliquez les migrations (`alembic upgrade head`) — la migration `f1a2b3c4d5e6` renomme `requetes_restantes_gratuites` en `credits_requetes` (quota gratuit journalier désormais compté dans Redis).

Les photos de chantier sont stockées dans `UPLOAD_DIR/chat_images/` (volume persistant obligatoire en production). Pour sortir de la base les photos déjà enregistrées en Base64 : `python -m app.scripts.migrate_chat_images --dry-run` puis sans `--dry-run` (à lancer dans le conteneur qui monte `UPLOAD_DIR`).

## 📝 Documentation de référence

- `PDR.md` est le PRD/PDR et la source de vérité produit et architecture.
- `AGENTS.md`, `CLAUDE.md` et `.agents/rules/project_rules.md` portent les règles d'implémentation.

Avant chaque commit puis avant chaque push, toute implémentation doit déclencher
une relecture et une mise à jour systématiques du PRD/PDR et des fichiers de
règles. Aucun commit ou push ne doit être effectué tant que ces documents, les
exemples d'environnement et les procédures concernées ne correspondent pas au code.

## 📄 Licence

Copyright © 2026 ProsArtisan. Tous droits réservés.
Voir [LICENSE.txt](LICENSE.txt).
