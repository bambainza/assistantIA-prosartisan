# Directives de Développement & Règles du Projet ProsArtisan

Ce fichier est chargé automatiquement par Antigravity IDE pour régir le comportement et les règles d'implémentation.

---

## Directives Générales
- **Type Hints PEP 484** : Obligatoires sur l'ensemble des fonctions Python.
- **Sécurité Secrets** : Utiliser exclusivement `app.config.settings` alimenté par `.env`.
- **RAG & Multimodal** : Filtrer impérativement par `metier_id` dans Qdrant et utiliser le prompt système multilingue Nouchi. Fiches à enjeu santé/sécurité : `ingestion/documents_a_valider/` (non indexé) jusqu'à relecture professionnelle.
- **Paiements** : parcours officiels Wave Checkout / Orange Money WebPay / CinetPay v1 via `app/services/payment_providers/` (simulateur `PAYMENT_MODE=demo` fidèle, désactivé en production par défaut) ; notifications authentifiées (`Wave-Signature` anti-rejeu, `notif_token` + confirmation `transactionstatus`, `notify_token` + confirmation `GET /v1/payment/{merchant_transaction_id}`, `X-Signature` pour le webhook générique), crédit unique et seulement si le montant confirmé est exact.
- **Historique** : aucune discussion anonyme côté serveur ; `/api/conversations` exige le JWT ; toute `conversation_id` est vérifiée avant quota et avant écriture.
- **Tokens** : seuls les JWT `type=access` ouvrent les routes protégées ; un refresh token ne sert qu'à `/api/auth/refresh` et `/api/auth/logout`.
- **Web/XSS/CSRF** : le navigateur utilise les cookies JWT `HttpOnly` via `/api/auth/web/*`, jamais `localStorage`; toute mutation cookie exige le double-submit CSRF. Tout Markdown LLM est assaini avant `innerHTML` et la CSP du chat interdit `script-src-attr`.
- **Photos & coûts IA** : photos validées avant quota puis stockées hors base (`media_service`, référence `media:<nom>`, URL signée) ; contrôles gratuits avant tout appel facturé (STT, vision), WebSocket compris ; noms de fichiers clients toujours assainis.
- **RAG & Bascule Multi-Fournisseurs (Mistral / Gemini)** : parité complète entre réponse et streaming (`RAGService._prepare`) et routage haute disponibilité via `llm_provider_service` entre Mistral AI et Google Gemini (`gemini-3.8-flash` sur `/v1beta/interactions`), avec coupe-circuit et failover automatique ; invalider le cache d'activation après toute (dés)activation de métier ou de document. Une panne de recherche (embedding, Qdrant) lève `RechercheIndisponibleError` (`503`, question rendue) : le repli zéro hallucination n'est servi et mis en cache qu'après une recherche aboutie sans résultat.
- **Suppressions tierces** : une suppression Qdrant attend un statut confirmé avant audit de succès, commit et invalidation du cache ; panne → `503`, jamais d'exception absorbée ni de faux succès ; opération idempotente par filtre.
- **Quotas & IP** : quota gratuit journalier en Redis (`INCR` atomique, par utilisateur ou par IP anonyme), crédits achetés décrémentés en SQL atomique ; question rendue (`restituer_quota`) si la réponse IA échoue ; `metier_id` lus via `GET /api/metiers`, jamais codés en dur ; IP cliente toujours via `get_client_ip` (`TRUSTED_PROXY_HOPS`).
- **Modèles ORM** : toute évolution s'accompagne d'une migration Alembic, et tout nouveau modèle est importé dans `app/models/__init__.py` (requis par les scripts `app/scripts/`, qui ne chargent pas `app.main`) ; horodatages stockés en UTC naïf (`UTCNaiveDateTime`, jamais d'écriture avec fuseau dans une colonne `DateTime` explicite).
- **Validation** : Garantir le succès à 100% de la suite de tests `pytest`.
- **Documentation contrôlée avant chaque commit et push** : Pour toute implémentation ou modification, même mineure, relire et mettre à jour systématiquement `PDR.md`, `AGENTS.md`, `CLAUDE.md` et ce fichier avant chaque `git commit`, puis vérifier à nouveau leur cohérence avant chaque `git push`. Mettre aussi à jour `.env.example`, `README.md` et les manifests de déploiement lorsqu'ils sont concernés. Il est interdit de committer ou pousser avant la fin de ce contrôle. Si aucune modification documentaire supplémentaire n'est nécessaire, confirmer explicitement dans le compte rendu que la relecture a été effectuée et que les fichiers restent à jour.

## Fiabilité des sessions et des dépendances (2026-11-14)

- Le TOTP des administrateurs s'applique aux connexions locales et Google, avant toute émission de jeton et avant toute liaison de compte Google. Les clients transmettent `totp_code` lorsqu'il est activé.
- La rotation d'un refresh token exige un `jti` et une consommation atomique Redis (`SET NX EX`). Deux appels concurrents ne doivent jamais réussir ensemble ; une panne du backend partagé produit `503`.
- En production, une panne du compteur de débit bloque les routes sensibles avec `503`. Le WebSocket envoie une erreur explicite et reste disponible pour les messages suivants.
- Les budgets audio sont indépendants des crédits de questions : `AUDIO_STT_REQUESTS_PER_DAY` (20 transcriptions par défaut) et `AUDIO_TTS_CHARS_PER_DAY` (20 000 caractères par défaut), par identité et jour UTC. La réservation atomique précède chaque appel facturé HTTP/WebSocket ; un échec restitue la réservation sur sa clé d'origine. Les Pass ne contournent pas ces budgets de coûts.
- Une panne de lecture des activations métier/document est une indisponibilité explicite ; elle ne doit ni produire un ensemble vide ni permettre de servir une réponse RAG en cache.
- `/health` et `/api/health` sont des sondes de vie. `/api/ready` vérifie SQL, Redis et la collection Qdrant et répond `503` en cas d'échec, sans détail interne. Docker et les contrôles de livraison utilisent la disponibilité ; la sonde de vie Cloud Run reste indépendante.
- La publication et le déploiement dépendent de la CI complète du même commit. Le webhook reçoit l'image par digest et la révision ; le contrôle final exige cette révision via `/api/ready` (`BUILD_SHA` intégré à l'image).

- Les scripts shell exécutés dans les conteneurs Linux utilisent LF (`*.sh text eol=lf` dans `.gitattributes`) ; le build normalise également le script de démarrage avant exécution.
