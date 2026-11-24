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

from .. import access, audit, compare, db, reservations
from ..access import require_writer
from ..auth import Principal, current_principal, require_admin

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
    lo, hi = (a, b) if a < b else (b, a)
    cid = db.execute(
        """INSERT INTO cables(port_a_id, port_b_id, cable_label, cable_type, note, created_by, created_at, provisional)
           VALUES (?,?,?,?,?,?,?,1)""",
        (lo, hi, "", "other", "Aus Soll/Ist-Abgleich übernommen (LLDP/CDP) – Strecke noch nicht vollständig dokumentiert", me.name, time.time()))
    audit.log(me.name, "cable.adopt", "port", a, f"-> {b}")
    return {"cable_id": cid, "port_a_id": lo, "port_b_id": hi}


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
