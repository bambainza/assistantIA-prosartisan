# 📜 Règles & Directives du Projet ProsArtisan

Ce document définit les normes d'ingénierie, les conventions de code et les garde-fous applicables au projet **ProsArtisan IA Expert**.

---

## 🏛️ 1. Architecture & Style de Code

- **Langage & Standard** : Python 3.12+ (PEP 8). Utiliser obligatoirement les type hints (PEP 484) sur toutes les fonctions et méthodes (`def func(param: str) -> bool:`).
- **Style Fonctionnel & Immuabilité** : Préférer les fonctions pures, la composition et l'immuabilité à la mutation directe d'état.
- **Asynchronisme** : Préférer le modèle `async/await` pour toutes les opérations I/O (SQLAlchemy asyncpg, HTTP Client `httpx`, Qdrant `AsyncQdrantClient`).
- **Code Découplé** : Conserver une séparation stricte des responsabilités entre Routers (`app/routers/`), Services Métier (`app/services/`), Schémas (`app/schemas/`) et Modèles ORM (`app/models/`).

---

## 🔒 2. Sécurité & Gestion des Secrets

- **Jamais de secrets en dur** : Ne jamais hardcoder de clés API, jetons JWT, mots de passe de base de données ou clés secrètes HMAC dans le code source.
- **Variables d'environnement** : Toutes les configurations doivent passer par `app.config.settings` alimenté par le fichier `.env`.
- **Validation HMAC SHA-256** : Tous les webhooks entrants (Wave, Orange Money) doivent valider la signature numérique transmise dans l'en-tête HTTP `X-Signature`.
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
- **Fallback DB en test** : Les services doivent intégrer un fallback gracieux lors des tests autonomes si la base de données PostgreSQL ou Redis n'est pas active sur la machine de dev.
