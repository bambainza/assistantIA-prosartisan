# 📜 Règles & Directives du Projet ProsArtisan

Ce document définit les normes d'ingénierie, les conventions de code et les garde-fous applicables au projet **ProsArtisan IA Expert**.

---

## 🏛️ 1. Architecture & Style de Code

- **Langage & Standard** : Python 3.12+ (PEP 8). Utiliser obligatoirement les type hints (PEP 484) sur toutes les fonctions et méthodes (`def func(param: str) -> bool:`).
- **Style Fonctionnel & Immuabilité** : Préférer les fonctions pures, la composition et l'immuabilité à la mutation directe d'état.
- **Asynchronisme** : Préférer le modèle `async/await` pour toutes les opérations I/O (SQLAlchemy asyncpg, HTTP Client `httpx`, Qdrant `AsyncQdrantClient`).
- **Code Découplé** : Conserver une séparation stricte des responsabilités entre Routers (`app/routers/`), Services Métier (`app/services/`), Schémas (`app/schemas/`) et Modèles ORM (`app/models/`).
- **Migrations Alembic obligatoires** : toute modification de modèle ORM (nouvelle colonne, contrainte, index) doit s'accompagner d'une migration Alembic. Ne jamais compter sur `Base.metadata.create_all` pour faire évoluer un schéma déjà déployé — ce mécanisme ne sert qu'à créer les tables manquantes en développement/tests, il ne modifie jamais une table existante.
- **État partagé entre workers** : tout compteur applicatif (rate limiting, quotas en cache, verrous) doit être stocké dans un backend partagé entre workers/processus (Redis, avec repli mémoire local documenté si Redis est indisponible) — jamais dans un simple attribut de classe Python, qui ne survit pas au multi-processus et se réinitialise à chaque redémarrage.
- **Travaux longs hors requête HTTP** : un traitement potentiellement long (ingestion de document, appel externe lourd) ne doit jamais bloquer la requête qui le déclenche ; utiliser une tâche de fond (`BackgroundTasks` a minima) et renvoyer immédiatement un statut `202 Accepted`.

---

## 🔒 2. Sécurité & Gestion des Secrets

- **Jamais de secrets en dur** : Ne jamais hardcoder de clés API, jetons JWT, mots de passe de base de données ou clés secrètes HMAC dans le code source. Cette règle s'étend aux comptes applicatifs créés par seed (ex. compte administrateur initial) : le mot de passe vient toujours de l'environnement, et son absence en production doit empêcher la création du compte plutôt que de retomber sur une valeur par défaut.
- **Variables d'environnement** : Toutes les configurations doivent passer par `app.config.settings` alimenté par le fichier `.env`.
- **Garde-fous de démarrage en production** : quand `APP_ENV=production`, l'application doit **refuser de démarrer** si `APP_SECRET_KEY`, `JWT_SECRET_KEY`, `MOBILE_MONEY_SECRET_KEY`, `DB_PASSWORD` sont laissés à leur valeur par défaut, si `CORS_ALLOWED_ORIGINS` vaut `*`, ou si `APP_DEBUG` est actif. Un échec explicite au démarrage est toujours préférable à une exécution silencieusement non sécurisée.
- **Identité déduite du JWT, jamais du client** : un `user_id` ne doit jamais être accepté depuis le corps ou les paramètres de requête d'un appel entrant — il est systématiquement déduit du token (`get_current_user_id` / `get_optional_user_id`). Le mode non connecté utilise un identifiant "anonyme" partagé et documenté, jamais une valeur fournie par l'appelant.
- **Isolation par propriétaire (anti-IDOR)** : toute ressource retrouvée via un identifiant opaque dans l'URL (conversation, transaction, document...) doit être filtrée par propriétaire au niveau de la requête (`WHERE user_id = ...`) — un identifiant valide ne suffit jamais à lui seul pour autoriser l'accès, la modification ou la suppression.
- **Validation HMAC SHA-256** : Tous les webhooks entrants (Wave, Orange Money) doivent valider la signature numérique transmise dans l'en-tête HTTP `X-Signature`. Un webhook sans en-tête de signature (ou avec une signature invalide) doit **toujours** être rejeté (`401`) — ne jamais rendre cette vérification optionnelle ou conditionnelle à la présence de l'en-tête.
- **Nettoyage des ressources tierces (Push Protection)** : Lors de l'intégration de templates HTML/JS ou de bibliothèques tierces, s'assurer de purger et de remplacer tous les jetons d'accès ou clés API configurés par défaut par des placeholders (ex. `YOUR_MAPBOX_ACCESS_TOKEN`) afin de ne pas bloquer les pushes vers GitHub (GitHub Push Protection).

---

## 🎯 3. Guardrails RAG & Multilinguisme

- **Zéro Hallucination** : Si les documents techniques ingérés ne contiennent pas l'information requise pour répondre à l'artisan, l'assistant doit déclencher le message de fallback standard sans inventer de règles de chantier.
- **Prise en charge du Nouchi & Langues Locales** : Le prompt système doit maintenir la capacité de comprendre le Nouchi (argot des chantiers), le Dioula, le Baoulé et le Bété, et répondre dans un français clair et technique.
- **Tagging sémantique strict** : Chaque chunk ingéré dans Qdrant doit comporter ses métadonnées obligatoires (`metier_id`, `secteur_id`, `type_document`, `niveau_expertise`).

---

## 🧪 4. Qualité du Code & Non-Régression

- **Tests systématiques** : Toute nouvelle fonctionnalité ou modification d'API doit s'accompagner de tests unitaires/d'intégration dans le répertoire `tests/`.
- **Exécution pytest** : La commande `.\.venv\Scripts\pytest.exe tests/ -v` doit s'exécuter avec **100% de réussite** avant tout commit ou livraison.
- **Tests de régression sécurité** : toute correction d'une faille (IDOR, usurpation d'identité, contournement d'authentification ou de signature webhook) doit être accompagnée d'un test qui échoue de façon démontrable sans le correctif.
- **Fallback DB en test** : Les services doivent intégrer un fallback gracieux lors des tests autonomes si la base de données PostgreSQL ou Redis n'est pas active sur la machine de dev. Ce repli reste strictement un confort de développement/test : voir §2 pour les garde-fous de production associés (`DB_REQUIRE_POSTGRES`, `APP_ENV=production`).
