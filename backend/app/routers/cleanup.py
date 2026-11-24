"""Aufräumbericht: vorläufige Kabel, von LLDP nicht gesehene Verbindungen, abgelaufene Reservierungen, liegengebliebene Aufträge,
geplante Geräte ohne Auftrag (siehe ``app.cleanup``)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import access, cleanup
from ..auth import Principal, current_principal, require_admin

router = APIRouter(prefix="/api/cleanup", tags=["cleanup"])


@router.get("")
def report(site_id: Optional[int] = None, days: int = Query(30, ge=1, le=3650), me: Principal = Depends(current_principal)):
    """Bericht für den eigenen Bereich; ``days``: ab wann ein vorläufiges Kabel bzw. ein offener Auftrag als „alt“ gilt."""
    if site_id:
        access.require_read(me, site_id, "Standort")
    return cleanup.report(me, site_id, days)


@router.post("/mail")
def send_now(_: Principal = Depends(require_admin)):
    """Wochenmail sofort an die globalen Administratoren senden (unabhängig vom Wochentag)."""
    n = cleanup.weekly_mail(force=True)
    if not n:
        raise HTTPException(409, "Nicht versendet – E-Mail nicht eingerichtet, keine Empfänger oder nichts zu berichten")
    return {"recipients": n}
