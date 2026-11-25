"""Änderungs-Revision: Portwerk merkt sich, wann zuletzt jemand Daten geändert hat und wer.

Jede erfolgreiche schreibende Anfrage (POST/PUT/PATCH/DELETE auf ``/api``-Routen) erhöht eine Revisionsnummer und merkt sich, **wer** sie
ausgelöst hat (angemeldeter Benutzer oder API-Zugang). Die Oberfläche fragt ``GET /api/live`` ab (kleine Antwort, nur wenn der Tab sichtbar ist)
und erfährt so, ob **andere** seit dem letzten Laden etwas geändert haben – dann erscheint „Neu laden“ statt stiller Überschreibung.
Die Revision liegt im Speicher (ein Prozess); sie startet mit der Uhrzeit, damit sie nach einem Neustart nie zurückspringt.
Ausgenommen sind Anmeldung und Konto-Einstellungen (``/auth``) und die Abfrage selbst.
"""
from __future__ import annotations

import threading
import time
from typing import Dict, Optional, Tuple

_lock = threading.Lock()
_rev = int(time.time() * 1000)                      # monoton, auch über Neustarts hinweg
_last: Dict[str, Tuple[int, str, float]] = {}       # Akteur-Schlüssel -> (letzte Revision, Anzeigename, Zeitpunkt)
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}
IGNORE_PREFIXES = ("/auth", "/api/live")


def actor_key(kind: str, ident) -> str:
    return f"{kind}:{ident}"


def counts(method: str, path: str, status: int) -> bool:
    """Zählt diese Anfrage als Datenänderung?"""
    return method in MUTATING and status < 400 and path.startswith("/api") and not path.startswith(IGNORE_PREFIXES)


def bump(key: str, name: str) -> int:
    global _rev
    with _lock:
        _rev += 1
        _last[key] = (_rev, name, time.time())
        return _rev


def status(key: Optional[str]) -> dict:
    """``rev``: aktuelle Revision; ``others``: Revision der letzten Änderung durch jemand anderen als ``key`` (0 = keine);
    ``by``/``at``: wer und wann."""
    with _lock:
        others = [v for k, v in _last.items() if k != key]
        o = max(others, default=None)
        return {"rev": _rev, "others": o[0] if o else 0, "by": o[1] if o else "", "at": o[2] if o else None}
