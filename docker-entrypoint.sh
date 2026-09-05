#!/bin/sh
set -e

echo "🚀 [ProsArtisan] Démarrage du conteneur en environnement : ${APP_ENV:-production}"

# Exécution des migrations Alembic si activé (par défaut true)
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "📦 [ProsArtisan] Exécution des migrations Alembic..."
  alembic upgrade head || {
    echo "⚠️ [ProsArtisan] Échec de la migration Alembic, tentative de continuation..."
  }
fi

# Exécution de la commande principale passée en argument
exec "$@"
