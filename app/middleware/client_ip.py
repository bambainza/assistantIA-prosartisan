"""Résolution de l'adresse IP réelle du client derrière un reverse proxy.

Utilisée par le rate limiter et par le quota des visiteurs non connectés :
derrière Caddy / Render / Cloud Run, `request.client.host` est l'IP du proxy,
commune à tous les utilisateurs.
"""

from __future__ import annotations

from starlette.requests import HTTPConnection

from app.config import settings


def get_client_ip(connection: HTTPConnection) -> str:
    """Retourne l'IP du client (requête HTTP ou WebSocket).

    Avec `TRUSTED_PROXY_HOPS=N`, on lit la N-ième entrée en partant de la
    droite de `X-Forwarded-For` : chaque proxy de confiance ajoute l'IP de
    son pair à droite, donc tout ce qui est plus à gauche a pu être injecté
    par le client. Si l'en-tête est absent ou trop court, on retombe sur
    l'IP TCP plutôt que de faire confiance à une valeur non vérifiable.
    """
    direct_ip = connection.client.host if connection.client else "unknown"
    hops = settings.trusted_proxy_hops
    if hops <= 0:
        return direct_ip

    header = connection.headers.get("x-forwarded-for", "")
    hosts = [h.strip() for h in header.split(",") if h.strip()]
    if len(hosts) < hops:
        return direct_ip
    return hosts[-hops]
