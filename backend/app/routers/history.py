"""Verbindungs-Historie: Was steckte wann wo? (Tabelle ``cable_history``, gepflegt durch Trigger und ``app/cablelog.py``)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import access, db, timetravel
from ..auth import Principal, current_principal

router = APIRouter(prefix="/api/cable-history", tags=["historie"])


def _parse_at(at: Optional[str]) -> Optional[float]:
    """``YYYY-MM-DD`` (Ende des Tages) oder ``YYYY-MM-DDTHH:MM[:SS]`` – mit Zeitzone (``+01:00``, ``Z``) genau,
    ohne in Ortszeit des Servers (im Container meist UTC; die Oberfläche schickt deshalb immer die Zeitzone mit)."""
    if not at:
        return None
    try:
        if len(at) == 10:
            return datetime.fromisoformat(at + "T23:59:59").timestamp()
        return datetime.fromisoformat(at).timestamp()
    except ValueError:
        raise HTTPException(400, "Zeitpunkt ungültig (erwartet JJJJ-MM-TT oder JJJJ-MM-TTThh:mm)")


def _out(r: dict, local_ports: Optional[set]) -> dict:
    a = {"port_id": r["port_a_id"], "port_name": r["port_a_name"], "hostname": r["host_a"], "device_id": r["dev_a"]}
    b = {"port_id": r["port_b_id"], "port_name": r["port_b_name"], "hostname": r["host_b"], "device_id": r["dev_b"]}
    if local_ports is not None and r["port_a_id"] not in local_ports and r["port_b_id"] in local_ports:
        a, b = b, a                                                       # „local“ ist immer die Seite des abgefragten Ports/Geräts
    return {
        "id": r["id"], "cable_id": r["cable_id"], "active": r["valid_to"] is None,
        "valid_from": r["valid_from"], "valid_to": r["valid_to"],
        "local": a, "remote": b,
        "cable_label": r["cable_label"], "cable_type": r["cable_type"], "length_m": r["length_m"], "color": r["color"], "note": r["note"],
        "created_by": r["created_by"],
        "workorder": {"id": r["workorder_id"], "number": r["wo_number"]} if r["workorder_id"] else None,
        "ended_by": r["ended_by"], "end_reason": r["end_reason"],
        "ended_workorder": {"id": r["ended_workorder_id"], "number": r["ended_wo_number"]} if r["ended_workorder_id"] else None,
    }


def _scope(me: Principal, site_id: Optional[int], location_id: Optional[int], device_id: Optional[int]) -> Optional[set]:
    if device_id is not None:
        if not db.row("SELECT id FROM devices WHERE id = ?", (device_id,)):
            raise HTTPException(404, "Gerät nicht gefunden")
        access.require_read(me, access.site_of_device(device_id), "Gerät")
    elif location_id is not None:
        if not db.row("SELECT id FROM locations WHERE id = ?", (location_id,)):
            raise HTTPException(404, "Location nicht gefunden")
        access.require_read(me, access.site_of_location(location_id), "Location")
    elif site_id is not None:
        access.require_read(me, site_id, "Standort")
    return timetravel.scope_devices(site_id, location_id, device_id)


@router.get("/snapshot")
def snapshot(at: str, site_id: Optional[int] = None, location_id: Optional[int] = None, device_id: Optional[int] = None,
             me: Principal = Depends(current_principal)):
    """Zeitreise: alle Verbindungen, die zum Zeitpunkt ``at`` steckten (optional nur Standort/Location/Gerät)."""
    t = _parse_at(at)
    rows = timetravel.active_at(t, me, _scope(me, site_id, location_id, device_id))
    return {"at": t, "connections": [timetravel.conn(r) for r in rows]}


@router.get("/diff")
def diff(from_: str = Query(..., alias="from"), to: Optional[str] = None, site_id: Optional[int] = None, location_id: Optional[int] = None,
         device_id: Optional[int] = None, me: Principal = Depends(current_principal)):
    """Zeitreise: Vergleich zweier Zeitpunkte (``to`` leer = jetzt) – neu, entfernt, umgesteckt, nur zwischenzeitlich gesteckt."""
    import time
    t1, t2 = _parse_at(from_), (_parse_at(to) if to else time.time())
    return timetravel.diff(t1, t2, me, _scope(me, site_id, location_id, device_id))


@router.get("")
def cable_history(
    port_id: Optional[int] = None,
    device_id: Optional[int] = None,
    at: Optional[str] = Query(None, description="Nur Verbindungen, die zu diesem Zeitpunkt steckten (JJJJ-MM-TT oder JJJJ-MM-TTThh:mm)"),
    limit: int = Query(200, ge=1, le=2000),
    me: Principal = Depends(current_principal),
):
    """Verbindungen eines Ports oder Geräts mit Zeitraum (neueste zuerst). Ohne Port/Gerät: alle Änderungen (nur mit globaler Berechtigung)."""
    where, args = [], []
    local: Optional[set] = None
    if port_id is not None:
        if not db.row("SELECT id FROM ports WHERE id = ?", (port_id,)):
            raise HTTPException(404, "Port nicht gefunden")
        access.require_read(me, access.site_of_port(port_id), "Port")
        where.append("(h.port_a_id = ? OR h.port_b_id = ?)"); args += [port_id, port_id]
        local = {port_id}
    elif device_id is not None:
        if not db.row("SELECT id FROM devices WHERE id = ?", (device_id,)):
            raise HTTPException(404, "Gerät nicht gefunden")
        access.require_read(me, access.site_of_device(device_id), "Gerät")
        local = {r["id"] for r in db.rows("SELECT id FROM ports WHERE device_id = ?", (device_id,))}
        sub = "SELECT id FROM ports WHERE device_id = ?"
        where.append(f"(h.port_a_id IN ({sub}) OR h.port_b_id IN ({sub}))"); args += [device_id, device_id]
    elif not me.is_global:
        raise HTTPException(403, "Ohne Port oder Gerät nur mit globaler Berechtigung")
    t = _parse_at(at)
    if t is not None:
        where.append("h.valid_from <= ? AND (h.valid_to IS NULL OR h.valid_to > ?)"); args += [t, t]
    w = ("WHERE " + " AND ".join(where)) if where else ""
    rows = db.rows(
        f"""SELECT h.*, pa.device_id AS dev_a, pb.device_id AS dev_b, wo.number AS wo_number, we.number AS ended_wo_number
            FROM cable_history h
            LEFT JOIN ports pa ON pa.id = h.port_a_id
            LEFT JOIN ports pb ON pb.id = h.port_b_id
            LEFT JOIN workorders wo ON wo.id = h.workorder_id
            LEFT JOIN workorders we ON we.id = h.ended_workorder_id
            {w}
            ORDER BY COALESCE(h.valid_to, 9e18) DESC, h.valid_from DESC, h.id DESC
            LIMIT ?""",
        (*args, limit),
    )
    return [_out(r, local) for r in rows]
