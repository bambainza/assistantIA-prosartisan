# Directives de Développement & Règles du Projet ProsArtisan

Ce fichier est chargé automatiquement par Antigravity IDE pour régir le comportement et les règles d'implémentation.

---

## Directives Générales
- **Type Hints PEP 484** : Obligatoires sur l'ensemble des fonctions Python.
- **Sécurité Secrets** : Utiliser exclusivement `app.config.settings` alimenté par `.env`.
- **RAG & Multimodal** : Filtrer impérativement par `metier_id` dans Qdrant et utiliser le prompt système multilingue Nouchi.
- **Paiements** : parcours officiels Wave Checkout / Orange Money WebPay via `app/services/payment_providers/` (simulateur `PAYMENT_MODE=demo` fidèle, désactivé en production par défaut) ; notifications authentifiées (`Wave-Signature` anti-rejeu, `notif_token` + confirmation `transactionstatus`, `X-Signature` pour le webhook générique), crédit unique et seulement si le montant confirmé est exact.
- **Historique** : aucune discussion anonyme côté serveur ; `/api/conversations` exige le JWT ; toute `conversation_id` est vérifiée avant quota et avant écriture.
- **Tokens** : seuls les JWT `type=access` ouvrent les routes protégées ; un refresh token ne sert qu'à `/api/auth/refresh` et `/api/auth/logout`.
- **Photos & coûts IA** : photos validées avant quota puis stockées hors base (`media_service`, référence `media:<nom>`, URL signée) ; contrôles gratuits avant tout appel facturé (STT, vision), WebSocket compris ; noms de fichiers clients toujours assainis.
- **RAG** : parité complète entre réponse et streaming (`RAGService._prepare`) ; invalider le cache d'activation après toute (dés)activation de métier ou de document.
- **Quotas & IP** : quota gratuit journalier en Redis (`INCR` atomique, par utilisateur ou par IP anonyme), crédits achetés décrémentés en SQL atomique ; IP cliente toujours via `get_client_ip` (`TRUSTED_PROXY_HOPS`).
- **Validation** : Garantir le succès à 100% de la suite de tests `pytest`.
- **Documentation contrôlée avant chaque commit et push** : Pour toute implémentation ou modification, même mineure, relire et mettre à jour systématiquement `PDR.md`, `AGENTS.md`, `CLAUDE.md` et ce fichier avant chaque `git commit`, puis vérifier à nouveau leur cohérence avant chaque `git push`. Mettre aussi à jour `.env.example`, `README.md` et les manifests de déploiement lorsqu'ils sont concernés. Il est interdit de committer ou pousser avant la fin de ce contrôle. Si aucune modification documentaire supplémentaire n'est nécessaire, confirmer explicitement dans le compte rendu que la relecture a été effectuée et que les fichiers restent à jour.
