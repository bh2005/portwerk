"""WAN-Verbindungen: Leitungsverzeichnis. Inbetriebnahme, Änderung und Kündigung laufen als Positionen in Patchaufträgen
(``wan_activate`` / ``wan_change`` / ``wan_terminate``, siehe workorders)."""
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

router = APIRouter(prefix="/api/wan", tags=["wan"], dependencies=[Depends(access.require_area("wan"))])

STATUSES = ("planned", "ordered", "active", "suspended", "terminated")
STATUS_LABELS = {"planned": "geplant", "ordered": "bestellt", "active": "in Betrieb", "suspended": "ruhend", "terminated": "gekündigt"}
TECHNOLOGIES = ("fiber", "mpls", "dsl", "cable", "lte", "sdwan", "leased", "other")
TECH_LABELS = {"fiber": "Glasfaser", "mpls": "MPLS", "dsl": "DSL", "cable": "Kabel/Koax", "lte": "Mobilfunk (LTE/5G)", "sdwan": "SD-WAN",
               "leased": "Mietleitung", "other": "Sonstige"}
PATCH_FIELDS = ("name", "technology", "provider", "circuit_id", "bandwidth_down", "bandwidth_up", "contract_number", "contract_start",
                "contract_end", "notice_days", "monthly_cost", "contact", "note", "remote_label", "site_b_id", "port_a_id", "port_b_id")
TEXT_FIELDS = ("name", "remote_label", "provider", "circuit_id", "contract_number", "contact", "note")


class WanIn(BaseModel):
    name:            str = Field(min_length=1, max_length=120)
    status:          str = "planned"
    technology:      str = "other"
    site_a_id:       int
    site_b_id:       Optional[int] = None
    remote_label:    str = ""
    port_a_id:       Optional[int] = None
    port_b_id:       Optional[int] = None
    provider:        str = ""
    circuit_id:      str = ""
    bandwidth_down:  Optional[float] = Field(default=None, ge=0)
    bandwidth_up:    Optional[float] = Field(default=None, ge=0)
    contract_number: str = ""
    contract_start:  Optional[str] = None
    contract_end:    Optional[str] = None
    notice_days:     Optional[int] = Field(default=None, ge=0, le=3650)
    monthly_cost:    Optional[float] = Field(default=None, ge=0)
    contact:         str = ""
    note:            str = ""


def _date(v: Optional[str], what: str) -> Optional[str]:
    if not v:
        return None
    try:
        return date.fromisoformat(v).isoformat()
    except ValueError:
        raise HTTPException(422, f"{what}: Datum im Format JJJJ-MM-TT erwartet")


def _site_name(sid: Optional[int]) -> str:
    r = db.row("SELECT code, name FROM sites WHERE id = ?", (sid,)) if sid else None
    return f"{r['code']} – {r['name']}" if r else ""


def _port_info(pid: Optional[int]) -> Optional[dict]:
    if not pid:
        return None
    r = db.row("SELECT p.id, p.name, p.device_id, d.hostname FROM ports p JOIN devices d ON d.id = p.device_id WHERE p.id = ?", (pid,))
    return {"id": r["id"], "name": r["name"], "device_id": r["device_id"], "device_hostname": r["hostname"]} if r else None


def out(r: dict) -> dict:
    d = dict(r)
    d.update({
        "status_label": STATUS_LABELS.get(r["status"], r["status"]), "technology_label": TECH_LABELS.get(r["technology"], r["technology"]),
        "site_a": _site_name(r["site_a_id"]), "site_b": _site_name(r["site_b_id"]) or r["remote_label"],
        "port_a": _port_info(r["port_a_id"]), "port_b": _port_info(r["port_b_id"]),
        "days_left": (date.fromisoformat(r["contract_end"]) - date.today()).days if r["contract_end"] else None,
    })
    return d


def link_or_404(lid: int, me: Optional[Principal] = None) -> dict:
    r = db.row("SELECT * FROM wan_links WHERE id = ?", (lid,))
    if not r or (me is not None and not (access.can_read_site(me, r["site_a_id"]) or access.can_read_site(me, r["site_b_id"]))):
        raise HTTPException(404, "WAN-Verbindung nicht gefunden")
    return r


def check_values(v: dict, link_id: Optional[int] = None) -> None:
    """Prüft (Teil-)Werte einer Verbindung: Technik, Datumsangaben, Standorte, Ports (nicht doppelt belegt)."""
    if "technology" in v and v["technology"] not in TECHNOLOGIES:
        raise HTTPException(422, f"Ungültige Technik: {v['technology']}")
    for k in ("contract_start", "contract_end"):
        if k in v:
            v[k] = _date(v[k], k)
    if v.get("contract_start") and v.get("contract_end") and v["contract_end"] < v["contract_start"]:
        raise HTTPException(422, "Vertragsende liegt vor dem Vertragsbeginn")
    if v.get("site_b_id") and not db.row("SELECT 1 AS x FROM sites WHERE id = ?", (v["site_b_id"],)):
        raise HTTPException(422, "Gegenstelle: Standort existiert nicht")
    for key, site_key in (("port_a_id", "site_a_id"), ("port_b_id", "site_b_id")):
        pid = v.get(key)
        if not pid:
            continue
        if not db.row("SELECT 1 AS x FROM ports WHERE id = ?", (pid,)):
            raise HTTPException(422, f"{key}: Port existiert nicht")
        if v.get(site_key) and access.site_of_port(pid) != v[site_key]:
            raise HTTPException(422, "Der Port gehört nicht zum gewählten Standort (" + ("A" if key == "port_a_id" else "B") + ")")
        busy = db.row("SELECT id, name FROM wan_links WHERE status <> 'terminated' AND (port_a_id = ? OR port_b_id = ?) AND id <> ?", (pid, pid, link_id or 0))
        if busy:
            raise HTTPException(409, {"code": "port_busy", "message": f"Der Port ist bereits der WAN-Verbindung „{busy['name']}“ zugeordnet",
                                      "conflicts": [{"wan_link_id": busy["id"], "name": busy["name"]}]})


def _values(body: WanIn) -> dict:
    v = body.model_dump()
    for k in TEXT_FIELDS:
        v[k] = v[k].strip()
    return v


def _csv_cell(x):
    s = "" if x is None else str(x)
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s


@router.get("/meta")
def meta(_: Principal = Depends(current_principal)):
    return {"statuses": [{"value": s, "label": STATUS_LABELS[s]} for s in STATUSES],
            "technologies": [{"value": t, "label": TECH_LABELS[t]} for t in TECHNOLOGIES]}


@router.get("")
def list_links(status: str = "", site_id: Optional[int] = None, q: str = "", expiring_days: Optional[int] = None,
               me: Principal = Depends(current_principal)):
    res = []
    for r in db.rows("SELECT * FROM wan_links ORDER BY name COLLATE NOCASE"):
        if not (access.can_read_site(me, r["site_a_id"]) or access.can_read_site(me, r["site_b_id"])):
            continue
        if status and r["status"] != status:
            continue
        if site_id and site_id not in (r["site_a_id"], r["site_b_id"]):
            continue
        o = out(r)
        if q:
            hay = " ".join(str(o.get(k) or "") for k in ("name", "provider", "circuit_id", "contract_number", "site_a", "site_b", "note")).lower()
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
    w.writerow(["Name", "Status", "Technik", "Standort A", "Standort B / Gegenstelle", "Provider", "Leitungs-ID", "Down Mbit/s", "Up Mbit/s",
                "Vertrag", "Vertragsende", "Kündigungsfrist Tage", "Kosten/Monat", "Kontakt"])
    for o in list_links(me=me):
        w.writerow([_csv_cell(x) for x in (o["name"], o["status_label"], o["technology_label"], o["site_a"], o["site_b"], o["provider"], o["circuit_id"],
                                           o["bandwidth_down"], o["bandwidth_up"], o["contract_number"], o["contract_end"], o["notice_days"],
                                           o["monthly_cost"], o["contact"])])
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="wan-verbindungen.csv"'})


@router.get("/{lid}")
def get_link(lid: int, me: Principal = Depends(current_principal)):
    o = out(link_or_404(lid, me))
    o["orders"] = [dict(x) for x in db.rows(
        """SELECT DISTINCT w.id, w.number, w.title, w.status, i.action FROM workitems i JOIN workorders w ON w.id = i.workorder_id
           WHERE i.wan_link_id = ? ORDER BY w.id DESC""", (lid,))]
    o["sip_trunks"] = [{"id": t["id"], "name": t["name"], "status": t["status"], "status_label": STATUS_LABELS.get(t["status"], t["status"])}
                       for t in db.rows("SELECT id, name, status, site_id FROM sip_trunks WHERE wan_link_id = ? ORDER BY name COLLATE NOCASE", (lid,))
                       if me.can_see("telephony") and access.can_read_site(me, t["site_id"])]
    return o


@router.post("", status_code=201)
def create_link(body: WanIn, me: Principal = Depends(access.require_writer)):
    if body.status not in STATUSES:
        raise HTTPException(422, f"Ungültiger Status: {body.status}")
    if not db.row("SELECT 1 AS x FROM sites WHERE id = ?", (body.site_a_id,)):
        raise HTTPException(422, "Standort A existiert nicht")
    access.require_write(me, body.site_a_id)
    v = _values(body)
    check_values(v)
    now = time.time()
    v.update(created_by=me.name, created_at=now, updated_at=now, activated_at=now if v["status"] == "active" else None,
             terminated_at=now if v["status"] == "terminated" else None)
    lid = db.execute(f"INSERT INTO wan_links({','.join(v)}) VALUES ({','.join('?' * len(v))})", tuple(v.values()))
    audit.log(me.name, "wan.create", "wan", lid, v["name"])
    return out(db.row("SELECT * FROM wan_links WHERE id = ?", (lid,)))


@router.put("/{lid}")
def update_link(lid: int, body: WanIn, me: Principal = Depends(access.require_writer)):
    r = link_or_404(lid, me)
    access.require_write(me, r["site_a_id"])
    if body.status not in STATUSES:
        raise HTTPException(422, f"Ungültiger Status: {body.status}")
    if not db.row("SELECT 1 AS x FROM sites WHERE id = ?", (body.site_a_id,)):
        raise HTTPException(422, "Standort A existiert nicht")
    if body.site_a_id != r["site_a_id"]:
        access.require_write(me, body.site_a_id)
    v = _values(body)
    check_values(v, lid)
    now = time.time()
    v["updated_at"] = now
    if v["status"] == "active" and r["status"] != "active":
        v["activated_at"] = now
    if v["status"] == "terminated" and r["status"] != "terminated":
        v["terminated_at"] = now
    db.execute(f"UPDATE wan_links SET {','.join(k + '=?' for k in v)} WHERE id = ?", (*v.values(), lid))
    audit.log(me.name, "wan.update", "wan", lid, v["name"])
    return out(db.row("SELECT * FROM wan_links WHERE id = ?", (lid,)))


@router.delete("/{lid}")
def delete_link(lid: int, me: Principal = Depends(access.require_writer)):
    r = link_or_404(lid, me)
    access.require_write(me, r["site_a_id"])
    if r["status"] not in ("planned", "terminated"):
        raise HTTPException(409, "Nur geplante oder gekündigte Verbindungen können gelöscht werden – laufende bitte per Auftrag kündigen")
    db.execute("DELETE FROM wan_links WHERE id = ?", (lid,))
    audit.log(me.name, "wan.delete", "wan", lid, r["name"])
    return {"ok": True}


# ── Anwendung aus Aufträgen ───────────────────────────────────────────────────

def apply_item(item: dict) -> None:
    """Wird beim Bestätigen eines Auftrags für WAN-Positionen aufgerufen."""
    lid = item["wan_link_id"]
    if not lid or not db.row("SELECT 1 AS x FROM wan_links WHERE id = ?", (lid,)):
        return
    now = time.time()
    if item["action"] == "wan_activate":
        db.execute("UPDATE wan_links SET status='active', activated_at=?, terminated_at=NULL, updated_at=? WHERE id=?", (now, now, lid))
    elif item["action"] == "wan_terminate":
        db.execute("UPDATE wan_links SET status='terminated', terminated_at=?, updated_at=? WHERE id=?", (now, now, lid))
    elif item["action"] == "wan_change":
        try:
            patch = json.loads(item["wan_patch"] or "{}")
        except ValueError:
            patch = {}
        patch = {k: v for k, v in patch.items() if k in PATCH_FIELDS}
        if patch:
            db.execute(f"UPDATE wan_links SET {','.join(k + '=?' for k in patch)}, updated_at=? WHERE id=?", (*patch.values(), now, lid))


def validate_item(me: Principal, action: str, lid: Optional[int], patch: dict) -> dict:
    """Prüft eine WAN-Position beim Anlegen; liefert die bereinigten Änderungswerte (nur bei wan_change)."""
    if not me.can_see("wan"):
        raise HTTPException(403, "Kein Zugriff auf diesen Bereich (Freigabe durch einen Administrator nötig)")
    r = db.row("SELECT * FROM wan_links WHERE id = ?", (lid,)) if lid else None
    if not r:
        raise HTTPException(400, "Für WAN-Positionen muss eine vorhandene WAN-Verbindung gewählt werden")
    if not me.is_global and not me.has_at(r["site_a_id"], "planer"):
        raise HTTPException(403, "Die WAN-Verbindung liegt außerhalb deines Bereichs")
    if action == "wan_activate" and r["status"] in ("active", "terminated"):
        raise HTTPException(409, f"Die Verbindung ist bereits {STATUS_LABELS[r['status']]} und kann nicht in Betrieb genommen werden")
    if action == "wan_terminate" and r["status"] == "terminated":
        raise HTTPException(409, "Die Verbindung ist bereits gekündigt")
    if action != "wan_change":
        return {}
    if r["status"] == "terminated":
        raise HTTPException(409, "Eine gekündigte Verbindung kann nicht geändert werden")
    bad = [k for k in patch if k not in PATCH_FIELDS]
    if bad:
        raise HTTPException(422, f"Nicht änderbar: {', '.join(bad)}")
    if not patch:
        raise HTTPException(422, "Keine Änderungen angegeben")
    probe = dict(patch)
    probe.setdefault("site_a_id", r["site_a_id"])
    probe.setdefault("site_b_id", r["site_b_id"])
    check_values(probe, lid)
    return {k: probe[k] for k in patch}
