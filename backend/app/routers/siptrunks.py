"""SIP-Trunks (Telefonie): Anschlüsse beim Provider mit SBC, TK-Anlage und WAN-Leitung. Einrichtung, Änderung und Kündigung
laufen wie bei WAN-Verbindungen als Positionen in Patchaufträgen (``trunk_activate`` / ``trunk_change`` / ``trunk_terminate``)."""
from __future__ import annotations

import csv
import io
import json
import time
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import access, audit, db
from ..auth import Principal, current_principal
from .wan import STATUS_LABELS, STATUSES, _csv_cell, _date, _site_name

router = APIRouter(prefix="/api/sip-trunks", tags=["telephony"], dependencies=[Depends(access.require_area("telephony"))])

MODES = ("registration", "static")
MODE_LABELS = {"registration": "Registrierung", "static": "statisch (IP-Peering)"}
SBC_TYPES = ("sbc", "voice_gateway", "gateway", "router", "firewall")      # Geräte, an denen ein Trunk ankommen kann
PBX_TYPES = ("pbx",)
PATCH_FIELDS = ("name", "mode", "provider", "trunk_ident", "registrar", "channels", "numbers", "sbc_device_id", "pbx_device_id", "wan_link_id",
                "contract_number", "contract_start", "contract_end", "notice_days", "monthly_cost", "contact", "note")
TEXT_FIELDS = ("name", "provider", "trunk_ident", "registrar", "numbers", "contract_number", "contact", "note")
ACTION_LABELS = {"trunk_activate": "in Betrieb nehmen", "trunk_change": "ändern", "trunk_terminate": "kündigen"}


class TrunkIn(BaseModel):
    name:            str = Field(min_length=1, max_length=120)
    status:          str = "planned"
    mode:            str = "registration"
    site_id:         int
    sbc_device_id:   Optional[int] = None
    pbx_device_id:   Optional[int] = None
    wan_link_id:     Optional[int] = None
    provider:        str = ""
    trunk_ident:     str = ""
    registrar:       str = ""
    channels:        Optional[int] = Field(default=None, ge=0, le=100000)
    numbers:         str = Field(default="", max_length=4000)
    contract_number: str = ""
    contract_start:  Optional[str] = None
    contract_end:    Optional[str] = None
    notice_days:     Optional[int] = Field(default=None, ge=0, le=3650)
    monthly_cost:    Optional[float] = Field(default=None, ge=0)
    contact:         str = ""
    note:            str = ""


def _device(did: Optional[int]) -> Optional[dict]:
    r = db.row("SELECT id, hostname, type, status FROM devices WHERE id = ?", (did,)) if did else None
    return dict(r) if r else None


def _wan(lid: Optional[int]) -> Optional[dict]:
    r = db.row("SELECT id, name, status, provider, circuit_id FROM wan_links WHERE id = ?", (lid,)) if lid else None
    return dict(r) if r else None


def out(r: dict) -> dict:
    d = dict(r)
    d.update({
        "status_label": STATUS_LABELS.get(r["status"], r["status"]), "mode_label": MODE_LABELS.get(r["mode"], r["mode"]),
        "site": _site_name(r["site_id"]), "sbc": _device(r["sbc_device_id"]), "pbx": _device(r["pbx_device_id"]), "wan": _wan(r["wan_link_id"]),
        "days_left": (date.fromisoformat(r["contract_end"]) - date.today()).days if r["contract_end"] else None,
    })
    return d


def trunk_or_404(tid: int, me: Optional[Principal] = None) -> dict:
    r = db.row("SELECT * FROM sip_trunks WHERE id = ?", (tid,))
    if not r or (me is not None and not access.can_read_site(me, r["site_id"])):
        raise HTTPException(404, "SIP-Trunk nicht gefunden")
    return r


def _check_device(did: Optional[int], site_id: int, types: tuple, what: str) -> None:
    if not did:
        return
    d = db.row("SELECT type FROM devices WHERE id = ?", (did,))
    if not d:
        raise HTTPException(422, f"{what}: Gerät existiert nicht")
    if d["type"] not in types:
        raise HTTPException(422, f"{what}: Gerätetyp passt nicht (erwartet: {', '.join(types)})")
    if access.site_of_device(did) != site_id:
        raise HTTPException(422, f"{what}: Das Gerät steht nicht am Standort des Trunks")


def check_values(v: dict) -> None:
    """Prüft (Teil-)Werte eines Trunks: Modus, Datumsangaben, Geräte und WAN-Leitung am Standort."""
    if "mode" in v and v["mode"] not in MODES:
        raise HTTPException(422, f"Ungültiger Modus: {v['mode']}")
    for k in ("contract_start", "contract_end"):
        if k in v:
            v[k] = _date(v[k], k)
    if v.get("contract_start") and v.get("contract_end") and v["contract_end"] < v["contract_start"]:
        raise HTTPException(422, "Vertragsende liegt vor dem Vertragsbeginn")
    site = v.get("site_id")
    if "sbc_device_id" in v:
        _check_device(v["sbc_device_id"], site, SBC_TYPES, "SBC")
    if "pbx_device_id" in v:
        _check_device(v["pbx_device_id"], site, PBX_TYPES, "TK-Anlage")
    if v.get("wan_link_id"):
        w = db.row("SELECT site_a_id, site_b_id FROM wan_links WHERE id = ?", (v["wan_link_id"],))
        if not w:
            raise HTTPException(422, "WAN-Leitung existiert nicht")
        if site not in (w["site_a_id"], w["site_b_id"]):
            raise HTTPException(422, "Die WAN-Leitung gehört nicht zum Standort des Trunks")


def _values(body: TrunkIn) -> dict:
    v = body.model_dump()
    for k in TEXT_FIELDS:
        v[k] = v[k].strip()
    return v


@router.get("/meta")
def meta(_: Principal = Depends(current_principal)):
    return {"statuses": [{"value": s, "label": STATUS_LABELS[s]} for s in STATUSES],
            "modes": [{"value": m, "label": MODE_LABELS[m]} for m in MODES],
            "sbc_types": list(SBC_TYPES), "pbx_types": list(PBX_TYPES)}


@router.get("")
def list_trunks(status: str = "", site_id: Optional[int] = None, q: str = "", expiring_days: Optional[int] = None,
                device_id: Optional[int] = None, wan_link_id: Optional[int] = None, me: Principal = Depends(current_principal)):
    res = []
    for r in db.rows("SELECT * FROM sip_trunks ORDER BY name COLLATE NOCASE"):
        if not access.can_read_site(me, r["site_id"]):
            continue
        if status and r["status"] != status:
            continue
        if site_id and r["site_id"] != site_id:
            continue
        if device_id and device_id not in (r["sbc_device_id"], r["pbx_device_id"]):
            continue
        if wan_link_id and r["wan_link_id"] != wan_link_id:
            continue
        o = out(r)
        if q:
            hay = " ".join(str(x or "") for x in (o["name"], o["provider"], o["trunk_ident"], o["registrar"], o["numbers"], o["contract_number"],
                                                  o["site"], (o["sbc"] or {}).get("hostname"), (o["pbx"] or {}).get("hostname"), o["note"])).lower()
            if q.lower() not in hay:
                continue
        if expiring_days is not None and (r["status"] == "terminated" or o["days_left"] is None or o["days_left"] > expiring_days):
            continue
        res.append(o)
    return res


@router.get("/export.csv")
def export_csv(me: Principal = Depends(current_principal)):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Name", "Status", "Modus", "Standort", "Provider", "Trunk-Kennung", "Registrar", "Kanäle", "Rufnummern", "SBC", "TK-Anlage",
                "WAN-Leitung", "Vertrag", "Vertragsende", "Kündigungsfrist Tage", "Kosten/Monat", "Kontakt"])
    for o in list_trunks(me=me):
        w.writerow([_csv_cell(x) for x in (o["name"], o["status_label"], o["mode_label"], o["site"], o["provider"], o["trunk_ident"], o["registrar"],
                                           o["channels"], " | ".join(x.strip() for x in o["numbers"].splitlines() if x.strip()),
                                           (o["sbc"] or {}).get("hostname"), (o["pbx"] or {}).get("hostname"), (o["wan"] or {}).get("name"),
                                           o["contract_number"], o["contract_end"], o["notice_days"], o["monthly_cost"], o["contact"])])
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="sip-trunks.csv"'})


@router.get("/{tid}")
def get_trunk(tid: int, me: Principal = Depends(current_principal)):
    o = out(trunk_or_404(tid, me))
    o["orders"] = [dict(x) for x in db.rows(
        """SELECT DISTINCT w.id, w.number, w.title, w.status, i.action FROM workitems i JOIN workorders w ON w.id = i.workorder_id
           WHERE i.sip_trunk_id = ? ORDER BY w.id DESC""", (tid,))]
    return o


def _check_site(me: Principal, body: TrunkIn) -> None:
    if body.status not in STATUSES:
        raise HTTPException(422, f"Ungültiger Status: {body.status}")
    if not db.row("SELECT 1 AS x FROM sites WHERE id = ?", (body.site_id,)):
        raise HTTPException(422, "Standort existiert nicht")
    access.require_write(me, body.site_id)


@router.post("", status_code=201)
def create_trunk(body: TrunkIn, me: Principal = Depends(access.require_writer)):
    _check_site(me, body)
    v = _values(body)
    check_values(v)
    now = time.time()
    v.update(created_by=me.name, created_at=now, updated_at=now, activated_at=now if v["status"] == "active" else None,
             terminated_at=now if v["status"] == "terminated" else None)
    tid = db.execute(f"INSERT INTO sip_trunks({','.join(v)}) VALUES ({','.join('?' * len(v))})", tuple(v.values()))
    audit.log(me.name, "sip_trunk.create", "sip_trunk", tid, v["name"])
    return out(db.row("SELECT * FROM sip_trunks WHERE id = ?", (tid,)))


@router.put("/{tid}")
def update_trunk(tid: int, body: TrunkIn, me: Principal = Depends(access.require_writer)):
    r = trunk_or_404(tid, me)
    access.require_write(me, r["site_id"])
    _check_site(me, body)
    v = _values(body)
    check_values(v)
    now = time.time()
    v["updated_at"] = now
    if v["status"] == "active" and r["status"] != "active":
        v["activated_at"] = now
    if v["status"] == "terminated" and r["status"] != "terminated":
        v["terminated_at"] = now
    db.execute(f"UPDATE sip_trunks SET {','.join(k + '=?' for k in v)} WHERE id = ?", (*v.values(), tid))
    audit.log(me.name, "sip_trunk.update", "sip_trunk", tid, v["name"])
    return out(db.row("SELECT * FROM sip_trunks WHERE id = ?", (tid,)))


@router.delete("/{tid}")
def delete_trunk(tid: int, me: Principal = Depends(access.require_writer)):
    r = trunk_or_404(tid, me)
    access.require_write(me, r["site_id"])
    if r["status"] not in ("planned", "terminated"):
        raise HTTPException(409, "Nur geplante oder gekündigte Trunks können gelöscht werden – laufende bitte per Auftrag kündigen")
    db.execute("DELETE FROM sip_trunks WHERE id = ?", (tid,))
    audit.log(me.name, "sip_trunk.delete", "sip_trunk", tid, r["name"])
    return {"ok": True}


# ── Anwendung aus Aufträgen ───────────────────────────────────────────────────

def apply_item(item: dict) -> None:
    """Wird beim Bestätigen eines Auftrags für Trunk-Positionen aufgerufen (Änderungswerte stehen in ``wan_patch``)."""
    tid = item["sip_trunk_id"]
    if not tid or not db.row("SELECT 1 AS x FROM sip_trunks WHERE id = ?", (tid,)):
        return
    now = time.time()
    if item["action"] == "trunk_activate":
        db.execute("UPDATE sip_trunks SET status='active', activated_at=?, terminated_at=NULL, updated_at=? WHERE id=?", (now, now, tid))
    elif item["action"] == "trunk_terminate":
        db.execute("UPDATE sip_trunks SET status='terminated', terminated_at=?, updated_at=? WHERE id=?", (now, now, tid))
    elif item["action"] == "trunk_change":
        try:
            patch = json.loads(item["wan_patch"] or "{}")
        except ValueError:
            patch = {}
        patch = {k: v for k, v in patch.items() if k in PATCH_FIELDS}
        if patch:
            db.execute(f"UPDATE sip_trunks SET {','.join(k + '=?' for k in patch)}, updated_at=? WHERE id=?", (*patch.values(), now, tid))


def validate_item(me: Principal, action: str, tid: Optional[int], patch: dict) -> dict:
    """Prüft eine Trunk-Position beim Anlegen; liefert die bereinigten Änderungswerte (nur bei trunk_change)."""
    if not me.can_see("telephony"):
        raise HTTPException(403, "Kein Zugriff auf diesen Bereich (Freigabe durch einen Administrator nötig)")
    r = db.row("SELECT * FROM sip_trunks WHERE id = ?", (tid,)) if tid else None
    if not r:
        raise HTTPException(400, "Für Trunk-Positionen muss ein vorhandener SIP-Trunk gewählt werden")
    if not me.is_global and not me.has_at(r["site_id"], "planer"):
        raise HTTPException(403, "Der SIP-Trunk liegt außerhalb deines Bereichs")
    if action == "trunk_activate" and r["status"] in ("active", "terminated"):
        raise HTTPException(409, f"Der Trunk ist bereits {STATUS_LABELS[r['status']]} und kann nicht in Betrieb genommen werden")
    if action == "trunk_terminate" and r["status"] == "terminated":
        raise HTTPException(409, "Der Trunk ist bereits gekündigt")
    if action != "trunk_change":
        return {}
    if r["status"] == "terminated":
        raise HTTPException(409, "Ein gekündigter Trunk kann nicht geändert werden")
    bad = [k for k in patch if k not in PATCH_FIELDS]
    if bad:
        raise HTTPException(422, f"Nicht änderbar: {', '.join(bad)}")
    if not patch:
        raise HTTPException(422, "Keine Änderungen angegeben")
    probe = {k: (v.strip() if isinstance(v, str) and k in TEXT_FIELDS else v) for k, v in patch.items()}
    if "name" in probe and not probe["name"]:
        raise HTTPException(422, "Der Name darf nicht leer sein")
    if "channels" in probe and probe["channels"] is not None and (not isinstance(probe["channels"], int) or probe["channels"] < 0):
        raise HTTPException(422, "Kanäle: ganze Zahl ab 0 erwartet")
    probe["site_id"] = r["site_id"]
    check_values(probe)
    return {k: probe[k] for k in patch}
