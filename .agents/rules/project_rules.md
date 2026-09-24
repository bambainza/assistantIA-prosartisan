# Directives de Développement & Règles du Projet ProsArtisan

Ce fichier est chargé automatiquement par Antigravity IDE pour régir le comportement et les règles d'implémentation.

---

## Directives Générales
- **Type Hints PEP 484** : Obligatoires sur l'ensemble des fonctions Python.
- **Sécurité Secrets** : Utiliser exclusivement `app.config.settings` alimenté par `.env`.
- **RAG & Multimodal** : Filtrer impérativement par `metier_id` dans Qdrant et utiliser le prompt système multilingue Nouchi.
- **Paiements** : Valider systématiquement la signature HMAC SHA-256 (`X-Signature`) sur le webhook Mobile Money.
- **Validation** : Garantir le succès à 100% de la suite de tests `pytest`.
- **Documentation synchronisée obligatoire** : À chaque nouvelle implémentation ou modification structurante, mettre à jour dans le même lot `PDR.md` pour les exigences produit, l'architecture et les API. Toute évolution de règle doit être répercutée sans contradiction dans `AGENTS.md`, `CLAUDE.md` et ce fichier `.agents/rules/project_rules.md`. Mettre aussi à jour `.env.example`, `README.md` et les manifests de déploiement lorsqu'ils sont concernés. Une livraison est incomplète tant que ces documents ne reflètent pas le code ; si aucune mise à jour n'est nécessaire, l'indiquer explicitement dans le compte rendu.
