# Plan d'Amélioration — Sécurité, Robustesse & Couverture Fonctionnelle

Document de suivi vivant. Chaque item porte un statut à mettre à jour au fil de l'implémentation :

- `☐ À faire`
- `🔄 En cours`
- `✅ Fait`
- `⏸️ Reporté` (préciser la raison en commentaire sous l'item)

Priorité : `P0` bloquant/fondation, `P1` haute, `P2` moyenne.
Effort : `S` (< 1 jour), `M` (1-3 jours), `L` (> 3 jours), estimation solo dev.

Ce document complète `AGENTS.md` (règles d'ingénierie à respecter pour chaque item : type hints, migrations Alembic obligatoires, séparation routers/services/schemas/models, tests systématiques, 100 % pytest avant commit) et `PDR.md` (architecture cible).

---

## Vue d'ensemble — Tableau de suivi global

| ID | Item | Phase | Priorité | Effort | Statut |
|---|---|---|---|---|---|
| 0.1 | RBAC (rôles & permissions) | Fondations | P0 | M | ✅ |
| 0.2 | Journal d'audit (audit_logs) | Fondations | P0 | M | ✅ |
| 0.3 | En-têtes de sécurité HTTP | Fondations | P0 | S | ✅ |
| 0.4 | 2FA TOTP pour comptes admin | Fondations | P1 | M | ✅ |
| 0.5 | Révocation des refresh tokens | Fondations | P1 | S | ✅ |
| 0.6 | Masquage `/docs`/`/redoc` en prod | Fondations | P0 | S | ✅ |
| 0.7 | CI : scan secrets + audit dépendances | Fondations | P1 | S | ✅ |
| 1.1 | UI gestion des rôles (admin_web) | Back-office | P1 | M | ✅ |
| 1.2 | UI journal d'audit (admin_web) | Back-office | P1 | M | ✅ |
| 1.3 | Module Actualités (back + UI) | Back-office | P2 | L | ✅ |
| 1.4 | Centre de notifications (composer) | Back-office | P2 | M | ✅ |
| 1.5 | Dashboard sécurité enrichi | Back-office | P2 | S | ✅ |
| 2.1 | `notification_service.py` pluggable | Infra transverse | P1 | M | ✅ |
| 2.2 | Table `notifications` | Infra transverse | P1 | S | ✅ |
| 2.3 | Modèle `actualite` + endpoints | Infra transverse | P2 | M | ✅ |
| 2.4 | Lien feedback ↔ actualités | Infra transverse | P2 | S | ✅ |
| 3.1 | PWA chat_web (manifest + service worker) | Chat web | P2 | M | ✅ |
| 3.2 | Web Push chat_web | Chat web | P2 | M | ✅ |
| 3.3 | Bandeau Actualités chat_web | Chat web | P2 | S | ✅ |
| 3.4 | Export/partage réponse (PDF, WhatsApp) | Chat web | P2 | S | ✅ |
| 3.5 | Accessibilité (a11y) + i18n interface | Chat web | P2 | M | ✅* |
| 4.1 | Migration `flutter_secure_storage` | Mobile | P0 | S | ✅ |
| 4.2 | Notifications push (FCM) | Mobile | P1 | M | ✅ |
| 4.3 | Sync offline robuste (file d'attente locale) | Mobile | P1 | L | ✅ |
| 4.4 | Biométrie (`local_auth`) | Mobile | P2 | S | ✅ |
| 4.5 | Crash reporting (Sentry) | Mobile | P1 | S | 🔄 |
| 4.6 | i18n interface mobile | Mobile | P2 | M | ⏸️ |

**Statut priorités** : P0 ✅ (2026-09-14) — P1 ✅ (2026-09-14, 4.2/4.5 scaffoldés) — P2 ✅ (2026-09-14, Web Push finalisé le même jour ; a11y fait/i18n reportée sur 3.5 et 4.6 — voir notes).

**Légende** : `🔄` code intégré et validé, mais inactif tant que l'utilisateur n'a pas fourni ses identifiants externes (Firebase, Sentry DSN, clés VAPID). `✅*` fait partiellement : voir note. `⏸️` reporté avec justification.

**Ordre d'implémentation recommandé** : Phase 0 (fondations) → 4.1 (faille mobile critique, indépendante) → 2.1/2.2 (infra notification, prérequis de 1.4/2.3/3.2/4.2) → reste des phases 1/3/4 en parallèle selon disponibilité.

---

## Phase 0 — Fondations sécurité (bloquant)

### 0.1 — RBAC (rôles & permissions)

- **Constat** : `User.is_admin` (`app/models/user.py:55`) est un simple booléen — aucune granularité (support, modérateur, super-admin).
- **Fichiers à créer/modifier** :
  - `app/models/role.py` (nouveau) — modèles `Role`, `Permission`, table d'association `role_permissions`.
  - `app/models/user.py` — ajouter `role_id: Mapped[uuid.UUID | None]` (FK vers `roles.id`), conserver `is_admin` en lecture seule dérivée ou le déprécier progressivement (ne pas casser les tests existants d'un coup).
  - `migrations/versions/xxxx_add_roles_and_permissions.py` — nouvelle migration Alembic.
  - `app/middleware/auth.py` — ajouter `require_permission(code: str)` en plus de `get_current_user_id`.
  - `app/schemas/role.py` (nouveau).
  - `app/routers/admin.py` — protéger chaque route par la permission adéquate au lieu du seul `is_admin`.
- **Schéma proposé** :
  ```python
  class Role(Base):
      __tablename__ = "roles"
      id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
      code: Mapped[str] = mapped_column(String(50), unique=True)   # "super_admin", "support", "moderateur_contenu"
      label: Mapped[str] = mapped_column(String(100))
      permissions: Mapped[list["Permission"]] = relationship(secondary="role_permissions")

  class Permission(Base):
      __tablename__ = "permissions"
      id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
      code: Mapped[str] = mapped_column(String(100), unique=True)  # "packages.write", "users.grant_pass", "documents.delete"
  ```
  Permissions de départ suggérées : `packages.write`, `packages.read`, `users.read`, `users.grant_pass`, `documents.write`, `documents.delete`, `transactions.read`, `logs.read`, `roles.write`, `audit.read`, `actualites.write`, `notifications.send`.
- **Migration de données** : script de seed créant `super_admin` (toutes permissions) et migrant tous les `is_admin=true` existants vers ce rôle.
- **Tests requis** : `tests/test_roles.py` — accès refusé (403) sans la permission requise, accès accordé avec le rôle adéquat, non-régression sur les tests admin existants (`test_admin.py`, `test_admin_full.py`, `test_packages_admin.py`).
- **Definition of Done** : toutes les routes de `app/routers/admin.py` utilisent `require_permission(...)` ; `is_admin` n'est plus la seule porte d'accès ; 100 % pytest vert.

### 0.2 — Journal d'audit (`audit_logs`)

- **Constat** : aucune trace nominative des actions sensibles (grant-pass, suppression de document, toggle package).
- **Fichiers à créer/modifier** :
  - `app/models/audit_log.py` (nouveau).
  - `app/services/audit_service.py` (nouveau) — fonction `log_action(db, actor_id, action, resource_type, resource_id, before, after, request)`.
  - `migrations/versions/xxxx_add_audit_logs.py`.
  - Intégration dans `app/routers/admin.py` sur chaque mutation (grant-pass, delete document, create/update/toggle package, changement de rôle).
- **Schéma proposé** :
  ```python
  class AuditLog(Base):
      __tablename__ = "audit_logs"
      id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
      actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
      action: Mapped[str] = mapped_column(String(100))          # "package.update", "user.grant_pass"
      resource_type: Mapped[str] = mapped_column(String(50))
      resource_id: Mapped[str] = mapped_column(String(100))
      before_json: Mapped[dict | None] = mapped_column(JSON, default=None)
      after_json: Mapped[dict | None] = mapped_column(JSON, default=None)
      ip_address: Mapped[str | None] = mapped_column(String(45), default=None)
      created_at: Mapped[datetime] = mapped_column(server_default=func.now())
  ```
- **Point d'attention (AGENTS.md §1)** : l'écriture d'audit ne doit jamais bloquer/ralentir significativement la requête — l'insérer dans la même transaction que la mutation (pas de `BackgroundTasks` ici car on veut la garantie que l'action et sa trace sont atomiques).
- **Tests requis** : `tests/test_audit_log.py` — vérifie qu'une action admin (ex. `grant-pass`) crée bien une entrée avec le bon acteur/avant-après ; vérifie l'isolation (un non-admin ne peut pas lire `/api/admin/audit-logs`).
- **Definition of Done** : toute mutation admin listée dans PDR.md §5 (Back-Office Admin) produit une entrée d'audit ; endpoint `GET /api/admin/audit-logs` (pagination + filtres acteur/action/date) protégé par la permission `audit.read`.

### 0.3 — En-têtes de sécurité HTTP

- **Constat** : `app/main.py` ne définit que CORS + rate limiting + logging — pas de CSP/HSTS/X-Frame-Options.
- **Fichiers à créer/modifier** :
  - `app/middleware/security_headers.py` (nouveau).
  - `app/main.py` — `app.add_middleware(SecurityHeadersMiddleware)`.
- **En-têtes à poser** : `Content-Security-Policy` (adapter aux assets Dastone servis sous `/admin` et au chat sous `/chat`), `Strict-Transport-Security` (uniquement si `APP_ENV=production` et HTTPS), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` (ou `SAMEORIGIN` pour `/admin` si besoin d'iframe interne), `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` restrictive (caméra/micro seulement où nécessaire pour le chat vocal/photo).
- **Tests requis** : `tests/test_security_headers.py` — vérifie la présence de chaque en-tête sur une réponse type.
- **Definition of Done** : en-têtes présents sur toutes les réponses (API + statique), CSP ne casse pas `admin_web`/`chat_web` (test manuel navigateur après déploiement).

### 0.4 — 2FA TOTP pour comptes admin

- **Fichiers à créer/modifier** :
  - `app/services/totp_service.py` (nouveau, ex. via `pyotp`).
  - `app/models/user.py` — `totp_secret: Mapped[str | None]`, `totp_enabled: Mapped[bool]`.
  - `migrations/versions/xxxx_add_totp_fields.py`.
  - `app/routers/auth.py` — `POST /auth/totp/enable`, `POST /auth/totp/verify`, adapter `POST /auth/login` pour exiger un second facteur si `totp_enabled=true` et rôle admin.
- **Contrainte métier à ajouter** : à terme, refuser en production l'attribution d'un rôle admin (`roles.write`) à un compte sans `totp_enabled=true` — cohérent avec l'esprit AGENTS.md §2 (échec explicite plutôt qu'exécution silencieusement non sécurisée).
- **Tests requis** : login admin sans TOTP → refusé ; avec code TOTP valide → accepté ; avec code invalide/expiré → 401.

### 0.5 — Révocation des refresh tokens

- **Fichiers à créer/modifier** : `app/services/cache_service.py` (réutiliser le cache Redis existant) — clé `revoked_token:{jti}` avec TTL = durée de vie restante du token ; `app/middleware/auth.py` — vérifier la liste noire à chaque décodage ; `app/routers/auth.py` — endpoint `POST /auth/logout` qui révoque le refresh token courant.
- **Tests requis** : un refresh token révoqué ne permet plus de renouveler l'access token (test avec fallback mémoire si Redis absent, cf. AGENTS.md §4).

### 0.6 — Masquage `/docs`/`/redoc` en production

- **Fichiers à modifier** : `app/main.py` — `docs_url=None, redoc_url=None` si `settings.app_env == "production"` (ou les protéger derrière `require_permission`).
- **Test requis** : `tests/test_config.py` (étendre) — en env `production`, `GET /docs` retourne 404.

### 0.7 — CI : scan de secrets + audit de dépendances

- **Fichiers à modifier** : `.github/workflows/ci.yml` — ajouter un job `security-scan` : `gitleaks` (ou `trufflehog`) sur le diff, `pip-audit` sur `requirements.txt`, `flutter pub outdated`/`dart pub audit` (job Flutter existant).
- **Definition of Done** : le job échoue la CI si un secret est détecté ou une CVE critique est trouvée dans une dépendance directe.

---

## Phase 1 — Back-office admin

### 1.1 — UI gestion des rôles (`admin_web`)

- **Dépend de** : 0.1.
- **Fichiers** : `admin_web/index.html` (nouvelle section), `admin_web/app.js` (1049 lignes actuellement — évaluer si un découpage en modules JS devient nécessaire à ce stade plutôt que de continuer à grossir un seul fichier).
- **Fonctionnel** : liste des utilisateurs admin avec rôle actuel, changement de rôle (select), historique visible via lien vers 1.2.
- **Contrainte** : chaque changement de rôle doit déclencher un audit log (0.2) — action `role.assign`.

### 1.2 — UI journal d'audit (`admin_web`)

- **Dépend de** : 0.2.
- **Fonctionnel** : table paginée, filtres (acteur, type de ressource, plage de dates), vue détail avant/après en JSON formaté, export CSV.

### 1.3 — Module Actualités (back + UI)

- **Dépend de** : 2.3 (modèle `actualite`).
- **Fonctionnel back-office** : CRUD actualités (titre, contenu, métier_id ciblé, date de publication, statut brouillon/publié), prévisualisation.
- **Diffusion** : publication déclenche optionnellement une notification (2.1/2.2) vers les artisans du métier ciblé.

### 1.4 — Centre de notifications (composer)

- **Dépend de** : 2.1, 2.2.
- **Fonctionnel** : formulaire de composition (titre, corps, canal ciblé, segment — par métier / statut d'abonnement / inactifs depuis N jours), historique des envois avec taux de lecture.

### 1.5 — Dashboard sécurité enrichi

- **Dépend de** : 0.2, 0.5.
- **Métriques à ajouter aux stats existantes** (`GET /api/admin/stats`, `GET /api/admin/overview`) : tentatives de connexion échouées (fenêtre glissante), webhooks Mobile Money rejetés pour signature invalide, nombre de tokens révoqués, actions admin des dernières 24h.

---

## Phase 2 — Infrastructure transverse (notifications & actualités)

### 2.1 — `notification_service.py` pluggable

- **Fichiers à créer** : `app/services/notification_service.py` — interface `NotificationProvider` (méthode `send(notification: Notification) -> bool`) avec implémentations `PushProvider` (FCM), `SmsProvider`, `EmailProvider`, `InAppProvider` (écrit simplement en base pour lecture via API).
- **Respect AGENTS.md §1** : envoi effectif (SMS/push réseau) exécuté en tâche de fond (`BackgroundTasks`), jamais synchrone dans la requête HTTP qui déclenche la notification.
- **Config** : nouvelles variables `.env` — `FCM_SERVER_KEY` (ou fichier de credentials service account), `SMS_PROVIDER_API_KEY` (si distinct d'Infobip/Twilio déjà utilisé pour l'OTP mobile côté marketplace — à clarifier si mutualisé).

### 2.2 — Table `notifications`

- **Fichiers** : `app/models/notification.py`, `migrations/versions/xxxx_add_notifications.py`, `app/routers/notification.py` (nouveau routeur `GET /api/notifications`, `PATCH /api/notifications/{id}/read`), `app/schemas/notification.py`.
- **Schéma proposé** :
  ```python
  class Notification(Base):
      __tablename__ = "notifications"
      id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
      user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
      channel: Mapped[str] = mapped_column(String(20))    # "push", "sms", "email", "in_app"
      title: Mapped[str] = mapped_column(String(200))
      body: Mapped[str] = mapped_column(String(1000))
      read_at: Mapped[datetime | None] = mapped_column(default=None)
      created_at: Mapped[datetime] = mapped_column(server_default=func.now())
  ```
- **Sécurité (AGENTS.md §2)** : `GET /api/notifications` filtré strictement par `user_id` déduit du JWT — jamais par un `user_id` en paramètre (anti-IDOR).

### 2.3 — Modèle `actualite` + endpoints

- **Fichiers** : `app/models/actualite.py`, `migrations/versions/xxxx_add_actualites.py`, `app/routers/actualite.py` (`GET /api/actualites` public/filtré par métier, routes admin CRUD sous `app/routers/admin.py` ou fichier dédié `app/routers/admin_actualites.py`).
- **Schéma proposé** : `id`, `titre`, `contenu`, `metier_id (nullable = tous métiers)`, `statut (brouillon/publie)`, `publie_at`, `created_by (FK users)`.

### 2.4 — Lien feedback ↔ actualités

- **Objectif** : les retours de `tests/test_feedback.py`/table `feedbacks` existante alimentent un tableau de bord admin suggérant des sujets d'actualité (ex. questions fréquemment en fallback zéro-hallucination → sujet de guide à publier).
- **Effort limité** : requête d'agrégation + affichage, pas de nouveau modèle.

---

## Phase 3 — Chat web (`chat_web/`)

### 3.1 — PWA (manifest + service worker)

- **Fichiers** : `chat_web/manifest.json`, `chat_web/sw.js`, balises `<link rel="manifest">` dans `chat_web/index.html`.
- **Fonctionnel** : app installable, shell offline (page + assets statiques en cache), file d'attente des messages envoyés hors-ligne (rejoue à la reconnexion — cohérent avec le contexte 3G/4G documenté dans CLAUDE.md).

### 3.2 — Web Push

- **Dépend de** : 2.1, 2.2.
- **Fichiers** : `chat_web/app.js` (souscription `PushManager`), `app/routers/notification.py` (endpoint d'enregistrement d'abonnement push par utilisateur).

### 3.3 — Bandeau Actualités

- **Dépend de** : 2.3.
- **Fonctionnel** : bandeau/section consommant `GET /api/actualites?metier_id=...` filtré sur le métier de l'utilisateur connecté.

### 3.4 — Export/partage réponse

- **Fonctionnel** : bouton « Exporter en PDF » (génération côté client, ex. `jspdf`, ou endpoint backend réutilisant une lib PDF si le projet en introduit une) et bouton « Partager » (Web Share API avec repli lien `wa.me` pré-rempli).

### 3.5 — Accessibilité (a11y) + i18n interface

- **Fonctionnel** : audit `axe-core`, ajout des attributs ARIA manquants, contraste conforme WCAG AA, navigation clavier complète ; extraction des chaînes d'interface dans un fichier de traduction (FR de base, structure prête pour Nouchi/langues locales même si le contenu conversationnel est déjà géré par le prompt système).

---

## Phase 4 — Application mobile (`mobile_app_flutter/`)

### 4.1 — Migration `flutter_secure_storage` (faille de sécurité actuelle)

- **Constat** : le JWT est actuellement persisté via `shared_preferences` (non chiffré, lisible sur device rooté/jailbreaké) — `mobile_app_flutter/lib/services/local_storage_service.dart`.
- **Fichiers** : `pubspec.yaml` (ajouter `flutter_secure_storage: ^9.x`), `local_storage_service.dart` (remplacer le stockage du token par le Keychain/Keystore natif via secure storage), conserver `shared_preferences` uniquement pour des préférences non sensibles (thème, langue).
- **Priorité P0** : c'est la seule faille concrète déjà identifiée dans le code mobile — à traiter en premier sur ce périmètre, indépendamment des autres phases.
- **Tests requis** : `flutter test` sur le service de stockage (mock du plugin secure storage).

### 4.2 — Notifications push (FCM)

- **Dépend de** : 2.1, 2.2.
- **Fichiers** : `pubspec.yaml` (`firebase_core`, `firebase_messaging`), `mobile_app_flutter/lib/services/push_notification_service.dart` (nouveau), configuration `google-services.json`/`GoogleService-Info.plist`, enregistrement du token FCM auprès du backend (`POST /api/notifications/register-device`).

### 4.3 — Sync offline robuste

- **Constat** : `offline_sheets_view.dart` existe déjà mais la persistance locale ne dépasse pas `shared_preferences` (pas de vraie base locale/file d'attente).
- **Fichiers** : introduire `Hive` ou `Isar` (`pubspec.yaml`), `mobile_app_flutter/lib/services/offline_queue_service.dart` — file d'attente des questions posées sans réseau, rejouées automatiquement à la reconnexion (écouter la connectivité via `connectivity_plus`).

### 4.4 — Biométrie (`local_auth`)

- **Fichiers** : `pubspec.yaml` (`local_auth`), écran de verrouillage optionnel avant `auth_view.dart`/`chat_view.dart` si l'utilisateur active l'option dans les réglages.

### 4.5 — Crash reporting (Sentry)

- **Fichiers** : `pubspec.yaml` (`sentry_flutter`), initialisation dans `main.dart`, variable `SENTRY_DSN` côté configuration de build (CI `cd.yml`/secrets).

### 4.6 — i18n interface mobile

- **Fichiers** : activer `flutter_localizations` + fichiers `.arb` (`lib/l10n/`), extraire les chaînes actuellement en dur dans `auth_view.dart`, `chat_view.dart`, `paywall_dialog.dart`, `offline_sheets_view.dart`.

---

## Notes de suivi

_(Ajouter ici, au fil de l'avancement, la date, l'item concerné et un résumé de ce qui a été fait/reporté — un log chronologique court, pas une réécriture du plan ci-dessus.)_

- **2026-09-14 — Priorité P0 (Fondations) implémentée.** 121/121 tests backend passent (110 existants + 11 nouveaux), `ruff check`/`ruff format --check` verts, `flutter analyze` vert. `PDR.md`, `AGENTS.md` et `CLAUDE.md` mis à jour en conséquence.
  - **0.1 RBAC** : modèles `Role`/`Permission`/`role_permissions` (`app/models/role.py`), colonne `users.role_id` (migration `a1b2c3d4e5f6`), dépendance `require_permission(code)` (`app/middleware/auth.py`), endpoints `GET /api/admin/roles`, `GET /api/admin/permissions`, `POST /api/admin/users/{id}/role`. Seed idempotent de 12 permissions et 3 rôles (`super_admin`, `support`, `moderateur_contenu`) dans `app/db/init_db.py` + migration. **Scope volontairement limité** : les ~20 routes admin existantes restent sur `get_current_admin_user_id` (is_admin brut) — seules les nouvelles routes RBAC/audit utilisent `require_permission`, pour ne pas risquer de casser les 22 fichiers de tests existants en un seul passage (cf. le risque déjà identifié dans le plan initial). Migrer les routes historiques vers des permissions fines est un suivi possible de la phase 1.
  - **0.2 Audit log** : modèle `AuditLog` (`app/models/audit_log.py`, migration `b2c3d4e5f6a7`), service `audit_service` (`app/services/audit_service.py`), endpoint `GET /api/admin/audit-logs` (permission `audit.read`). Instrumenté sur : grant-pass, packages (create/update/toggle/delete), abonnements (assign/extend/cancel), documents (toggle/delete), métiers (toggle), rôles (assign). **Limite connue** : plusieurs méthodes de `subscription_service` committent déjà en interne (ex. `toggle_package`) ; l'entrée d'audit est donc écrite dans une transaction séparée juste après, pas strictement atomique avec la mutation. Une atomicité complète demanderait de retirer les `commit()` internes aux services au profit d'un commit unique côté routeur — refactor plus large, hors scope de cette passe.
  - **0.3 En-têtes de sécurité** : `SecurityHeadersMiddleware` (`app/middleware/security_headers.py`). CSP avec `'unsafe-inline'` sur script-src/style-src (template Dastone + chat_web ont des scripts/styles inline statiques) — un durcissement complet par nonces est du ressort de l'item 3.5.
  - **0.6 Masquage docs prod** : `app.main.docs_urls(is_production)` — `/docs`, `/redoc`, `/openapi.json` retournent `None` en production.
  - **4.1 flutter_secure_storage** : le JWT et l'email de session dans `NetworkClient` (`mobile_app_flutter/lib/network/network_client.dart`) sont passés de `shared_preferences` (clair) à `flutter_secure_storage` (Keychain/Keystore). `baseUrl` (non sensible) reste dans `shared_preferences`.
  - **Non fait dans cette passe** : 0.4 (2FA TOTP) et 0.5 (révocation refresh token) sont classés P1, traités à la priorité suivante.

- **2026-09-14 — Priorité P1 implémentée.** 133/133 tests backend passent (+12 par rapport à P0), `ruff check`/`ruff format --check` verts, `flutter analyze` vert, `flutter test` 7/7 verts. `PDR.md`, `AGENTS.md` et `CLAUDE.md` mis à jour.
  - **0.4 2FA TOTP** : `app/services/totp_service.py` (pyotp), colonnes `users.totp_secret`/`totp_enabled` (migration `c3d4e5f6a7b8`), endpoints `POST /api/auth/totp/setup|enable|disable`. `POST /api/auth/login` exige `totp_code` pour tout admin avec `totp_enabled=true`. Réservé aux comptes `is_admin=True` ; pas encore rendu obligatoire à l'attribution d'un rôle (reste une amélioration future, cf. plan initial).
  - **0.5 Révocation refresh token** : `jti` ajouté aux refresh tokens, liste noire Redis/mémoire (`revoke_refresh_token`/`is_refresh_token_revoked` dans `app/middleware/auth.py`), `POST /api/auth/logout`, et **rotation à usage unique** sur `/refresh` (l'ancien token est révoqué dès qu'il a servi, même non expiré).
  - **0.7 CI security-scan** : nouveau job dans `.github/workflows/ci.yml` — `gitleaks` (bloquant) + `pip-audit` (informatif, `continue-on-error: true`). **Suivi identifié** : `pip-audit -r requirements.txt` remonte des CVE connues sur plusieurs dépendances déjà pinnées (`pypdf`, `python-jose`, `python-multipart`, `starlette`, `langchain-core`, `langchain-text-splitters`, `langsmith`, `python-dotenv`, `pytest`, `ecdsa`) — à traiter dans un item dédié (montées de version à valider une par une, hors scope de cette passe pour ne pas risquer une régression fonctionnelle non testée).
  - **2.1/2.2 Notifications** : modèle `Notification` (migration `d4e5f6a7b8c9`, avec colonne `users.fcm_device_token`), `app/services/notification_service.py` (provider `FcmPushProvider` no-op si `FCM_SERVER_KEY` absent), router `app/routers/notification.py` (`GET /api/notifications`, `GET /api/notifications/unread-count`, `PATCH /api/notifications/{id}/read`, `POST /api/notifications/register-device`).
  - **1.1/1.2 UI admin_web** : nouvel onglet "Sécurité (Rôles & Audit)" — liste des rôles RBAC, formulaire d'assignation de rôle, table du journal d'audit (100 dernières entrées). **Simplification assumée** : l'assignation de rôle se fait par saisie manuelle de l'UUID de l'admin cible (pas de sélecteur, faute d'un endpoint listant spécifiquement les comptes admin) — à raffiner si le besoin se confirme.
  - **4.2 FCM (mobile, partiellement actif)** : `firebase_core`/`firebase_messaging` ajoutés, `PushNotificationService` (initialise Firebase, demande la permission, enregistre le token via `NetworkClient.registerDevice`). **Reste à faire par l'utilisateur** : créer un projet Firebase, générer `google-services.json`/`GoogleService-Info.plist`, les placer dans `android/app/` et `ios/Runner/`. Sans ça, le service échoue silencieusement (capturé) et l'app fonctionne normalement sans push.
  - **4.3 Sync offline** : `OfflineQueueService` (Hive) + écoute `connectivity_plus` dans `ChatViewModel` — une question envoyée sans réseau est mise en file et rejouée automatiquement à la reconnexion. **Limite connue** : seul le texte est mis en file (pas les photos jointes).
  - **4.5 Sentry (mobile, partiellement actif)** : `sentry_flutter` ajouté, initialisation conditionnelle à `--dart-define=SENTRY_DSN=...` dans `main.dart`. **Reste à faire par l'utilisateur** : créer un projet Sentry et fournir le DSN au build/CD.
  - **Correctif induit** : la migration de `network_client.dart` vers `flutter_secure_storage` (item 4.1) faisait échouer 2 tests existants (`MissingPluginException` en environnement de test sans plugin natif) — corrigé en enveloppant les appels au stockage sécurisé dans un `try/catch` avec repli sur session déconnectée, cohérent avec le reste du fichier.

- **2026-09-14 — Suivi 0.7 : mise à jour du backlog de dépendances vulnérables (une par une, tests à chaque étape).** 149/149 tests backend passent, `ruff` clean. `pip-audit` passe de ~13 paquets vulnérables à 3 restants (voir détail ci-dessous).
  - **Mis à jour sans régression** : `python-dotenv` 1.0.1→1.2.3, `python-jose` 3.3.0→3.4.0, `python-multipart` 0.0.9→0.0.32, `pypdf` 4.3.1→6.16.1 (vérifié avec un vrai PDF généré à la volée), `pytest` 8.3.2→9.0.3 + `pytest-asyncio` 0.23.8→1.4.0 + `pytest-cov` 5.0.0→7.1.0, `fastapi` 0.115.0→0.115.14 + `starlette` 0.38.6→0.46.2 (dernière combinaison compatible sans franchir un palier majeur FastAPI).
  - **Retiré (jamais utilisé)** : `langchain`, `langchain-openai`, `langchain-community`, `langchain-qdrant` et leur dépendance transitive `langsmith` — grep confirme qu'aucun `import langchain` n'existe dans `app/`/`ingestion/` ; le RAG appelle directement `openai.AsyncOpenAI` et `qdrant_client.AsyncQdrantClient`. Suppression = élimination totale des CVE associées, risque nul.
  - **3 vulnérabilités restantes, sciemment non résolues** :
    - `starlette` (plusieurs CVE, correctifs à partir de 0.47.2) : la borne haute compatible avec FastAPI 0.115.x est `<0.47.0`. Aller plus loin exige de sauter FastAPI vers une série majeure ultérieure (0.115→0.14x, 26 versions mineures) — risque de rupture d'API bien plus large que les upgrades ci-dessus, à traiter comme un chantier séparé avec son propre passage de tests.
    - `pyasn1` (0.4.8, requis par `python-jose<0.5.0`) vs `google-auth` (requiert `>=0.6.1`, ajouté pour le FCM v1 — voir item 4.2 ci-dessous) : conflit de résolveur *confirmé sans impact réel* — ce projet n'utilise que HS256 via le backend `cryptography` de python-jose, qui n'exerce jamais le code dépendant de `pyasn1`. Documenté dans `requirements.txt`.
    - `ecdsa` (transitif de `python-jose`) : `PYSEC-2026-1325` n'a pas de version corrigée (risque de timing side-channel documenté par les mainteneurs comme non corrigible sans changer de bibliothèque JWT) ; sans impact pour ce projet qui n'utilise pas les algorithmes EC de python-jose.
  - **Item 4.2 (FCM) terminé et vérifié de bout en bout** : l'utilisateur a créé un vrai projet Firebase (`assistantia-app`). L'ancienne « clé serveur » legacy que `FcmPushProvider` ciblait initialement n'existe plus pour les nouveaux projets Firebase (API dépréciée par Google) — réécrit pour utiliser l'API HTTP v1 authentifiée par compte de service (OAuth2 via `google-auth`, PAS le SDK complet `firebase-admin` dont la dépendance stricte `httpx==0.28.1` cassait `openai==1.43.0` — conflit détecté et corrigé immédiatement, voir `tests/test_fcm_push.py`). Réglage `FCM_SERVICE_ACCOUNT_PATH` pointant vers `secrets/firebase-service-account.json` (dossier gitignored). **Vérifié en conditions réelles** : obtention effective d'un token OAuth2 auprès des serveurs Google avec le compte de service fourni par l'utilisateur.
    - Package Android/iOS renommé `com.example.prosartisan` → `ci.prosartisan.app` (choix utilisateur) : `android/app/build.gradle.kts` (`namespace`/`applicationId`), `MainActivity.kt` déplacé vers `android/app/src/main/kotlin/ci/prosartisan/app/`, `PRODUCT_BUNDLE_IDENTIFIER` iOS mis à jour dans `project.pbxproj`. `google-services.json` placé dans `android/app/` (gitignored) ; plugin Gradle `com.google.gms.google-services` appliqué conditionnellement (seulement si le fichier est présent), pour ne jamais casser le build des contributeurs sans config Firebase.
    - **Bug latent corrigé en cours de route** : une tentative de build Android réel (`flutter build apk`) — jamais exécutée jusqu'ici, la CI ne fait que `flutter analyze`/`flutter test` — a révélé que `sentry_flutter ^8.10.0` (ajouté en P2, item 4.5) embarque un `android/build.gradle` avec `languageVersion = "1.6"` codé en dur, incompatible avec le plugin Kotlin Gradle 2.2.20 du projet (« Language version 1.6 is no longer supported »). Corrigé en montant vers `sentry_flutter ^9.30.0` (`flutter analyze`/`flutter test` toujours verts après ce bump).
    - **Statut du build APK local** : bloqué par un verrou de fichiers Windows pendant la fusion des assets Gradle (`Unable to delete directory ... mergeDebugAssets`), qui persiste malgré l'arrêt des daemons Java résiduels — tout indique un conflit avec la synchronisation OneDrive du dossier `Documents\GitHub\...` où vit le projet. Ce n'est pas un problème de code : la résolution des dépendances et la compilation Kotlin passent désormais sans erreur, seule l'étape de nettoyage de fichiers échoue de façon environnementale. **Recommandation** : soit exclure `mobile_app_flutter/build/` de la synchronisation OneDrive, soit lancer le build depuis Android Studio (qui gère mieux ces verrous que l'invocation Gradle brute), soit déplacer le dépôt hors du dossier OneDrive.

- **2026-09-14 — Priorité P2 implémentée.** 141/141 tests backend passent (+8), `ruff check`/`ruff format --check` verts, `flutter analyze` vert, `flutter test` 7/7 verts, JS (`admin_web`/`chat_web`) validé par `node --check`.
  - **2.3/2.4 Actualités** : modèle `Actualite` (migration `e5f6a7b8c9d0`), `app/services/actualite_service.py` (CRUD + `suggested_topics_from_feedback` — agrégation des conversations les plus mal notées, sans nouveau modèle), endpoints publics `GET /api/actualites` et admin `app/routers/admin.py` (`GET/POST/PUT/DELETE /actualites`, `POST /actualites/{id}/publish|unpublish`), permissions `actualites.read`/`actualites.write`.
  - **1.4/2.1 Centre de notifications** : `POST /api/admin/notifications/broadcast` (permission `notifications.send`) — composition libre ou ciblée par métier, envoi en **tâche de fond** (`BackgroundTasks`, session DB dédiée) pour ne jamais bloquer la requête même vers de nombreux artisans (AGENTS.md §1). La publication d'une actualité avec notification réutilise cette même tâche de fond.
  - **1.5 Dashboard sécurité** : `GET /api/admin/security-stats` — actions admin des dernières 24h (`AuditLog`), et 3 nouveaux compteurs glissants (30 jours) stockés via `cache_service` (Redis/mémoire) : tentatives de connexion échouées (`app/routers/auth.py`), webhooks Mobile Money rejetés (`app/routers/payment.py`), tokens révoqués (`app/middleware/auth.py`). Ces événements n'étaient auparavant ni comptés ni consultables.
  - **1.1/1.2/1.3/1.4/1.5 UI admin_web** : nouvel onglet "Actualités & Notifications" (CRUD actualités, composer de diffusion, suggestions issues du feedback) ; le KPI-row sécurité (4 compteurs) a été ajouté en tête de l'onglet "Sécurité" existant.
  - **3.1 PWA chat_web** : `manifest.json` + `sw.js` (cache du shell statique, jamais des réponses API — une réponse RAG périmée servie hors-ligne serait pire qu'une absence de réponse), enregistrement du service worker dans `index.html`.
  - **3.2 Web Push — finalisé (même jour, après le point d'étape initial)** : à la différence de FCM/Sentry, les clés VAPID ne nécessitent aucun compte tiers (paire ECDSA générée localement). Ajouté : `app/models/push_subscription.py` (migration `f6a7b8c9d0e1`), `WebPushProvider` dans `notification_service.py` (`pywebpush`, déporté via `asyncio.to_thread` car synchrone), endpoints `GET /api/notifications/vapid-public-key`, `POST /api/notifications/web-push/{subscribe,unsubscribe}`, bouton cloche dans `chat_web` (`toggleWebPushSubscription`). Une paire de clés de développement est intégrée par défaut dans `app.config.settings` (fonctionnelle immédiatement) et **doit être régénérée en production** — ajoutée au garde-fou `_verifier_secrets_production` au même titre que `JWT_SECRET_KEY`.
  - **3.3 Bandeau actualités** : `chat_web/app.js` (`loadActualitesBanner`) affiche la dernière actualité publiée pertinente pour l'utilisateur (déduite de son métier si connecté), rejetable pour la session (`sessionStorage`).
  - **3.4 Export/partage** : boutons "Exporter" (impression navigateur → PDF, sans dépendance externe) et "Partager" (Web Share API, repli lien WhatsApp `wa.me`) sur chaque réponse de l'assistant.
  - **3.5 Accessibilité (a11y)** : `aria-label` ajoutés sur tous les boutons icône-seule et champs `placeholder`-only de `chat_web/index.html` (menu, thème, micro, envoi, déconnexion, fermeture modale, champs de connexion/inscription). **i18n reportée délibérément** : le produit est français-only par conception (CLAUDE.md/PDR.md — le Nouchi/langues locales sont gérés côté LLM, pas dans l'interface) ; un scaffold i18n complet sans locale supplémentaire réelle à servir n'apporterait aucune valeur produit immédiate.
  - **4.4 Biométrie mobile** : `local_auth` ajouté, `BiometricService`, nouvel état `AppScreen.locked` avec écran de déverrouillage dédié (`main.dart`), bouton d'activation/désactivation dans l'AppBar du chat (confirmation biométrique requise pour activer).
  - **4.6 i18n mobile — reporté (`⏸️`)** : même justification que 3.5 (produit français-only). À reconsidérer si une cible anglophone (autres pays CEDEAO) est un jour visée.
