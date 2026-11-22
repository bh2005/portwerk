"""Port-Reservierungen verwalten: Ports für einen Zweck/ein Projekt freihalten (Planer am Standort des Ports oder Administratoren)."""
from __future__ import annotations

import re
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .. import access, audit, db, reservations
from ..auth import Principal, current_principal
from . import masterdata, workorders

router = APIRouter(prefix="/api/reservations", tags=["reservierungen"])
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ReservationIn(BaseModel):
    port_ids: list[int] = Field(min_length=1, max_length=500)
    purpose: str = Field(min_length=1, max_length=200)
    until: Optional[str] = None
    workorder_id: Optional[int] = None


class ReservationUpdate(BaseModel):
    purpose: str = Field(min_length=1, max_length=200)
    until: Optional[str] = None
    workorder_id: Optional[int] = None


class ReleaseIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)


def _check_until(until: Optional[str]) -> Optional[str]:
    if not until:
        return None
    if not DATE_RE.match(until):
        raise HTTPException(400, "„Reserviert bis“: Datum als JJJJ-MM-TT")
    if until < reservations.today():
        raise HTTPException(400, "„Reserviert bis“ liegt in der Vergangenheit")
    return until


def _check_workorder(me: Principal, wid: Optional[int]) -> Optional[int]:
    if not wid:
        return None
    w = workorders._wo_or_404(wid, me)
    if w["status"] not in reservations.PLANNING_STATES:
        raise HTTPException(400, f"{w['number']} ist bereits abgeschlossen")
    return wid


def _may_plan(me: Principal, port_id: int) -> bool:
    return me.kind == "user" and me.has_at(access.site_of_port(port_id), "planer")


def _row_or_404(rid: int, me: Principal) -> dict:
    r = db.row("SELECT * FROM port_reservations WHERE id = ?", (rid,))
    if not r or not access.can_read_site(me, access.site_of_port(r["port_id"])):
        raise HTTPException(404, "Reservierung nicht gefunden")
    return r


def _may_change(me: Principal, r: dict) -> None:
    if not (_may_plan(me, r["port_id"]) or (me.kind == "user" and r["reserved_by"].casefold() == me.name.casefold())):
        raise HTTPException(403, "Nur Planer am Standort oder wer reserviert hat")


def _out(r: dict) -> dict:
    return {"id": r["id"], "port_id": r["port_id"], "port": r["port_name"], "device_id": r["device_id"], "hostname": r["hostname"],
            "location": masterdata.location_path(r["location_id"]) if r["location_id"] else "",
            "purpose": r["purpose"], "reserved_by": r["reserved_by"], "until": r["until"], "created_at": r["created_at"],
            "expired": bool(r["until"] and r["until"] < reservations.today()), "busy": bool(r["busy"]),
            "workorder": {"id": r["workorder_id"], "number": r["wo_number"]} if r["workorder_id"] else None}


LIST_SQL = """SELECT r.*, p.name AS port_name, d.id AS device_id, d.hostname, d.location_id, w.number AS wo_number,
                     EXISTS(SELECT 1 FROM cables c WHERE c.port_a_id = p.id OR c.port_b_id = p.id) AS busy
              FROM port_reservations r JOIN ports p ON p.id = r.port_id JOIN devices d ON d.id = p.device_id
              LEFT JOIN workorders w ON w.id = r.workorder_id"""


@router.get("")
def list_reservations(device_id: Optional[int] = None, q: Optional[str] = Query(None, max_length=100), expired: Optional[bool] = None,
                      me: Principal = Depends(current_principal)):
    """Reservierungen im eigenen Bereich; ``expired``: nur abgelaufene (true) bzw. nur gültige (false)."""
    where, args = [], []
    clause, cargs = access.device_clause(me, "d")
    if clause:
        where.append(clause); args += cargs
    if device_id:
        where.append("d.id = ?"); args.append(device_id)
    if q:
        where.append("(r.purpose LIKE ? OR d.hostname LIKE ? OR r.reserved_by LIKE ?)"); args += [f"%{q}%"] * 3
    if expired is True:
        where.append("r.until IS NOT NULL AND r.until < ?"); args.append(reservations.today())
    elif expired is False:
        where.append("(r.until IS NULL OR r.until >= ?)"); args.append(reservations.today())
    w = ("WHERE " + " AND ".join(where)) if where else ""
    rows = db.rows(f"{LIST_SQL} {w} ORDER BY r.purpose COLLATE NOCASE, d.hostname COLLATE NOCASE, p.name", tuple(args))
    out = [_out(r) for r in rows]
    nk = masterdata._natural_key
    out.sort(key=lambda x: (x["purpose"].casefold(), nk(x["hostname"]), nk(x["port"])))
    return out


@router.post("", status_code=201)
def reserve(body: ReservationIn, me: Principal = Depends(current_principal)):
    """Ports reservieren. Bereits gültig reservierte Ports werden nicht überschrieben (409); abgelaufene Reservierungen werden ersetzt."""
    until, wid = _check_until(body.until), _check_workorder(me, body.workorder_id)
    ids = sorted(set(body.port_ids))
    for pid in ids:
        if not db.row("SELECT id FROM ports WHERE id = ?", (pid,)):
            raise HTTPException(404, f"Port {pid} nicht gefunden")
        access.require_read(me, access.site_of_port(pid), "Port")
        if not _may_plan(me, pid):
            raise HTTPException(403, "Reservieren dürfen Planer am Standort des Ports")
    taken = reservations.active(ids)
    if taken:
        raise HTTPException(409, detail={"code": "already_reserved", "message": "Schon reserviert: " + "; ".join(
            f"{reservations._label(p)} für „{r['purpose']}“ ({r['reserved_by']})" for p, r in taken.items()),
            "port_ids": sorted(taken)})
    now, purpose = time.time(), body.purpose.strip()
    with db.transaction() as c:
        c.execute(f"DELETE FROM port_reservations WHERE port_id IN ({','.join('?' * len(ids))})", ids)      # abgelaufene ersetzen
        for pid in ids:
            c.execute("INSERT INTO port_reservations(port_id, purpose, reserved_by, workorder_id, until, created_at) VALUES (?,?,?,?,?,?)",
                      (pid, purpose, me.name, wid, until, now))
    audit.log(me.name, "reservation.create", "port", ",".join(map(str, ids[:50])), f"{len(ids)} Port(s) für „{purpose}“" + (f" bis {until}" if until else ""))
    rows = db.rows(f"{LIST_SQL} WHERE r.port_id IN ({','.join('?' * len(ids))})", tuple(ids))
    return [_out(r) for r in rows]


@router.put("/{rid}")
def update(rid: int, body: ReservationUpdate, me: Principal = Depends(current_principal)):
    r = _row_or_404(rid, me)
    _may_change(me, r)
    db.execute("UPDATE port_reservations SET purpose = ?, until = ?, workorder_id = ? WHERE id = ?",
               (body.purpose.strip(), _check_until(body.until), _check_workorder(me, body.workorder_id), rid))
    audit.log(me.name, "reservation.update", "port", r["port_id"], f"„{body.purpose.strip()}“")
    return _out(db.row(f"{LIST_SQL} WHERE r.id = ?", (rid,)))


@router.delete("/{rid}")
def release(rid: int, me: Principal = Depends(current_principal)):
    r = _row_or_404(rid, me)
    _may_change(me, r)
    db.execute("DELETE FROM port_reservations WHERE id = ?", (rid,))
    audit.log(me.name, "reservation.delete", "port", r["port_id"], f"„{r['purpose']}“ ({r['reserved_by']})")
    return {"ok": True}


@router.post("/release")
def release_many(body: ReleaseIn, me: Principal = Depends(current_principal)):
    rows = [_row_or_404(i, me) for i in sorted(set(body.ids))]
    for r in rows:
        _may_change(me, r)
    with db.transaction() as c:
        for r in rows:
            c.execute("DELETE FROM port_reservations WHERE id = ?", (r["id"],))
    audit.log(me.name, "reservation.delete", "port", ",".join(str(r["port_id"]) for r in rows[:50]), f"{len(rows)} Reservierung(en) freigegeben")
    return {"released": len(rows)}
