#!/bin/sh
set -e

echo "🚀 [ProsArtisan] Démarrage du conteneur en environnement : ${APP_ENV:-production}"

# Exécution des migrations Alembic si activé (par défaut true)
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "📦 [ProsArtisan] Exécution des migrations Alembic..."
  # Échec de migration = arrêt : démarrer sur un schéma en retard produirait des
  # erreurs 500 (colonnes manquantes) au lieu d'un échec de déploiement visible.
  if ! alembic upgrade head; then
    echo "❌ [ProsArtisan] Échec de la migration Alembic : démarrage interrompu." >&2
    exit 1
  fi
fi

# Exécution de la commande principale passée en argument
exec "$@"
