# Directives de Développement & Règles du Projet ProsArtisan

Ce fichier est chargé automatiquement par Antigravity IDE pour régir le comportement et les règles d'implémentation.

---

## Directives Générales
- **Type Hints PEP 484** : Obligatoires sur l'ensemble des fonctions Python.
- **Sécurité Secrets** : Utiliser exclusivement `app.config.settings` alimenté par `.env`.
- **RAG & Multimodal** : Filtrer impérativement par `metier_id` dans Qdrant et utiliser le prompt système multilingue Nouchi.
- **Paiements** : Valider systématiquement la signature HMAC SHA-256 (`X-Signature`) sur le webhook Mobile Money.
- **Validation** : Garantir le succès à 100% de la suite de tests `pytest`.
- **Documentation contrôlée avant chaque commit et push** : Pour toute implémentation ou modification, même mineure, relire et mettre à jour systématiquement `PDR.md`, `AGENTS.md`, `CLAUDE.md` et ce fichier avant chaque `git commit`, puis vérifier à nouveau leur cohérence avant chaque `git push`. Mettre aussi à jour `.env.example`, `README.md` et les manifests de déploiement lorsqu'ils sont concernés. Il est interdit de committer ou pousser avant la fin de ce contrôle. Si aucune modification documentaire supplémentaire n'est nécessaire, confirmer explicitement dans le compte rendu que la relecture a été effectuée et que les fichiers restent à jour.
