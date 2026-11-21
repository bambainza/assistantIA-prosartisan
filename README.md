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
├── scripts/            # Scripts d'exploitation (photos Base64, paiements, calibrage du seuil RAG)
└── main.py             # Point d'entrée
ingestion/              # Pipeline RAG (PDF/Markdown → Qdrant) ; documents/ = corpus indexé,
                        # documents_a_valider/ = fiches santé/sécurité en attente de relecture,
                        # evaluation/ = jeu de questions pour calibrer RAG_MIN_SCORE
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

**Paiements Mobile Money** : `PAYMENT_MODE=demo` (défaut) active un simulateur qui reproduit les parcours officiels Wave Checkout, Orange Money WebPay et CinetPay v1 (page de paiement sans débit réel, notifications signées ou confirmées au format officiel). Le passage en réel ne demande que les identifiants opérateurs (`WAVE_API_KEY`, `WAVE_WEBHOOK_SECRET`, `ORANGE_CLIENT_ID`, `ORANGE_CLIENT_SECRET`, `ORANGE_MERCHANT_KEY`, `CINETPAY_API_KEY`, `CINETPAY_API_PASSWORD`), `PUBLIC_BASE_URL` en HTTPS et `PAYMENT_MODE=live`. En production, le mode démo refuse les paiements sauf `PAYMENT_DEMO_IN_PRODUCTION=true`. Planifiez `python -m app.scripts.reconcile_payments` toutes les 10-15 minutes.

**Historique anonyme** : le serveur ne conserve plus de discussions pour les visiteurs non connectés (historique local dans le navigateur). Pour supprimer celles de l'ancien compte anonyme partagé : `python -m app.scripts.purge_anonymous_history --dry-run`, puis sans `--dry-run`.

**Session Web sécurisée** : `chat_web` utilise les endpoints `/api/auth/web/*` et des cookies JWT `HttpOnly`; les jetons ne sont jamais stockés dans `localStorage`. Les mutations ajoutent automatiquement le double-submit `X-CSRF-Token`. Le client Flutter conserve l'authentification `Authorization: Bearer`. Les réponses Markdown sont filtrées avant leur insertion dans le DOM et la CSP du chat bloque les scripts et attributs événementiels inline.

Les photos de chantier sont stockées dans `UPLOAD_DIR/chat_images/` (volume persistant obligatoire en production). Pour sortir de la base les photos déjà enregistrées en Base64 : `python -m app.scripts.migrate_chat_images --dry-run` puis sans `--dry-run` (à lancer dans le conteneur qui monte `UPLOAD_DIR`).

**Suppression documentaire** : l'administration confirme la suppression dans Qdrant avant de valider l'audit et d'invalider le cache RAG. Une indisponibilité Qdrant renvoie `503`; elle ne produit jamais un faux message de succès.

**Ingestion documentaire admin** : l'upload exige les quatre métadonnées sémantiques (`metier_id`, `secteur_id`, `type_document`, `niveau_expertise`) et contrôle le métier et le secteur dans le référentiel. Le fichier est écrit sans écrasement dans un dossier isolé par tâche, puis ingéré en arrière-plan. La demande et son résultat sont audités avec un `job_id`; un fichier en échec est supprimé.

**Données du back-office & Bascule IA (Mistral / Gemini)** : les listes vides restent vides et ne sont jamais remplacées par des artisans, documents ou statistiques de démonstration. Les routes documentaires renvoient `503` lorsque Qdrant est indisponible. Les journaux d'audit enregistrent l'IP cliente résolue selon `TRUSTED_PROXY_HOPS`. L'onglet Paramètres du back-office (`/api/admin/parametres/llm-providers`) permet de superviser la stabilité de **Mistral AI** et **Google Gemini** (`gemini-3.8-flash`) et de basculer entre le mode par défaut `gemini` (Gemini prioritaire, réglable par `LLM_PROVIDER`), le mode `auto` (sélection automatique de la ressource la plus stable et disponible avec coupe-circuit) ou `mistral` (Mistral prioritaire).

**Clé IA obligatoire en production** : avec `APP_ENV=production`, l'API refuse de démarrer sans `MISTRAL_API_KEY` ou `GEMINI_API_KEY` valide. Sans clé (développement), les réponses et devis sont des exemples génériques signalés « Mode démonstration ».

**Seuil RAG** : `RAG_MIN_SCORE=0.71` a été calibré le 21 novembre 2026 pour `gemini-embedding-001` (toutes les questions couvertes servies, aucune question hors corpus acceptée). Après tout changement de modèle de vecteurs ou ajout important au corpus, recalibrez-le sur le corpus indexé (clé réelle du fournisseur de vecteurs requise, `GEMINI_API_KEY` par défaut, lecture seule) :

```bash
python -m app.scripts.calibrer_seuil_rag --avec-reformulation --json rapport_seuil.json
```

Le script propose le seuil le plus bas qui laisse passer au plus 5 % de questions hors corpus (`--max-faux-positifs`) et liste les questions couvertes qui ne seraient plus servies. `RAG_REFORMULATION_REQUETE=true` cherche aussi la question reformulée en français technique ; elle est désactivée par défaut, car au calibrage elle rapprochait les scores hors corpus des scores couverts sans gain mesuré. Si vous la réactivez, recalibrez avec `--avec-reformulation`.

**Vecteurs Gemini** : la recherche documentaire utilise par défaut `gemini-embedding-001` (`EMBEDDING_PROVIDER=gemini`, 1536 dimensions) dans la collection `connaissances_prosartisan_gemini_1536`. Après passage à Gemini (ou tout changement de modèle ou de dimension), réindexez le corpus — `python -m ingestion.pipeline --docs-dir ./ingestion/documents --metier-id 1` traite tout le corpus, le manifeste étant propre à chaque collection — puis recalibrez `RAG_MIN_SCORE`. `EMBEDDING_PROVIDER=mistral` revient à `mistral-embed` et à la collection historique.

**Grille de prix des devis** : les devis pré-remplis par l'IA ne prennent leurs prix que dans la grille de référence (onglet Devis du back-office, permissions `prix.read`/`prix.write`) ou dans les prix dictés par l'artisan. Une ligne sans prix correspondant (même unité, commune du chantier ou prix national) reste à 0 F et est surlignée. Tant que la grille est vide, toutes les lignes sont à compléter par l'artisan. Appliquez la migration `c4d5e6f7a8b9` (`alembic upgrade head`).

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


### Sessions, budgets audio et disponibilité

Le TOTP administrateur est requis pour les connexions locales et Google (`totp_code`). Les refresh tokens sont consommés atomiquement ; les jetons anciens sans `jti` nécessitent une nouvelle connexion. En production, une panne Redis bloque les opérations sensibles avec `503`.

Les budgets audio journaliers sont séparés des questions : `AUDIO_STT_REQUESTS_PER_DAY=20` et `AUDIO_TTS_CHARS_PER_DAY=20000`, y compris pour les Pass. Ils sont réservés avant les appels HTTP/WebSocket, avec `429` à épuisement et restitution en cas d'échec fournisseur.

`/api/health` est une sonde de vie ; `/api/ready` est la sonde SQL/Redis/Qdrant utilisée par Docker et la livraison (`503` si indisponible). Le Compose de production transmet la paire VAPID, à générer ensemble, et les paramètres CinetPay. La CI précède la publication et le webhook reçoit l'image par digest ainsi que le SHA attendu ; voir `docs/DEPLOYMENT.md` pour son contrat.

Tests Redis réels : sélectionner le backend via `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, puis définir `RUN_SHARED_BACKEND_TESTS=1` avant `pytest tests/ -v`. Sous Windows, si le dossier temporaire système est inaccessible, ajouter `--basetemp=scratch/pytest-validation-<identifiant-unique>`.


Les scripts `.sh` sont conservés en LF via `.gitattributes`. Le build Docker normalise aussi `docker-entrypoint.sh` avant de le rendre exécutable : un shebang CRLF provoquerait `exec ./docker-entrypoint.sh: no such file or directory` sous Linux. Après ce correctif, reconstruire avec `docker compose -f docker-compose.prod.yml up -d --build --force-recreate app`.


### Docker local et GitHub

Le workflow CD publie l'image sur GHCR après réussite de la CI. Le déploiement distant est ignoré par défaut ; `DEPLOY_WEBHOOK_URL` et `PROD_URL` ne sont pas nécessaires pour ce mode. Pour activer un hébergeur distant ultérieurement, définir la variable de dépôt GitHub Actions `ENABLE_REMOTE_DEPLOY=true` puis renseigner les deux secrets. Cette variable ne se place pas dans `.env`.

Après réussite de la publication GitHub, mettre à jour Docker local avec :

```powershell
docker compose -f docker-compose.prod.yml pull app
docker compose -f docker-compose.prod.yml up -d --no-deps --no-build --force-recreate app
docker compose -f docker-compose.prod.yml exec app curl -fsS http://localhost:8000/api/ready
```

`--no-deps` ne recrée que l'API. Sans lui, Docker Compose recrée aussi `db`, `redis` et `qdrant` dès que leur définition diffère des conteneurs en place, et peut les rebrancher sur d'autres volumes (`prod_*` au lieu des volumes de `docker-compose.yml`).
