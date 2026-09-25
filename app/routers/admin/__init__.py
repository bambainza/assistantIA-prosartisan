"""
Router Admin : Back-office d'administration (`/api/admin`).

Découpé par domaine ; chaque sous-module déclare ses routes sur son propre
`APIRouter`, regroupés ici sous le préfixe commun. L'ordre d'inclusion est
celui de l'ancien module unique (l'ordre d'enregistrement des routes compte).
"""

from fastapi import APIRouter

from app.routers.admin import (
    communication,
    contenus,
    offres,
    securite,
    supervision,
    utilisateurs,
)

router = APIRouter(prefix="/api/admin", tags=["Back-Office Admin"])
for _module in (contenus, utilisateurs, offres, securite, communication, supervision):
    router.include_router(_module.router)
