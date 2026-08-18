# 📜 Cahier des Charges Détaillé — ProsArtisan IA Expert

> **Assistant IA Technique & Multimodal pour Artisans du Bâtiment et des Métiers d'Art (Côte d'Ivoire & Zone UEMOA)**

---

## 🎯 1. Vision & Objectifs du Projet

**ProsArtisan** est une plateforme SaaS freemium innovante qui met la puissance de l'IA générative et du RAG (Retrieval-Augmented Generation) au service des artisans sur le terrain. 

L'objectif est d'offrir un **Copilote Technique et Multimodal** capable de :
- Répondre instantanément aux questions techniques du chantier (dosages, normes DTU, assemblages, dépannage).
- Analyser des photos de chantiers (fissures, branchements, pièces de bois ou cuir).
- Communiquer en **français**, **nouchi**, **dioula**, **baoulé** et **bété**, par écrit et par **voix** (StT / TtS).
- Fonctionner de manière fluide via un paiement par **Mobile Money** (Wave, Orange Money, MTN, Moov) et supporter un **mode hors-ligne** pour la consultation des réponses sauvegardées.

---

## 👥 2. Périmètre Métiers & Linguistique

### 🔨 2.1 Métiers Cibles du Lancement (Phase 1)
- **Bâtiment & Travaux Publics (BTP)** : Maçonnerie, Plomberie, Électricité bâtiment, Carrelage & Revêtement, Coffrage & Béton armé, Peinture & Enduits.
- **Métiers d'Art & Artisanat de Précision** : Ébénisterie & Menuiserie d'art, Maroquinerie, Ferronnerie d'art.

### 🗣️ 2.2 Support Multilingue & Vocal
- **Langues supportées** :
  1. **Français** (standard et technique)
  2. **Nouchi** (argot populaire ivoirien des chantiers)
  3. **Dioula / Malinké**
  4. **Baoulé**
  5. **Bété**
- **Intégration Vocale** :
  - **Speech-to-Text (StT)** : Transcription de la voix de l'artisan en texte (ex: OpenAI Whisper).
  - **Text-to-Speech (TtS)** : Synthese vocale de la réponse de l'IA pour écoute sur les chantiers.

---

## 👁️ 3. Fonctionnalités Multimodales & Base de Connaissances RAG

### 📸 3.1 Analyse Multimodale (Vision / Photos)
- L'artisan peut photographier un problème sur son chantier (ex: fissure sur mur, branchement électrique complexe, défaut sur assemblage bois/cuir).
- Le modèle de vision (GPT-4o / GPT-4o-mini Vision) analyse la photo conjointement avec la question et le contexte RAG tagué.

### 📚 3.2 Ingestion des Documents Techniques (Base Vectorielle Qdrant)
- **Sources de données** : Manuels de fabrication, fiches techniques fabricants, fiches FDS, règles DTU.
- **Métadonnées de filtrage (Qdrant)** :
  ```json
  {
    "secteur_id": "batiment",
    "metier_id": "maconnerie",
    "sous_metier_id": "gros-oeuvre",
    "type_document": "norme_dtu",
    "niveau_expertise": "professionnel"
  }
  ```
- **Cycle de mise à jour des connaissances** :
  - **Revue mensuelle** : Ajustement des fiches produit et correctifs.
  - **Évolution trimestrielle** : Ingestion massive de nouveaux manuels et normes.

### 🖥️ 3.3 Back-Office d'Administration Web (Admin Dashboard)
- Interface d'administration dédiée (FastAPI + React / Jinja2 / Tailwind).
- Upload drag-and-drop de PDF / Fiches techniques.
- Découpage automatique (Semantic Chunking) et vectorisation vers Qdrant.
- Tableau de bord des statistiques d'utilisation, requêtes populaires et feedbacks artisans (pouce haut/bas).

---

## 💰 4. Modèle Économique, Quotas & Mobile Money

### 💳 4.1 Offres & Pass
- **Tier Découverte (Gratuit)** : 3 à 5 questions gratuites par jour (réinitialisées automatiquement à minuit via Redis TTL).
- **Pass 24H Urgence Chantier** : 500 FCFA (accès illimité pendant 24 heures).
- **Pass Mensuel Pro** : 3 000 FCFA / mois.
- **Packs de Requêtes** : Ex: Pack 50 recherches (valable sans limite de temps).

### 📱 4.2 Agrégateur & Opérateurs Mobile Money
- Intégration directe avec **Wave Business API**, **Orange Money API**, **MTN MoMo**, **Moov Money** (ou agrégateur CinetPay/TouchPay).
- **Securisation Webhooks** : Vérification stricte des signatures HMAC-SHA256.
- **Magie du Déblocage Temps Réel** : Push WebSocket / FCM (`payment_success`) ➡️ retrait instantané de la modale de paywall et reprise automatique de la question.

---

## 📱 5. Application Mobile & Mode Hors-Ligne (Offline)

### 📲 5.1 Architecture Application Mobile (Flutter / Cross-Platform)
- Interface type Chat moderne (Dark/Light mode).
- Jauge dynamique de crédit en haut de l'écran.
- Écran de Paywall avec copywriting empathique et boutons de paiement Wave/Orange.

### 💾 5.2 Mode Hors-Ligne (Offline Sync)
- **Base de données locale** (SQLite / Hive / WatermelonDB).
- Sauvegarde automatique de l'historique des chats, fiches de réponses et schémas consultés.
- Consultation accessible sans connexion internet sur le chantier.

---

## ⚙️ 6. Architecture Technique Cible

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                 APPLICATION MOBILE (Flutter / WebApp)                       │
│     Chat vocal/texte | Vision Photo | Base Locale Offline (SQLite)          │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ (REST / WebSockets)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       BACKEND FASTAPI (Python 3.12)                         │
│  - Routers : Auth, Chat, Payment, Quotas, Admin                             │
│  - Middleware : Rate Limiter Redis, HMAC Webhooks                           │
└──────────────┬───────────────────────┬───────────────────────┬──────────────┘
               │                       │                       │
               ▼                       ▼                       ▼
┌───────────────────────────┐ ┌───────────────────┐ ┌────────────────────────┐
│   PostgreSQL 16 (DB)      │ │   Redis 7 (Cache) │ │   Qdrant (Vector DB)   │
│ Profils, Abonnements,     │ │ Quotas en direct, │ │ Chunks techniques      │
│ Transactions Mobile Money │ │ Sessions WS       │ │ Filtrés par metier_id  │
└───────────────────────────┘ └───────────────────┘ └────────────────────────┘
```

---

## 🚀 7. Feuille de Route d'Exécution (Roadmap)

1. **Phase 1 : Socle Backend & Modèles DB** *(Terminé ✅)*
   - Base de données PostgreSQL & Redis configurés avec Alembic.
   - Modèles ORM : `User`, `Metier`, `SousMetier`, `QuotaUtilisateur`, `TransactionMobileMoney`.

2. **Phase 2 : Ingestion Qdrant & Pipeline RAG Multimodal** *(Prochaine étape)*
   - Script d'ingestion PDF avec métadonnées (`ingestion/pipeline.py`).
   - Intégration GPT-4o Vision pour l'analyse de photos.

3. **Phase 3 : Webhook Mobile Money & Gateways**
   - Routes d'initialisation de paiement Wave / Orange Money.
   - Validation HMAC et notification WebSocket temps réel.

4. **Phase 4 : Back-Office Web d'Administration**
   - Dashboard Web de gestion des PDF et suivi des transactions.

5. **Phase 5 : Application Mobile Flutter & Audio / Offline**
   - Développement du client Flutter (Audio StT/TtS, SQLite local, Paywall native).
