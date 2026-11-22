"""Portwerk – FastAPI-Anwendung."""
from __future__ import annotations

import logging

import anyio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import acme_client, auth, backup
from .config import settings
from .routers import accounts, backups, catalog, compare, documents, history, imports, labels, portreservations, masterdata, notify, openplan, overview, patchlists, search, serverconfig, wan, wizards, workorders
from .static import find_static_dir, register_static

logger = logging.getLogger("opp")

app = FastAPI(
    title="Portwerk API",
    version="0.1.0",
    description="Verwaltung und Planung von Verkabelung/Patchungen – Stammdaten, Import, Aufträge.",
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)

if settings.cors_origins.strip():
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
                       allow_methods=["*"], allow_headers=["*"])

app.include_router(accounts.router)
app.include_router(masterdata.router)
app.include_router(catalog.router)
app.include_router(wizards.router)
app.include_router(serverconfig.router)
app.include_router(imports.router)
app.include_router(overview.router)
app.include_router(workorders.router)
app.include_router(patchlists.router)
app.include_router(notify.router)
app.include_router(openplan.router)
app.include_router(wan.router)
app.include_router(compare.router)
app.include_router(search.router)
app.include_router(history.router)
app.include_router(backups.router)
app.include_router(labels.router)
app.include_router(documents.router)
app.include_router(portreservations.router)


@app.on_event("startup")
async def startup() -> None:
    generated = auth.init()
    if generated:
        logger.warning("Start-Admin '%s' angelegt mit generiertem Passwort: %s (bitte nach der Anmeldung ändern)",
                       settings.admin_username, generated)
    # Sync-Routen laufen in einem Thread-Pool; die Obergrenze verhindert, dass viele parallele Anfragen eine kleine VM überlasten.
    backup.start_background()                # tägliche automatische Sicherung (Einstellung in der Verwaltung)
    acme_client.start_background()           # prüft regelmäßig, ob das Server-Zertifikat erneuert werden muss
    anyio.to_thread.current_default_thread_limiter().total_tokens = 8


@app.get("/.well-known/acme-challenge/{token}", include_in_schema=False)
def acme_challenge(token: str):
    """HTTP-01-Validierung der CA (öffentlich, nur aktive Tokens)."""
    from fastapi import HTTPException
    from fastapi.responses import PlainTextResponse
    ka = acme_client.CHALLENGES.get(token)
    if not ka:
        raise HTTPException(404)
    return PlainTextResponse(ka)


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "version": app.version}


# Muss zuletzt stehen: liefert die Oberfläche (falls gebaut) für alle Pfade außerhalb der API
register_static(app, find_static_dir(settings.static_dir))
