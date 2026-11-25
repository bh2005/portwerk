"""Portwerk – FastAPI-Anwendung."""
from __future__ import annotations

import logging
import os

import anyio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from . import acme_client, auth, backup, livechange, notifications, releases
from .config import settings
from .routers import live as live_router, accounts, backups, catalog, cleanup as cleanup_router, compare, documents, history, imports, labels, portreservations, routing as routing_router, stations, vlans, masterdata, notify, openplan, overview, patchlists, releases as releases_router, search, serverconfig, wan, wizards, workorders
from .static import find_static_dir, register_static

logger = logging.getLogger("opp")

app = FastAPI(
    title="Portwerk API",
    version=releases.current_version("0.1.0"),
    description="Verwaltung und Planung von Verkabelung/Patchungen – Stammdaten, Import, Aufträge.",
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)

if settings.cors_origins.strip():
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
                       allow_methods=["*"], allow_headers=["*"])

# HTTP -> HTTPS: nur wenn FORCE_HTTPS=1 UND der HTTPS-Listener tatsächlich läuft (Marker DATA_DIR/tls/serving). So sperrt man sich nie aus,
# solange noch kein Zertifikat existiert. Ausgenommen: ACME-HTTP-01 und der Health-Check (Docker/Monitoring).
# Nur verwenden, wenn Portwerk selbst TLS terminiert (nicht hinter einem Reverse-Proxy, der TLS abschließt – sonst Weiterleitungsschleife).
FORCE_HTTPS = os.environ.get("FORCE_HTTPS", "").lower() in ("1", "true", "yes")
PUBLIC_HTTPS_PORT = os.environ.get("PUBLIC_HTTPS_PORT", "443")
HTTP_EXEMPT = ("/.well-known/acme-challenge/", "/health")


def _host(h: str) -> str:
    """Host-Header ohne Port (IPv6-Literale bleiben in Klammern)."""
    if h.startswith("["):
        return h.split("]")[0] + "]"
    return h.rsplit(":", 1)[0] if ":" in h else h


@app.middleware("http")
async def https_redirect(request, call_next):
    if (FORCE_HTTPS and request.url.scheme == "http" and not request.url.path.startswith(HTTP_EXEMPT)
            and acme_client.TLS_DIR.joinpath("serving").exists()):
        host = _host(request.headers.get("host") or "")
        if host:
            port = "" if PUBLIC_HTTPS_PORT == "443" else ":" + PUBLIC_HTTPS_PORT
            query = "?" + request.url.query if request.url.query else ""
            return RedirectResponse("https://%s%s%s%s" % (host, port, request.url.path, query), status_code=308)
    return await call_next(request)


@app.middleware("http")
async def track_changes(request, call_next):
    """Erfolgreiche schreibende API-Aufrufe erhöhen die Änderungs-Revision (wer, wann) – Grundlage für „Neu laden“ in der Oberfläche."""
    response = await call_next(request)
    actor = getattr(request.state, "actor", None)
    if actor and livechange.counts(request.method, request.url.path, response.status_code):
        livechange.bump(*actor)
    return response


app.include_router(accounts.router)
app.include_router(live_router.router)
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
app.include_router(stations.router)
app.include_router(routing_router.router)
app.include_router(releases_router.router)
app.include_router(search.router)
app.include_router(history.router)
app.include_router(backups.router)
app.include_router(labels.router)
app.include_router(documents.router)
app.include_router(portreservations.router)
app.include_router(cleanup_router.router)
app.include_router(vlans.router)


@app.on_event("startup")
async def startup() -> None:
    generated = auth.init()
    if generated:
        logger.warning("Start-Admin '%s' angelegt mit generiertem Passwort: %s (bitte nach der Anmeldung ändern)",
                       settings.admin_username, generated)
    # Sync-Routen laufen in einem Thread-Pool; die Obergrenze verhindert, dass viele parallele Anfragen eine kleine VM überlasten.
    notifications.start_background()          # tägliche Erinnerungen (Reservierungen laufen ab)
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
