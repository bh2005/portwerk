"""Port-Reservierungen und „verplante“ Ports.

Ein Port gilt beim Planen als vergeben, wenn
* er ausdrücklich reserviert ist (Tabelle ``port_reservations``, nicht abgelaufen), oder
* ein anderer offener Patchauftrag ihn mit „herstellen“/„umstecken“ belegen will.

``check`` meldet das als Rückfrage (409 ``port_reserved``); mit ``use_reserved`` wird trotzdem geplant – ausdrückliche Reservierungen
werden dabei freigegeben (Audit-Log). Reservierungen für genau den Auftrag, in dem geplant wird, sind kein Konflikt.
"""
from __future__ import annotations

import sqlite3
import time
from typing import Iterable, Optional

from fastapi import HTTPException

from . import audit, db

PLANNING_STATES = ("draft", "submitted", "approved", "in_progress", "done", "rework")


def today() -> str:
    return time.strftime("%Y-%m-%d")


def _ids(port_ids: Iterable) -> list[int]:
    return sorted({int(p) for p in port_ids if p})


def active(port_ids: Iterable, c: Optional[sqlite3.Connection] = None) -> dict[int, dict]:
    """Nicht abgelaufene Reservierungen je Port."""
    ids = _ids(port_ids)
    if not ids:
        return {}
    ph = ",".join("?" * len(ids))
    sql = f"""SELECT r.*, w.number AS wo_number FROM port_reservations r LEFT JOIN workorders w ON w.id = r.workorder_id
              WHERE r.port_id IN ({ph}) AND (r.until IS NULL OR r.until >= ?)"""
    rows = [dict(r) for r in c.execute(sql, (*ids, today()))] if c else db.rows(sql, (*ids, today()))
    return {r["port_id"]: r for r in rows}


def planned(port_ids: Iterable, exclude_workorder: Optional[int] = None) -> dict[int, dict]:
    """Ports, die ein offener Auftrag verbinden will (erster Auftrag je Port)."""
    ids = _ids(port_ids)
    if not ids:
        return {}
    ph = ",".join("?" * len(ids))
    out: dict[int, dict] = {}
    for r in db.rows(f"""SELECT w.id, w.number, w.title, w.status, i.port_a_id, i.port_b_id FROM workitems i JOIN workorders w ON w.id = i.workorder_id
                         WHERE i.action IN ('connect', 'move') AND w.status IN ({",".join("?" * len(PLANNING_STATES))})
                           AND (i.port_a_id IN ({ph}) OR i.port_b_id IN ({ph})) AND w.id != ?
                         ORDER BY w.id""", (*PLANNING_STATES, *ids, *ids, exclude_workorder or 0)):
        for pid in (r["port_a_id"], r["port_b_id"]):
            if pid in ids and pid not in out:
                out[pid] = {"id": r["id"], "number": r["number"], "title": r["title"]}
    return out


def _label(pid: int) -> str:
    r = db.row("SELECT d.hostname, p.name FROM ports p JOIN devices d ON d.id = p.device_id WHERE p.id = ?", (pid,))
    return f"{r['hostname']}:{r['name']}" if r else f"Port {pid}"


def conflicts(port_ids: Iterable, workorder_id: Optional[int] = None) -> list[dict]:
    ids = _ids(port_ids)
    res, plan = active(ids), planned(ids, workorder_id)
    out = []
    for pid in ids:
        r = res.get(pid)
        if r and not (workorder_id and r["workorder_id"] == workorder_id):
            out.append({"port_id": pid, "port": _label(pid), "kind": "reservation", "reservation_id": r["id"], "purpose": r["purpose"],
                        "reserved_by": r["reserved_by"], "until": r["until"],
                        "workorder": {"id": r["workorder_id"], "number": r["wo_number"]} if r["workorder_id"] else None})
        elif pid in plan:
            out.append({"port_id": pid, "port": _label(pid), "kind": "planned", "workorder": plan[pid]})
    return out


def message(cs: list[dict]) -> str:
    parts = []
    for x in cs:
        if x["kind"] == "reservation":
            parts.append(f"{x['port']} ist reserviert für „{x['purpose']}“ ({x['reserved_by']}" + (f", bis {x['until']}" if x["until"] else "") + ")")
        else:
            parts.append(f"{x['port']} ist bereits in {x['workorder']['number']} ({x['workorder']['title']}) verplant")
    return "; ".join(parts) + ". Trotzdem verwenden? Reservierungen werden dabei freigegeben."


def check(port_ids: Iterable, *, use_reserved: bool, by: str, workorder_id: Optional[int] = None, dry_run: bool = False) -> list[dict]:
    """Rückfrage bei reservierten/verplanten Ports; mit ``use_reserved`` werden die Reservierungen freigegeben (außer im Trockenlauf)."""
    cs = conflicts(port_ids, workorder_id)
    if not cs:
        return []
    if not use_reserved:
        raise HTTPException(409, detail={"code": "port_reserved", "message": message(cs), "conflicts": cs})
    if not dry_run:
        for x in cs:
            if x["kind"] == "reservation":
                db.execute("DELETE FROM port_reservations WHERE id = ?", (x["reservation_id"],))
                audit.log(by, "reservation.override", "port", x["port_id"], f"{x['port']}: „{x['purpose']}“ von {x['reserved_by']} freigegeben")
    return cs


def release_for_workorder(workorder_id: int, port_ids: Iterable, by: str) -> int:
    """Nach dem Bestätigen: Reservierungen der jetzt verkabelten Ports aufheben."""
    ids = _ids(port_ids)
    if not ids:
        return 0
    ph = ",".join("?" * len(ids))
    rows = db.rows(f"SELECT id, port_id FROM port_reservations WHERE port_id IN ({ph}) AND workorder_id = ?",
                   (*ids, workorder_id))
    for r in rows:
        db.execute("DELETE FROM port_reservations WHERE id = ?", (r["id"],))
    if rows:
        audit.log(by, "reservation.release", "workorder", workorder_id, f"{len(rows)} Reservierung(en) nach Bestätigung aufgehoben")
    return len(rows)
