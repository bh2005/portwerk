"""Arbeitsplatz-Assistent: „Neuer Arbeitsplatz an Dose X“ → Strecke bis zum Patchfeld verfolgen, freien Switchport vorschlagen,
Profil/VLAN wählen und daraus einen Patchauftrag machen.

Ablauf
1. Ab dem Port der Dose die dokumentierte Strecke verfolgen (Pfad-Tracer). Das Ende am Patchfeld ohne Patchkabel ist der Patchpunkt.
   Reicht die Strecke schon bis zu einem Switch, ist die Dose verbunden – dann gibt es nur noch „Port umkonfigurieren“.
2. Freie Switchports vorschlagen: zuerst im selben Rack wie das Patchfeld, dann am gleichen übergeordneten Ort, dann am Standort.
   Frei = kein Kabel, nicht reserviert, nicht von einem offenen Auftrag verplant, Gerät nicht außer Betrieb, kein Steckmodul-Port.
3. Position „herstellen“ Patchpunkt ↔ Switchport mit Ziel-Konfiguration am Switchport; optional Dose ↔ Endgerät.
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import HTTPException

from . import access, db, pathtrace, portcfg, reservations
from .auth import Principal
from .compare import THROUGH_TYPES

MODULE_MEDIA = ("SFP", "SFP+", "SFP28", "QSFP", "LWL")


def _port(pid: Optional[int]) -> Optional[dict]:
    return db.row("""SELECT p.id, p.name, p.medium, p.peer_port_id, d.id AS device_id, d.hostname, d.type, d.status, d.location_id, l.site_id
                     FROM ports p JOIN devices d ON d.id = p.device_id LEFT JOIN locations l ON l.id = d.location_id WHERE p.id = ?""", (pid,)) if pid else None


def label(p: dict) -> str:
    return f"{p['hostname']}:{p['name']}"


def analyse(outlet_port_id: int, me: Principal) -> dict:
    """Strecke ab der Dose: {state: connected|open|undocumented, patch_point, user_port, switch_port, path, why}."""
    start = _port(outlet_port_id)
    if not start:
        raise HTTPException(404, "Port nicht gefunden")
    access.require_read(me, start["site_id"], "Port")
    t = pathtrace.trace(outlet_port_id, me)
    nodes = t["nodes"]
    ends = [(nodes[0], nodes[0]["ports"][0]), (nodes[-1], nodes[-1]["ports"][-1])]
    switch = next((p for n, p in ends if n["device"]["type"] in portcfg.SWITCH_TYPES and p["id"]), None)
    user_side = next((p for n, p in ends if n["device"]["id"] == start["device_id"]), None)
    out = {"path": t, "user_port": _port(user_side["id"]) if user_side and user_side["id"] else start}
    if t["complete"] or switch:
        out.update(state="connected", switch_port=_port(switch["id"]) if switch else None,
                   why="Die Dose ist bereits bis zum Switch verbunden" if switch else "Die Strecke ist bereits durchgängig")
        return out
    patch = next((p for n, p in ends if n["device"]["id"] != start["device_id"] and n["device"]["type"] == "patchpanel" and p["id"]), None)
    if not patch:
        out.update(state="undocumented", why="Die Strecke ab der Dose ist nicht bis zu einem Patchfeld dokumentiert")
        return out
    out.update(state="open", patch_point=_port(patch["id"]), why="")
    return out


def candidates(patch_port: dict, me: Principal, limit: int = 20) -> list[dict]:
    """Freie Switchports nach Nähe zum Patchfeld: 0 = selbes Rack/Raum, 1 = gleicher übergeordneter Ort, 2 = gleicher Standort."""
    if not patch_port["site_id"]:
        return []
    locs = {l["id"]: l for l in db.rows("SELECT id, parent_id FROM locations WHERE site_id = ?", (patch_port["site_id"],))}
    here = locs.get(patch_port["location_id"]) or {"id": None, "parent_id": None}
    vis = access.visible_sites(me)
    if vis is not None and patch_port["site_id"] not in vis:
        return []
    busy = {r["p"] for r in db.rows("SELECT port_a_id AS p FROM cables UNION SELECT port_b_id FROM cables")}
    rows = db.rows(f"""SELECT p.id, p.name, p.medium, d.id AS device_id, d.hostname, d.type, d.location_id, d.status
                       FROM ports p JOIN devices d ON d.id = p.device_id
                       WHERE d.type IN ({','.join('?' * len(portcfg.SWITCH_TYPES))}) AND d.status <> 'retired'
                         AND d.location_id IN ({','.join('?' * len(locs)) or 'NULL'})""", (*portcfg.SWITCH_TYPES, *locs))
    rows = [r for r in rows if r["id"] not in busy and (r["medium"] not in MODULE_MEDIA or patch_port["medium"] in MODULE_MEDIA)]
    res, plan = reservations.active(r["id"] for r in rows), reservations.planned(r["id"] for r in rows)
    from .routers.masterdata import _natural_key as nk, location_path

    def rank(r: dict) -> int:
        loc = locs.get(r["location_id"]) or {}
        if r["location_id"] == here["id"]:
            return 0
        return 1 if here["parent_id"] and loc.get("parent_id") == here["parent_id"] else 2
    free = sorted((r for r in rows if r["id"] not in res and r["id"] not in plan), key=lambda r: (rank(r), nk(r["hostname"]), nk(r["name"])))
    return [{"port_id": r["id"], "port": r["name"], "device_id": r["device_id"], "hostname": r["hostname"], "medium": r["medium"],
             "location": location_path(r["location_id"]) if r["location_id"] else "", "distance": rank(r),
             "distance_label": ("im selben Rack/Raum", "in der Nähe", "am Standort")[rank(r)]} for r in free[:limit]]


def target_cfg(profile_id: Optional[int], cfg: Optional[dict]) -> Optional[dict]:
    if cfg:
        return portcfg.normalize(cfg)
    if profile_id:
        return portcfg.normalize({"profile_id": profile_id})
    return None


def cfg_json(c: Optional[dict]) -> str:
    return json.dumps(c) if c else ""


def is_passive(p: dict) -> bool:
    return p["type"] in THROUGH_TYPES
