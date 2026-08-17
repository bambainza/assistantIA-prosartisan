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
   # Éditez .env avec vos clés (OpenAI, Wave, etc.)
   ```

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
├── routers/            # Routes API (REST + WebSocket)
├── services/           # Logique métier (quotas, paiement, IA)
├── middleware/          # Auth JWT
├── db/                 # Session & init DB
└── main.py             # Point d'entrée
ingestion/              # Pipeline RAG (PDF → Qdrant)
prompts/                # Prompt système IA
migrations/             # Alembic (migrations BDD)
tests/                  # Tests pytest
docs/                   # Cahier des charges
```

## 🔑 Variables d'Environnement

Consultez [`.env.example`](.env.example) pour la liste complète.

## 📄 Licence

Copyright © 2026 ProsArtisan. Tous droits réservés.
Voir [LICENSE.txt](LICENSE.txt).