"""Liefert die gebaute Oberfläche (frontend/dist) aus – ein Container genügt.

Alle Pfade, die nicht zur API gehören, liefern ``index.html`` (Vue-Router im History-Modus).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

API_PREFIXES = ("api/", "auth/", "health")
NO_CACHE = {"Cache-Control": "no-cache"}      # index.html immer neu prüfen (ETag), sonst zeigt der Browser nach einem Update die alte Oberfläche


def find_static_dir(configured: str = "") -> Optional[Path]:
    root = Path(__file__).resolve().parent.parent.parent
    for cand in (configured, str(root / "frontend" / "dist"), "/app/static"):
        if cand and (Path(cand) / "index.html").is_file():
            return Path(cand)
    return None


def register_static(app: FastAPI, directory: Optional[Path]) -> bool:
    """Muss nach allen API-Routern aufgerufen werden (der Catch-All fängt alles Übrige)."""
    if not directory:
        return False
    dist = directory.resolve()
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith(API_PREFIXES):
            return JSONResponse({"detail": "Nicht gefunden"}, status_code=404)
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and dist in candidate.parents:      # nur Dateien innerhalb von dist
            return FileResponse(candidate, headers=NO_CACHE if candidate.name == "index.html" else None)
        return FileResponse(dist / "index.html", headers=NO_CACHE)

    return True
