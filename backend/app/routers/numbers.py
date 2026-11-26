"""Rufnummernplan (Telefonie): Rufnummernblöcke mit Durchwahlbereich und die vergebenen bzw. reservierten Durchwahlen.
Freie Nummern ergeben sich aus dem Bereich. Vergabe ist Verwaltungsarbeit (kein Patchauftrag) und wird im Audit-Log festgehalten."""
from __future__ import annotations

import csv
import io
import re
import time
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import access, audit, db
from ..auth import Principal, current_principal
from .wan import _csv_cell, _date, _site_name

router = APIRouter(prefix="/api/numbers", tags=["telephony"], dependencies=[Depends(access.require_area("telephony"))])

MAX_RANGE = 10000                     # Durchwahlen je Block
STATUSES = ("assigned", "reserved")
STATUS_LABELS = {"assigned": "vergeben", "reserved": "reserviert", "free": "frei"}
KINDS = ("person", "function", "group", "fax", "special", "other")
KIND_LABELS = {"person": "Person", "function": "Funktion (Zentrale, Empfang …)", "group": "Sammelruf / Gruppe", "fax": "Fax",
               "special": "Sonderanschluss (Aufzug, Notruf, Alarm …)", "other": "Sonstiges"}
_PREFIX_RE = re.compile(r"^\+?[0-9][0-9 ()/-]{1,30}$")


class BlockIn(BaseModel):
    site_id:      int
    sip_trunk_id: Optional[int] = None
    name:         str = Field(default="", max_length=120)
    prefix:       str = Field(min_length=2, max_length=32)
    range_from:   int = Field(ge=0, le=99999999)
    range_to:     int = Field(ge=0, le=99999999)
    width:        int = Field(default=0, ge=0, le=8)
    note:         str = Field(default="", max_length=2000)


class AssignmentIn(BaseModel):
    status:         str = "assigned"
    kind:           str = "person"
    holder:         str = Field(default="", max_length=200)
    device_id:      Optional[int] = None
    reserved_until: Optional[str] = None
    note:           str = Field(default="", max_length=2000)


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def ext_text(b: dict, ext: int) -> str:
    return str(ext).zfill(b["width"]) if b["width"] else str(ext)


def full_number(b: dict, ext: int) -> str:
    return f"{b['prefix']}-{ext_text(b, ext)}"


def _expired(a: dict) -> bool:
    return a["status"] == "reserved" and bool(a["reserved_until"]) and a["reserved_until"] < date.today().isoformat()


def _counts(b: dict) -> dict:
    total = b["range_to"] - b["range_from"] + 1
    rows = db.rows("SELECT status, reserved_until FROM number_assignments WHERE block_id = ?", (b["id"],))
    assigned = sum(1 for r in rows if r["status"] == "assigned")
    reserved = sum(1 for r in rows if r["status"] == "reserved")
    return {"total": total, "assigned": assigned, "reserved": reserved, "free": total - assigned - reserved,
            "expired": sum(1 for r in rows if _expired(r))}


def block_out(b: dict) -> dict:
    t = db.row("SELECT id, name, status FROM sip_trunks WHERE id = ?", (b["sip_trunk_id"],)) if b["sip_trunk_id"] else None
    return {**dict(b), "site": _site_name(b["site_id"]), "trunk": dict(t) if t else None,
            "first": full_number(b, b["range_from"]), "last": full_number(b, b["range_to"]), "counts": _counts(b)}


def _device(did: Optional[int]) -> Optional[dict]:
    r = db.row("SELECT id, hostname, type FROM devices WHERE id = ?", (did,)) if did else None
    return dict(r) if r else None


def assignment_out(b: dict, a: dict) -> dict:
    return {**dict(a), "number": full_number(b, a["extension"]), "ext": ext_text(b, a["extension"]),
            "status_label": STATUS_LABELS[a["status"]], "kind_label": KIND_LABELS.get(a["kind"], a["kind"]),
            "device": _device(a["device_id"]), "expired": _expired(a)}


def block_or_404(bid: int, me: Principal) -> dict:
    b = db.row("SELECT * FROM number_blocks WHERE id = ?", (bid,))
    if not b or not access.can_read_site(me, b["site_id"]):
        raise HTTPException(404, "Rufnummernblock nicht gefunden")
    return b


def _require_assign(me: Principal, site_id: int) -> None:
    """Durchwahlen vergeben: Planer am Standort, Bereichs-/globale Admins oder API-Zugänge mit Umfang write."""
    if not (access.can_write_site(me, site_id) or me.has_at(site_id, "planer")):
        raise HTTPException(403, "Durchwahlen vergeben dürfen Planer und Administratoren des Standorts")


def _check_block(v: dict, bid: Optional[int] = None) -> dict:
    v["prefix"] = re.sub(r"\s+", " ", v["prefix"].strip())
    v["name"] = v["name"].strip()
    v["note"] = v["note"].strip()
    if not _PREFIX_RE.match(v["prefix"]):
        raise HTTPException(422, "Präfix: Ziffern mit optionalem +, Leerzeichen, Klammern, / oder - (z. B. +49 6181 1234)")
    if v["range_to"] < v["range_from"]:
        raise HTTPException(422, "Der Bereich endet vor seinem Anfang")
    if v["range_to"] - v["range_from"] + 1 > MAX_RANGE:
        raise HTTPException(422, f"Höchstens {MAX_RANGE} Durchwahlen je Block")
    if not db.row("SELECT 1 AS x FROM sites WHERE id = ?", (v["site_id"],)):
        raise HTTPException(422, "Standort existiert nicht")
    if v.get("sip_trunk_id"):
        t = db.row("SELECT site_id FROM sip_trunks WHERE id = ?", (v["sip_trunk_id"],))
        if not t:
            raise HTTPException(422, "SIP-Trunk existiert nicht")
        if t["site_id"] != v["site_id"]:
            raise HTTPException(422, "Der SIP-Trunk gehört zu einem anderen Standort")
    for o in db.rows("SELECT * FROM number_blocks WHERE id <> ?", (bid or 0,)):
        if _digits(o["prefix"]) == _digits(v["prefix"]) and o["range_from"] <= v["range_to"] and v["range_from"] <= o["range_to"]:
            raise HTTPException(409, f"Überschneidet sich mit dem Block {o['prefix']} {o['range_from']}–{o['range_to']}"
                                     + (f" ({o['name']})" if o["name"] else ""))
    if bid:
        outside = db.row("SELECT COUNT(*) AS n FROM number_assignments WHERE block_id = ? AND (extension < ? OR extension > ?)",
                         (bid, v["range_from"], v["range_to"]))["n"]
        if outside:
            raise HTTPException(409, f"{outside} vergebene oder reservierte Durchwahl(en) lägen außerhalb des neuen Bereichs")
    return v


# ── Blöcke ────────────────────────────────────────────────────────────────────

@router.get("/meta")
def meta(_: Principal = Depends(current_principal)):
    return {"statuses": [{"value": s, "label": STATUS_LABELS[s]} for s in STATUSES],
            "kinds": [{"value": k, "label": KIND_LABELS[k]} for k in KINDS], "max_range": MAX_RANGE}


@router.get("/blocks")
def list_blocks(site_id: Optional[int] = None, sip_trunk_id: Optional[int] = None, me: Principal = Depends(current_principal)):
    out = []
    for b in db.rows("SELECT * FROM number_blocks ORDER BY prefix, range_from"):
        if not access.can_read_site(me, b["site_id"]):
            continue
        if (site_id and b["site_id"] != site_id) or (sip_trunk_id and b["sip_trunk_id"] != sip_trunk_id):
            continue
        out.append(block_out(b))
    return out


@router.post("/blocks", status_code=201)
def create_block(body: BlockIn, me: Principal = Depends(access.require_writer)):
    access.require_write(me, body.site_id)
    v = _check_block(body.model_dump())
    now = time.time()
    v.update(created_by=me.name, created_at=now, updated_at=now)
    bid = db.execute(f"INSERT INTO number_blocks({','.join(v)}) VALUES ({','.join('?' * len(v))})", tuple(v.values()))
    audit.log(me.name, "numbers.block.create", "number_block", bid, f"{v['prefix']} {v['range_from']}–{v['range_to']}")
    return block_out(db.row("SELECT * FROM number_blocks WHERE id = ?", (bid,)))


@router.put("/blocks/{bid}")
def update_block(bid: int, body: BlockIn, me: Principal = Depends(access.require_writer)):
    b = block_or_404(bid, me)
    access.require_write(me, b["site_id"])
    access.require_write(me, body.site_id)
    v = _check_block(body.model_dump(), bid)
    v["updated_at"] = time.time()
    db.execute(f"UPDATE number_blocks SET {','.join(k + '=?' for k in v)} WHERE id = ?", (*v.values(), bid))
    audit.log(me.name, "numbers.block.update", "number_block", bid, f"{v['prefix']} {v['range_from']}–{v['range_to']}")
    return block_out(db.row("SELECT * FROM number_blocks WHERE id = ?", (bid,)))


@router.delete("/blocks/{bid}")
def delete_block(bid: int, me: Principal = Depends(access.require_writer)):
    b = block_or_404(bid, me)
    access.require_write(me, b["site_id"])
    n = db.row("SELECT COUNT(*) AS n FROM number_assignments WHERE block_id = ?", (bid,))["n"]
    if n:
        raise HTTPException(409, f"Im Block sind noch {n} Durchwahl(en) vergeben oder reserviert – erst freigeben")
    db.execute("DELETE FROM number_blocks WHERE id = ?", (bid,))
    audit.log(me.name, "numbers.block.delete", "number_block", bid, f"{b['prefix']} {b['range_from']}–{b['range_to']}")
    return {"ok": True}


@router.get("/blocks/{bid}")
def get_block(bid: int, me: Principal = Depends(current_principal)):
    """Block mit allen vergebenen/reservierten Durchwahlen (freie ergeben sich aus dem Bereich)."""
    b = block_or_404(bid, me)
    rows = db.rows("SELECT * FROM number_assignments WHERE block_id = ? ORDER BY extension", (bid,))
    return {**block_out(b), "assignments": [assignment_out(b, a) for a in rows],
            "can_assign": access.can_write_site(me, b["site_id"]) or me.has_at(b["site_id"], "planer"),
            "can_edit": access.can_write_site(me, b["site_id"])}


@router.get("/blocks/{bid}/next-free")
def next_free(bid: int, after: Optional[int] = None, me: Principal = Depends(current_principal)):
    b = block_or_404(bid, me)
    used = {r["extension"] for r in db.rows("SELECT extension FROM number_assignments WHERE block_id = ?", (bid,))}
    start = max(b["range_from"], (after + 1) if after is not None else b["range_from"])
    for ext in range(start, b["range_to"] + 1):
        if ext not in used:
            return {"extension": ext, "ext": ext_text(b, ext), "number": full_number(b, ext)}
    raise HTTPException(409, "Im Block ist keine Durchwahl mehr frei")


# ── Durchwahlen ───────────────────────────────────────────────────────────────

@router.put("/blocks/{bid}/ext/{ext}")
def set_assignment(bid: int, ext: int, body: AssignmentIn, me: Principal = Depends(current_principal)):
    b = block_or_404(bid, me)
    _require_assign(me, b["site_id"])
    if not b["range_from"] <= ext <= b["range_to"]:
        raise HTTPException(422, "Die Durchwahl liegt nicht im Bereich des Blocks")
    if body.status not in STATUSES:
        raise HTTPException(422, f"Ungültiger Status: {body.status}")
    if body.kind not in KINDS:
        raise HTTPException(422, f"Ungültige Art: {body.kind}")
    holder = body.holder.strip()
    if body.status == "assigned" and not holder:
        raise HTTPException(422, "Bitte angeben, wem bzw. welcher Funktion die Durchwahl gehört")
    until = _date(body.reserved_until, "Reserviert bis") if body.status == "reserved" else None
    if body.device_id:
        if not db.row("SELECT 1 AS x FROM devices WHERE id = ?", (body.device_id,)):
            raise HTTPException(422, "Endgerät existiert nicht")
        if not access.can_read_site(me, access.site_of_device(body.device_id)):
            raise HTTPException(422, "Endgerät existiert nicht")
    now = time.time()
    cur = db.row("SELECT * FROM number_assignments WHERE block_id = ? AND extension = ?", (bid, ext))
    vals = (body.status, body.kind, holder, body.device_id, until, body.note.strip(), me.name, now)
    if cur:
        db.execute("""UPDATE number_assignments SET status=?, kind=?, holder=?, device_id=?, reserved_until=?, note=?, updated_by=?, updated_at=?
                      WHERE id = ?""", (*vals, cur["id"]))
    else:
        db.execute("""INSERT INTO number_assignments(status, kind, holder, device_id, reserved_until, note, updated_by, updated_at, block_id, extension, created_at)
                      VALUES (?,?,?,?,?,?,?,?,?,?,?)""", (*vals, bid, ext, now))
    num = full_number(b, ext)
    audit.log(me.name, "numbers.assign" if body.status == "assigned" else "numbers.reserve", "number_block", bid,
              f"{num}: {holder or '-'}" + (f" (bis {until})" if until else "") + (f", vorher {cur['holder'] or cur['status']}" if cur else ""))
    return assignment_out(b, db.row("SELECT * FROM number_assignments WHERE block_id = ? AND extension = ?", (bid, ext)))


@router.delete("/blocks/{bid}/ext/{ext}")
def free_assignment(bid: int, ext: int, me: Principal = Depends(current_principal)):
    b = block_or_404(bid, me)
    _require_assign(me, b["site_id"])
    cur = db.row("SELECT * FROM number_assignments WHERE block_id = ? AND extension = ?", (bid, ext))
    if not cur:
        raise HTTPException(404, "Die Durchwahl ist nicht vergeben")
    db.execute("DELETE FROM number_assignments WHERE id = ?", (cur["id"],))
    audit.log(me.name, "numbers.free", "number_block", bid, f"{full_number(b, ext)}: war {cur['holder'] or cur['status']}")
    return {"ok": True}


def find(me: Principal, q: str, limit: int = 50) -> list[dict]:
    """Durchwahlen nach Inhaber/Notiz oder Rufnummer (Ziffernfolge, auch Teil) – für Suche und Schnellsuche."""
    ql, qd = q.strip().lower(), _digits(q).lstrip("0")         # führende 0/00 weg: 06181… findet auch +49 6181…
    blocks = {b["id"]: b for b in db.rows("SELECT * FROM number_blocks") if access.can_read_site(me, b["site_id"])}
    out = []
    for a in db.rows("SELECT * FROM number_assignments ORDER BY block_id, extension"):
        b = blocks.get(a["block_id"])
        if not b:
            continue
        num = full_number(b, a["extension"])
        hit = (ql and (ql in a["holder"].lower() or ql in a["note"].lower())) or (len(qd) >= 2 and qd in _digits(num))
        if hit:
            out.append({**assignment_out(b, a), "block_name": b["name"], "site_id": b["site_id"]})
            if len(out) >= limit:
                break
    return out


@router.get("/by-device/{did}")
def by_device(did: int, me: Principal = Depends(current_principal)):
    out = []
    for a in db.rows("SELECT * FROM number_assignments WHERE device_id = ? ORDER BY block_id, extension", (did,)):
        b = db.row("SELECT * FROM number_blocks WHERE id = ?", (a["block_id"],))
        if b and access.can_read_site(me, b["site_id"]):
            out.append(assignment_out(b, a))
    return out


@router.get("/search")
def search(q: str, me: Principal = Depends(current_principal)):
    return find(me, q) if q.strip() else []


@router.get("/export.csv")
def export_csv(block_id: Optional[int] = None, include_free: bool = False, me: Principal = Depends(current_principal)):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Rufnummer", "Durchwahl", "Block", "Standort", "Status", "Art", "Inhaber / Funktion", "Endgerät", "Reserviert bis", "Notiz"])
    for bo in list_blocks(me=me):
        if block_id and bo["id"] != block_id:
            continue
        b = db.row("SELECT * FROM number_blocks WHERE id = ?", (bo["id"],))
        got = {a["extension"]: a for a in db.rows("SELECT * FROM number_assignments WHERE block_id = ?", (b["id"],))}
        for ext in range(b["range_from"], b["range_to"] + 1):
            a = got.get(ext)
            if not a and not include_free:
                continue
            o = assignment_out(b, a) if a else None
            w.writerow([_csv_cell(x) for x in (full_number(b, ext), ext_text(b, ext), b["name"] or b["prefix"], bo["site"],
                                               o["status_label"] if o else "frei", o["kind_label"] if o else "", o["holder"] if o else "",
                                               (o["device"] or {}).get("hostname", "") if o else "", o["reserved_until"] if o else "",
                                               o["note"] if o else "")])
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="rufnummernplan.csv"'})
