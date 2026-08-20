import logging
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("app.request")
logger.setLevel(logging.INFO)

# Setup basic console logging configuration if not already configured
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [RID:%(request_id)s] %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)


class LoggingAndRequestIdMiddleware(BaseHTTPMiddleware):
    """Middleware pour ajouter X-Request-ID et enregistrer des logs structurés."""

    async def dispatch(self, request: Request, call_next):
        # 1. Extraction ou génération du Request ID
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())

        # Enregistrer l'ID dans le scope de la requête pour y accéder ailleurs
        request.state.request_id = request_id

        # 2. Logs de début de requête
        start_time = time.time()
        logger.info(
            f"Requête entrante : {request.method} {request.url.path}",
            extra={"request_id": request_id},
        )

        # 3. Exécution de la requête
        response = await call_next(request)

        # 4. Logs de fin de requête
        duration = time.time() - start_time
        logger.info(
            f"Réponse sortante : {request.method} {request.url.path} - Statut {response.status_code} en {duration:.4f}s",
            extra={"request_id": request_id},
        )

        # 5. Attacher le Request ID à l'en-tête de réponse
        response.headers["X-Request-ID"] = request_id

        return response
