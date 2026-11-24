"""Zwischenstationen (Patchfeld, Dose) in eine Strecke einfügen oder daraus entfernen.

Eine Strecke besteht aus Kabeln, die über Stationen (vorn ↔ hinten, ``ports.peer_port_id``) verbunden sind. Beide Operationen ersetzen
Kabel in **einer** Transaktion und halten die Verbindungs-Historie vollständig (alte Kabel werden mit Vermerk beendet, neue angelegt):

* ``insert-station``: Kabel X–Y wird zu X–Station(vorn) und Station(hinten)–Y.
* ``remove``: Kabel X–Station(vorn) und Station(hinten)–Y werden zum Direktkabel X–Y (als vorläufig markiert).
"""
from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import access, audit, cablelog, db, reservations
from ..access import require_writer
from ..auth import Principal
from ..compare import THROUGH_TYPES

router = APIRouter(tags=["strecken"])


class InsertStationIn(BaseModel):
    port_id: int                                    # Port der Station, der zum Kabelende ``side_port_id`` zeigt (die Gegenseite ergibt sich aus der Durchschleifung)
    side_port_id: Optional[int] = None              # Kabelende, das mit ``port_id`` verbunden wird (Standard: Port A des Kabels)


class RemoveStationIn(BaseModel):
    port_id: int                                    # einer der beiden Ports der Station


def _station(port_id: int) -> tuple[dict, dict]:
    """(Port, Gegenseite) einer durchgeschleiften Station; 400 sonst."""
    p = db.row("""SELECT p.id, p.name, p.peer_port_id, d.type, d.hostname FROM ports p JOIN devices d ON d.id = p.device_id WHERE p.id = ?""", (port_id,))
    if not p:
        raise HTTPException(404, "Port nicht gefunden")
    if p["type"] not in THROUGH_TYPES:
        raise HTTPException(400, f"{p['hostname']} ist kein Patchfeld und keine Dose")
    if not p["peer_port_id"]:
        raise HTTPException(400, f"{p['hostname']}:{p['name']} hat keine dokumentierte Gegenseite (vorn ↔ hinten)")
    q = db.row("SELECT id, name FROM ports WHERE id = ?", (p["peer_port_id"],))
    return p, q


def _cable_at(port_id: int) -> Optional[dict]:
    return db.row("SELECT * FROM cables WHERE port_a_id = ? OR port_b_id = ?", (port_id, port_id))


def _insert(t, a: int, b: int, src: dict, me: Principal, full: bool, provisional: int, note: str = "") -> int:
    lo, hi = (a, b) if a < b else (b, a)
    cur = t.execute(
        """INSERT INTO cables(port_a_id, port_b_id, cable_label, cable_type, fiber_count, length_m, color, installed_at, note, created_by, created_at, provisional)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (lo, hi, src["cable_label"] if full else "", src["cable_type"], src["fiber_count"], src["length_m"] if full else None, src["color"],
         src["installed_at"] if full else None, note, me.name, time.time(), provisional))
    return cur.lastrowid


@router.post("/api/cables/{cid}/insert-station", status_code=201)
def insert_station(cid: int, body: InsertStationIn, me: Principal = Depends(require_writer)):
    """Patchfeld oder Dose in ein Kabel einfügen. Das erste Teilkabel behält Nummer, Länge und Einbaudatum des alten Kabels;
    Kabelart, Farbe und das Kennzeichen „vorläufig“ gelten für beide. Das Messprotokoll gehört zum alten Kabel und wird nicht übernommen."""
    c = db.row("SELECT * FROM cables WHERE id = ?", (cid,))
    if not c:
        raise HTTPException(404, "Kabel nicht gefunden")
    x = body.side_port_id or c["port_a_id"]
    if x not in (c["port_a_id"], c["port_b_id"]):
        raise HTTPException(400, "side_port_id gehört nicht zu diesem Kabel")
    y = c["port_b_id"] if x == c["port_a_id"] else c["port_a_id"]
    s, s2 = _station(body.port_id)
    if {s["id"], s2["id"]} & {x, y}:
        raise HTTPException(400, "Die Station darf nicht an dem Kabel selbst hängen")
    for pid in (x, y, s["id"]):
        access.require_write(me, access.site_of_port(pid))
    if _cable_at(s["id"]) or _cable_at(s2["id"]):
        raise HTTPException(409, "Ein Port der Station ist bereits verbunden")
    reservations.check([s["id"], s2["id"]], use_reserved=False, by=me.name)
    with db.transaction() as t:                                                       # ab hier nur noch schreiben (alles oder nichts)
        cablelog.remove_cable(cid, by=me.name, reason="manual", c=t)
        first = _insert(t, x, s["id"], c, me, True, c["provisional"])
        second = _insert(t, s2["id"], y, c, me, False, c["provisional"])
    audit.log(me.name, "cable.insert_station", "cable", cid, f"{s['name']} ↔ {s2['name']}")
    return {"cable_ids": [first, second], "station_port_id": s["id"], "station_peer_port_id": s2["id"]}


@router.post("/api/stations/remove", status_code=201)
def remove_station(body: RemoveStationIn, me: Principal = Depends(require_writer)):
    """Zwischenstation aus der Strecke nehmen: die beiden Kabel werden zu einem Direktkabel (vorläufig, Daten des ersten Kabels)."""
    s, s2 = _station(body.port_id)
    c1, c2 = _cable_at(s["id"]), _cable_at(s2["id"])
    if not (c1 and c2):
        raise HTTPException(409, "Die Station ist nur auf einer Seite verbunden – dann das Kabel lösen statt die Station zu entfernen")
    x = c1["port_b_id"] if c1["port_a_id"] == s["id"] else c1["port_a_id"]
    y = c2["port_b_id"] if c2["port_a_id"] == s2["id"] else c2["port_a_id"]
    if x == y or {x, y} & {s["id"], s2["id"]}:
        raise HTTPException(409, "Die Strecke ist in sich geschlossen")
    for pid in (x, y, s["id"]):
        access.require_write(me, access.site_of_port(pid))
    with db.transaction() as t:
        cablelog.remove_cable(c1["id"], by=me.name, reason="manual", c=t)
        cablelog.remove_cable(c2["id"], by=me.name, reason="manual", c=t)
        new = _insert(t, x, y, c1, me, True, 1, "Zwischenstation entfernt – Strecke nicht vollständig dokumentiert")
    audit.log(me.name, "cable.remove_station", "port", s["id"], f"{s['name']} ↔ {s2['name']}")
    return {"cable_id": new, "port_a_id": min(x, y), "port_b_id": max(x, y)}
