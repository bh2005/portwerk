"""Änderungs-Revision für die Oberfläche („Andere haben etwas geändert – neu laden“). Logik in ``livechange.py``."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from .. import livechange
from ..auth import Principal, require_user

router = APIRouter(prefix="/api", tags=["übersicht"])


@router.get("/live")
def live(me: Principal = Depends(require_user)):
    """Kleine Abfrage (nur angemeldete Benutzer): ``others`` = Revision der letzten Änderung durch jemand anderen, ``by``/``at`` = wer und wann."""
    return livechange.status(livechange.actor_key("user", me.user_id))
