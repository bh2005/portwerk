"""Soll/Ist-Abgleich (LLDP/CDP) und der Link zu Checkmk (Einstellungen in ``app_settings``, Schlüssel ``checkmk``)."""
from __future__ import annotations

import csv
import io
import json
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

import time

from .. import access, audit, checkmk_api, compare, db, reservations
from ..access import require_writer
from ..auth import Principal, current_principal, require_admin
from ..schemas import DEVICE_TYPES, DeviceIn, PortIn
from .masterdata import create_device, create_port

router = APIRouter(tags=["soll-ist"])

SETTING_KEY = "checkmk"
DEFAULTS = {"base_url": "", "link_all": True}


def link_settings() -> dict:
    r = db.row("SELECT value FROM app_settings WHERE key = ?", (SETTING_KEY,))
    return {**DEFAULTS, **(json.loads(r["value"]) if r else {})}


class CheckmkLinkIn(BaseModel):
    base_url: str = Field(default="", max_length=300)        # Adresse der Site, z. B. https://monitoring.example.test/prod
    link_all: bool = True                                    # auch für manuell angelegte Geräte (sonst nur Geräte aus dem Checkmk-Import)


@router.get("/api/integrations/checkmk")
def get_link(_: Principal = Depends(current_principal)):
    s = link_settings()
    return {"enabled": bool(s["base_url"]), "base_url": s["base_url"], "link_all": s["link_all"]}


@router.put("/api/admin/checkmk")
def put_link(body: CheckmkLinkIn, me: Principal = Depends(require_admin)):
    url = body.base_url.strip().rstrip("/")
    if url and not re.match(r"^https?://[^\s/]+(/[^\s?#]*)?$", url):
        raise HTTPException(422, "Adresse im Format https://host/site erwartet (ohne Parameter)")
    db.put_settings({SETTING_KEY: json.dumps({"base_url": url, "link_all": body.link_all})})
    audit.log(me.name, "checkmk.settings", "settings", 0, url or "aus")
    return get_link(me)


class CheckmkApiIn(BaseModel):
    enabled: Optional[bool] = None
    api_url: Optional[str] = Field(default=None, max_length=300)       # Site-Adresse ohne /check_mk/api, z. B. http://host/site
    user: Optional[str] = Field(default=None, max_length=80)
    secret: Optional[str] = Field(default=None, max_length=200)        # leer/fehlend = unverändert
    ca_pem: Optional[str] = Field(default=None, max_length=20000)
    verify_tls: Optional[bool] = None
    default_folder: Optional[str] = Field(default=None, max_length=300)


@router.get("/api/admin/checkmk-api")
def get_checkmk_api(_: Principal = Depends(require_admin)):
    return checkmk_api.public()


@router.put("/api/admin/checkmk-api")
def put_checkmk_api(body: CheckmkApiIn, me: Principal = Depends(require_admin)):
    out = checkmk_api.save(body.model_dump(exclude_none=True))
    audit.log(me.name, "settings.checkmk_api.save", "settings", 0, f"aktiv={out['enabled']}, {out['api_url']}, User {out['user']}, Standardordner {out['default_folder']}")
    return out


@router.post("/api/admin/checkmk-api/test")
def test_checkmk_api(_: Principal = Depends(require_admin)):
    return checkmk_api.check_connection()


@router.get("/api/checkmk/status")
def checkmk_status(_: Principal = Depends(current_principal)):
    s = checkmk_api.settings()
    return {"enabled": bool(s["enabled"] and s["api_url"] and s["user"] and s["secret"]), "default_folder": s["default_folder"]}


@router.get("/api/checkmk/host")
def checkmk_host(name: str, _: Principal = Depends(require_writer)):
    """Ist der Host in Checkmk vorhanden? (Ordner und IP, falls ja)"""
    return checkmk_api.host(name)


@router.get("/api/checkmk/folders")
def checkmk_folders(_: Principal = Depends(require_writer)):
    return checkmk_api.folders()


@router.get("/api/checkmk/location-tags")
def checkmk_location_tags(_: Principal = Depends(require_writer)):
    return checkmk_api.location_tags()


class CheckmkHostIn(BaseModel):
    hostname: str = Field(min_length=1, max_length=120)
    ip: str = Field(default="", max_length=80)
    folder: str = Field(default="", max_length=300)                    # leer = Standardordner aus den Einstellungen
    location_tag: str = Field(default="", max_length=40)               # Checkmk-Standort-Tag (z. B. LOC026); leer = keins


@router.post("/api/checkmk/hosts", status_code=201)
def checkmk_create_host(body: CheckmkHostIn, me: Principal = Depends(require_writer)):
    """Host in Checkmk anlegen – nur mit Host-Check (Ping), als ausstehende Änderung (Aktivierung in Checkmk). Nur mit globaler Berechtigung."""
    if not me.is_global:
        raise HTTPException(403, "Hosts in Checkmk anlegen nur mit globaler Berechtigung")
    res = checkmk_api.create_host(body.hostname, body.ip, body.folder, location_tag=body.location_tag)
    audit.log(me.name, "checkmk.host.create", "host", 0, f"{res['host_name']} -> {res['folder']}{', ' + res['location_tag'] if res['location_tag'] else ''} (Ping, Aktivierung ausstehend)")
    return res


@router.get("/api/compare")
def get_compare(site_id: Optional[int] = None, status: str = "", me: Principal = Depends(current_principal)):
    res = compare.compare(me, site_id)
    if status:
        wanted = set(status.split(","))
        res["rows"] = [r for r in res["rows"] if r["status"] in wanted]
    res["labels"] = compare.STATUS_LABELS
    return res


class AdoptIn(BaseModel):
    port_id: int


@router.post("/api/compare/adopt", status_code=201)
def adopt(body: AdoptIn, me: Principal = Depends(require_writer)):
    """„Verbindung übernehmen“: dokumentiert eine per LLDP/CDP gesehene, bisher undokumentierte Verbindung als Direktkabel.
    Das Kabel ist als vorläufig markiert – Dosen und Patchfelder lassen sich später nachtragen."""
    try:
        a, b = compare.adopt(body.port_id)
    except ValueError as e:
        raise HTTPException(409, str(e))
    access.require_write(me, access.site_of_port(a))
    access.require_write(me, access.site_of_port(b))                                  # beide Enden müssen im eigenen Bereich liegen
    reservations.check([a, b], use_reserved=False, by=me.name)
    cid, lo, hi = _insert_provisional(a, b, me)
    return {"cable_id": cid, "port_a_id": lo, "port_b_id": hi}


def _insert_provisional(a: int, b: int, me: Principal) -> tuple:
    lo, hi = (a, b) if a < b else (b, a)
    cid = db.execute(
        """INSERT INTO cables(port_a_id, port_b_id, cable_label, cable_type, note, created_by, created_at, provisional)
           VALUES (?,?,?,?,?,?,?,1)""",
        (lo, hi, "", "other", "Aus Soll/Ist-Abgleich übernommen (LLDP/CDP) – Strecke noch nicht vollständig dokumentiert", me.name, time.time()))
    audit.log(me.name, "cable.adopt", "port", a, f"-> {b}")
    return cid, lo, hi


class AdoptDeviceIn(BaseModel):
    obs_id: int                                              # gemeldeter Nachbar (Zeile aus dem Abgleich)
    hostname: str = Field(min_length=1, max_length=120)
    type: str = "other"
    mgmt_ip: str = Field(default="", max_length=80)
    neighbor_port: str = Field(default="", max_length=64)    # Portname am neuen Gerät; leer = keinen Port anlegen
    create_cable: bool = True                                # zusätzlich die Verbindung (vorläufig) dokumentieren


@router.post("/api/compare/adopt-device", status_code=201)
def adopt_device(body: AdoptDeviceIn, me: Principal = Depends(require_writer)):
    """„In Bestand übernehmen“: legt ein per LLDP/CDP gesehenes, aber unbekanntes Gerät an (am Standort des meldenden Geräts),
    bei Bedarf dessen Port und den unbekannten lokalen Port, und dokumentiert auf Wunsch die Verbindung als vorläufiges Direktkabel."""
    if body.type not in DEVICE_TYPES:
        raise HTTPException(400, "Gerätetyp ungültig")
    o = db.row("SELECT * FROM observations WHERE id = ?", (body.obs_id,))
    if not o:
        raise HTTPException(404, "Nachbar nicht gefunden (Abgleich neu laden)")
    local = db.row("SELECT * FROM devices WHERE id = ?", (o["device_id"],))
    access.require_write(me, access.site_of_device(local["id"]))
    w = compare._World()
    if w.device_by_neighbor(o["neighbor_name"], o["neighbor_address"]):
        raise HTTPException(409, "Das Gerät ist bereits im Bestand")
    dev = create_device(DeviceIn(hostname=body.hostname.strip(), type=body.type, mgmt_ip=body.mgmt_ip.strip(), location_id=local["location_id"],
                                 note="Aus Soll/Ist-Abgleich übernommen (LLDP/CDP)"), me)
    remote_port = None
    if body.neighbor_port.strip():
        remote_port = create_port(dev["id"], PortIn(name=body.neighbor_port.strip()), me)["id"]
    local_port = o["port_id"] or w.by_dev_port.get((local["id"], compare.norm_port(o["local_port"])))
    if not local_port and o["local_port"].strip():                                   # „Port unbekannt“: lokalen Port mit anlegen
        local_port = create_port(local["id"], PortIn(name=o["local_port"].strip()), me)["id"]
    if local_port and not o["port_id"]:
        db.execute("UPDATE observations SET port_id = ? WHERE id = ?", (local_port, o["id"]))
    cable_id, skipped = None, ""
    if body.create_cable:
        if not (local_port and remote_port):
            skipped = "Port fehlt"
        elif local_port in w.cable or local_port in w.peer:
            skipped = "lokaler Port ist bereits verbunden"
        else:
            cable_id = _insert_provisional(local_port, remote_port, me)[0]
    audit.log(me.name, "device.adopt", "device", dev["id"], f"{body.hostname} (gesehen von {local['hostname']}:{o['local_port']})")
    return {"device_id": dev["id"], "hostname": dev["hostname"], "port_id": remote_port, "cable_id": cable_id, "cable_skipped": skipped}


def _cell(x):
    s = "" if x is None else str(x)
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s


@router.get("/api/compare/export.csv")
def export_csv(site_id: Optional[int] = None, status: str = "", me: Principal = Depends(current_principal)):
    res = get_compare(site_id, status, me)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Ergebnis", "Gerät", "Port", "Soll (dokumentiert)", "Über", "Ist (gesehen)", "Protokoll"])
    for r in res["rows"]:
        soll = r["soll"] or {}
        w.writerow([_cell(x) for x in (r["status_label"], r["device"], r["port"], soll.get("label") or soll.get("why", ""), " → ".join(soll.get("via", [])),
                                       "; ".join(f"{i['name']}:{i['port']}" for i in r["ist"]), "; ".join(sorted({i["protocol"] for i in r["ist"]})))])
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="soll-ist.csv"'})
