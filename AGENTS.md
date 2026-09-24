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
- **RBAC (rôles & permissions)** : les comptes admin (`is_admin=True`) peuvent recevoir un rôle RBAC (`app/models/role.py`) affinant leurs permissions. Toute nouvelle route admin sensible doit utiliser `require_permission("<ressource>.<verbe>")` (`app/middleware/auth.py`) plutôt que le seul `get_current_admin_user_id`, dès qu'une permission dédiée a du sens. Un admin sans rôle assigné conserve l'accès complet (compatibilité descendante) — ne jamais casser cette garantie sans migration de données préalable.
- **Journal d'audit obligatoire** : toute mutation admin sensible (création/modification/suppression de package, abonnement, document, rôle, attribution de Pass...) doit écrire une entrée via `app.services.audit_service.audit_service.log_action(...)` avant le `db.commit()` de l'action métier. Une nouvelle route de mutation admin sans trace d'audit est un défaut à corriger, pas une exception acceptable.
- **En-têtes de sécurité HTTP** : `SecurityHeadersMiddleware` (`app/middleware/security_headers.py`) pose CSP/HSTS/X-Frame-Options/Referrer-Policy sur toutes les réponses. Toute nouvelle ressource tierce chargée par `admin_web`/`chat_web` (script, style, iframe) doit être ajoutée explicitement à la CSP plutôt que de relâcher la politique globalement.
- **Documentation interactive masquée en production** : `/docs`, `/redoc` et `/openapi.json` sont désactivés quand `APP_ENV=production` (`app.main.docs_urls`). Ne jamais les réactiver inconditionnellement.
- **2FA (TOTP) pour les comptes admin** : `app/services/totp_service.py`. Un admin avec `totp_enabled=True` doit systématiquement fournir un `totp_code` valide à la connexion (`POST /api/auth/login`) — ne jamais contourner cette vérification, y compris pour des comptes de démonstration.
- **Refresh tokens à usage unique** : chaque refresh token porte un `jti` ; `POST /api/auth/refresh` révoque l'ancien token dès qu'il a servi (rotation) et `POST /api/auth/logout` permet une révocation explicite. Toute nouvelle émission de refresh token doit passer par `create_refresh_token` (jamais un token sans `jti`, non révocable).
- **Notifications** : toute notification doit passer par `app.services.notification_service.notification_service.notify(...)`, qui écrit toujours l'entrée in-app (source de vérité) avant de tenter un canal externe. Un canal externe non configuré (`FCM_SERVER_KEY` absent, pas de device token) doit se dégrader silencieusement (log), jamais lever d'exception bloquante.
- **Diffusion vers de nombreux artisans** : toute action admin qui notifie potentiellement toute la base d'artisans (composer de notifications, publication d'actualité avec notification) doit s'exécuter en `BackgroundTasks` avec sa propre session DB (`async_session()`), jamais dans la requête HTTP d'origine. Une erreur dans cette tâche de fond doit être journalisée et jamais remontée (la requête a déjà répondu).
- **Compteurs de sécurité** : les événements de sécurité qui ne créent pas naturellement de ligne en base (tentative de connexion échouée, webhook rejeté, token révoqué) sont comptabilisés via `cache_service.increment(...)` sous le préfixe `prosartisan:security:` et exposés par `GET /api/admin/security-stats`. Toute nouvelle vérification de sécurité qui peut échouer devrait envisager le même pattern plutôt que de rester invisible au dashboard admin.
- **Clé VAPID (Web Push)** : `VAPID_PRIVATE_KEY` fait partie des secrets vérifiés au démarrage en production (`_verifier_secrets_production`) — la paire de développement intégrée par défaut ne doit jamais servir en production (elle serait alors partagée par tous les déploiements n'ayant pas régénéré leur propre clé).

---

## 🎯 3. Guardrails RAG & Multilinguisme

- **Zéro Hallucination, appliqué en code** : Si les documents techniques ingérés ne contiennent pas l'information requise pour répondre à l'artisan, l'assistant doit déclencher le message de fallback standard sans inventer de règles de chantier. Cette règle doit être **appliquée par le code du service RAG** (court-circuiter l'appel au LLM et renvoyer directement le message de repli s'il n'y a aucun extrait pertinent) et non reposer uniquement sur une instruction du prompt système, qu'un modèle peut ignorer. Le message codé (`FALLBACK_MESSAGE` dans `app/services/rag_service.py`) et celui du prompt système (`prompts/system_prompt.txt`) doivent rester identiques mot pour mot. Un extrait dont le score de similarité est sous le seuil configuré (`RAG_MIN_SCORE`) est traité comme non pertinent : il ne doit jamais servir de contexte au LLM.
- **Prise en charge du Nouchi & Langues Locales** : Le prompt système doit maintenir la capacité de comprendre le Nouchi (argot des chantiers), le Dioula, le Baoulé et le Bété, et répondre dans un français clair et technique.
- **Tagging sémantique strict** : Chaque chunk ingéré dans Qdrant doit comporter ses métadonnées obligatoires (`metier_id`, `secteur_id`, `type_document`, `niveau_expertise`). Ces métadonnées sont validées à l'ingestion (présence, `metier_id`/`secteur_id` numériques positifs) : un document dont les métadonnées sont manquantes ou invalides est rejeté avec une erreur explicite, jamais indexé silencieusement.
- **Cohérence des embeddings** : les vecteurs d'ingestion et de recherche doivent provenir de la même fonction d'embedding (`rag_service.get_embedding`, cache et mode mock inclus). Ne jamais introduire de vecteur factice ou codé en dur dans le pipeline d'ingestion : la recherche sémantique deviendrait inopérante même après ingestion de vrais documents.

---

## 🧪 4. Qualité du Code & Non-Régression

- **Tests systématiques** : Toute nouvelle fonctionnalité ou modification d'API doit s'accompagner de tests unitaires/d'intégration dans le répertoire `tests/`.
- **Exécution pytest** : La commande `.\.venv\Scripts\pytest.exe tests/ -v` doit s'exécuter avec **100% de réussite** avant tout commit ou livraison.
- **Tests de régression sécurité** : toute correction d'une faille (IDOR, usurpation d'identité, contournement d'authentification ou de signature webhook) doit être accompagnée d'un test qui échoue de façon démontrable sans le correctif.
- **Fallback DB en test** : Les services doivent intégrer un fallback gracieux lors des tests autonomes si la base de données PostgreSQL ou Redis n'est pas active sur la machine de dev. Ce repli reste strictement un confort de développement/test : voir §2 pour les garde-fous de production associés (`DB_REQUIRE_POSTGRES`, `APP_ENV=production`).

---

## 📝 5. Synchronisation obligatoire de la documentation

- **Contrôle bloquant avant Git** : avant chaque `git commit` puis avant chaque `git push`, relire et mettre à jour systématiquement la documentation de référence pour toute implémentation ou modification, même mineure. Il est interdit de committer ou pousser tant que ce contrôle n'est pas terminé.
- **PRD/PDR** : mettre à jour `PDR.md` pour tout changement de comportement produit, parcours utilisateur, endpoint, architecture, intégration externe, configuration, offre commerciale ou procédure de validation.
- **Règles agents/IDE** : lorsqu'une règle d'ingénierie, de sécurité, de qualité ou de livraison évolue, synchroniser obligatoirement `AGENTS.md`, `CLAUDE.md` et `.agents/rules/project_rules.md`. Aucun de ces fichiers ne doit contredire les autres.
- **Exploitation** : mettre à jour `.env.example`, `README.md` et les manifests de déploiement concernés dès qu'une variable d'environnement, une dépendance, une commande ou une procédure opérationnelle change.
- **Traçabilité du contrôle** : si la relecture conclut qu'aucune modification documentaire supplémentaire n'est nécessaire, le signaler explicitement dans le compte rendu avant le commit et confirmer à nouveau la cohérence avant le push. Cette confirmation ne dispense jamais de la relecture systématique.
