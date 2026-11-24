"""Geräte aus OpenPlan übernehmen (Konzept, Abschnitt 6, Richtung 3).

OpenPlan führt Geräte-Rollouts als Vorgänge mit Gerätedaten (``ext_key`` gesetzt, ``attrs``: hostname, standort, loc, typ, modell, raum,
rack „R3 / HE 12“, ip, seriennummer, alt_host …). ``preview`` liest ein Projekt (``GET /api/projects/{pid}``, dafür genügt der vorhandene
API-Zugang) und ordnet jedes Gerät zu:

* Standort: Location-Code (``loc``) = Standort-Code in Portwerk, sonst Standortname bzw. -code = ``standort``
* Ort: Rack mit dem Namen aus „Rack / HE“ (bei mehreren gleichnamigen das im passenden Raum), sonst der Raum, sonst offen (Auswahl im Dialog)
* Typ aus dem Gerätetyp der Vorlage (Switch, Access Point, Firewall …), Katalogmodell über „Hersteller Modell“ oder „Modell“

``apply`` legt die gewählten Geräte als **geplant** an (Recht: Planer am Standort oder Bereichs-Administrator) (Quelle „openplan“, mit Ports aus dem Katalogmodell, auf der HE, wenn sie frei ist)
oder verknüpft ein vorhandenes Gerät gleichen Namens. In OpenPlan bekommt der Geräte-Vorgang die Referenz ``portwerk`` mit Link zurück
(Fehler dabei stören die Übernahme nicht).
"""
from __future__ import annotations

import re
import time
from typing import Optional

from fastapi import HTTPException

from . import access, audit, db, openplan, rackmount
from .auth import Principal
from .schemas import CONTAINER_KINDS

PLACE_KINDS = ("room", "machine", "vehicle", "rack", "wallrack", "cabinet")
TYPE_WORDS = (("access point", "ap"), ("accesspoint", "ap"), ("wlan", "ap"), ("firewall", "firewall"), ("router", "router"), ("switch", "switch"),
              ("server", "server"), ("usv", "ups"), ("ups", "ups"), ("pdu", "pdu"), ("gateway", "gateway"), ("drucker", "endpoint"),
              ("printer", "endpoint"), ("kamera", "endpoint"), ("camera", "endpoint"))
RACK_RE = re.compile(r"^\s*(?P<rack>[^/]+?)\s*(?:/\s*(?:HE|RU|U)?\s*(?P<pos>\d+))?\s*$", re.I)


def _require_plan(me: Principal, site_id: Optional[int]) -> None:
    """Geplante Geräte anlegen/verknüpfen: wer am Standort Stammdaten schreiben darf oder dort Planer ist (wie beim Geräte-Assistenten per Auftrag)."""
    if not (access.can_write_site(me, site_id) or (me.kind == "user" and me.has_at(site_id, "planer"))):
        raise HTTPException(403, "Keine Berechtigung für diesen Standort (Planer oder Bereichs-Administrator nötig)")


def ref(pid: int, tid: int) -> str:
    return f"{pid}:{tid}"


def guess_type(typ: str) -> str:
    t = (typ or "").lower()
    for word, dtype in TYPE_WORDS:
        if word in t:
            return dtype
    return "other"


def parse_rack(s: str) -> tuple[str, Optional[int]]:
    m = RACK_RE.match(s or "")
    if not m:
        return "", None
    return m.group("rack").strip(), int(m.group("pos")) if m.group("pos") else None


class _World:
    def __init__(self, me: Principal):
        from .routers.masterdata import location_path
        vs = access.visible_sites(me)
        self.sites = [s for s in db.rows("SELECT id, code, name FROM sites ORDER BY code") if vs is None or s["id"] in vs]
        self.locs = db.rows("SELECT id, site_id, parent_id, kind, name, rack_units FROM locations")
        self.loc_by_id = {l["id"]: l for l in self.locs}
        self.path = {l["id"]: location_path(l["id"]) for l in self.locs if l["kind"] in PLACE_KINDS}
        self.hosts = {d["hostname"].lower(): d for d in db.rows("SELECT id, hostname, status, openplan_ref, location_id FROM devices")}
        self.linked = {d["openplan_ref"]: d for d in self.hosts.values() if d["openplan_ref"]}
        self.models = db.rows("SELECT id, vendor, model, type, height_u FROM device_models WHERE active = 1")

    def site(self, a: dict) -> Optional[dict]:
        loc, name = (a.get("loc") or "").strip().lower(), (a.get("standort") or "").strip().lower()
        for s in self.sites:
            if loc and s["code"].lower() == loc:
                return s
        for s in self.sites:
            if name and (s["name"].lower() == name or s["code"].lower() == name):
                return s
        return None

    def ancestors(self, lid: Optional[int]) -> list[str]:
        out = []
        while lid and lid in self.loc_by_id:
            out.append(self.loc_by_id[lid]["name"].lower())
            lid = self.loc_by_id[lid]["parent_id"]
        return out

    def place(self, site_id: int, a: dict) -> tuple[Optional[int], Optional[int], str]:
        """(Location, HE, Hinweis) – Rack nach Name (Raum entscheidet bei Mehrdeutigkeit), sonst Raum."""
        rack_name, pos = parse_rack(a.get("rack", ""))
        room_parts = [p.strip().lower() for p in re.split(r"[/,]", a.get("raum", "")) if p.strip()]
        in_site = [l for l in self.locs if l["site_id"] == site_id]
        if rack_name:
            racks = [l for l in in_site if l["kind"] in CONTAINER_KINDS and l["name"].lower() == rack_name.lower()]
            if len(racks) > 1 and room_parts:
                racks = [l for l in racks if any(p in self.ancestors(l["parent_id"]) for p in room_parts)] or racks
            if len(racks) == 1:
                return racks[0]["id"], pos, ""
            if len(racks) > 1:
                return None, None, f"Rack „{rack_name}“ gibt es mehrfach – bitte Ort wählen"
        rooms = [l for l in in_site if l["kind"] in ("room", "machine") and room_parts and l["name"].lower() == room_parts[-1]]
        if len(rooms) == 1:
            return rooms[0]["id"], None, f"Rack „{rack_name}“ nicht gefunden – Raum gewählt" if rack_name else ""
        return None, None, "Ort nicht gefunden – bitte wählen" if (rack_name or room_parts) else "Kein Ort angegeben – bitte wählen"

    def model(self, text: str) -> Optional[dict]:
        t = (text or "").strip().lower()
        if not t:
            return None
        hit = [m for m in self.models if f"{m['vendor']} {m['model']}".strip().lower() == t] or [m for m in self.models if m["model"].lower() == t]
        return hit[0] if len(hit) == 1 else None


def preview(pid: int, me: Principal) -> dict:
    cfg = openplan.require_enabled()
    proj = openplan.call("GET", f"/api/projects/{pid}", None, cfg)
    w = _World(me)
    items = []
    for t in proj.get("tasks", []):
        a = t.get("attrs") or {}
        if t.get("ext_key") is None or not a.get("hostname"):
            continue                                                         # nur Geräte-Vorgänge
        host = a["hostname"].strip()
        site = w.site(a)
        model = w.model(a.get("modell", ""))
        dtype = model["type"] if model else guess_type(a.get("typ", ""))
        it = {"task_id": t["id"], "hostname": host, "typ": a.get("typ", ""), "type": dtype, "modell": a.get("modell", ""),
              "model_id": model["id"] if model else None, "model_label": f"{model['vendor']} {model['model']}".strip() if model else "",
              "ip": a.get("ip", ""), "serial": a.get("seriennummer", ""), "standort": a.get("standort", ""), "loc": a.get("loc", ""),
              "raum": a.get("raum", ""), "rack": a.get("rack", ""), "alt_host": a.get("alt_host", ""), "status": t.get("status", ""),
              "site_id": site["id"] if site else None, "site": f"{site['code']} · {site['name']}" if site else "",
              "location_id": None, "rack_position": None, "hint": "", "device": None}
        linked = w.linked.get(ref(pid, t["id"]))
        same = w.hosts.get(host.lower())
        if linked:
            it.update(state="linked", device={"id": linked["id"], "hostname": linked["hostname"], "status": linked["status"]})
        elif same:
            it.update(state="exists", device={"id": same["id"], "hostname": same["hostname"], "status": same["status"]},
                      hint="Gerät mit diesem Namen gibt es schon – verknüpfen" + (" (es hat schon einen anderen OpenPlan-Verweis)" if same["openplan_ref"] else ""))
        elif not site:
            it.update(state="no_site", hint=f"Standort „{a.get('loc') or a.get('standort') or '–'}“ nicht in Portwerk (oder nicht sichtbar)")
        else:
            lid, pos, hint = w.place(site["id"], a)
            it.update(state="new", location_id=lid, rack_position=pos, hint=hint)
        if a.get("alt_host") and a["alt_host"].lower() in w.hosts and a["alt_host"].lower() != host.lower():
            it["hint"] = (it["hint"] + " · " if it["hint"] else "") + f"ersetzt {a['alt_host']}"
        items.append(it)
    items.sort(key=lambda i: ({"new": 0, "exists": 1, "no_site": 2, "linked": 3}[i["state"]], i["site"], i["hostname"].lower()))
    places: dict[int, list] = {}
    for lid, path in w.path.items():
        sid = w.loc_by_id[lid]["site_id"]
        if any(s["id"] == sid for s in w.sites):
            places.setdefault(sid, []).append({"id": lid, "path": path, "kind": w.loc_by_id[lid]["kind"]})
    for v in places.values():
        v.sort(key=lambda x: x["path"].lower())
    counts = {k: sum(1 for i in items if i["state"] == k) for k in ("new", "exists", "no_site", "linked")}
    return {"project": {"id": proj["project"]["id"], "name": proj["project"]["name"]}, "items": items, "counts": counts, "places": places}


def _link_back(cfg: dict, tid: int, did: int, hostname: str) -> str:
    base = openplan.own_url(cfg)
    try:
        # Geräte-Vorgänge sind Sammelvorgänge (Schritte darunter): Referenz direkt setzen – /events gilt nur für Blatt-Vorgänge
        openplan.request("PUT", f"/api/tasks/{tid}/refs/{openplan.SYSTEM}", {"ref": hostname, "url": f"{base}/devices/{did}" if base else ""}, cfg)
        return ""
    except openplan.OpenPlanError as e:
        return e.message


def apply(pid: int, picks: list[dict], me: Principal) -> dict:
    """``picks``: [{task_id, location_id?, type?}] – „new“ wird angelegt, „exists“ verknüpft; anderes wird übersprungen."""
    from .routers.masterdata import _apply_model_ports
    cfg = openplan.settings()
    pv = preview(pid, me)
    by_tid = {i["task_id"]: i for i in pv["items"]}
    created, linked, skipped, warnings = [], [], [], []
    for p in picks:
        it = by_tid.get(p.get("task_id"))
        if not it or it["state"] not in ("new", "exists"):
            skipped.append({"task_id": p.get("task_id"), "hostname": it["hostname"] if it else "?", "why": "nicht übernehmbar (Stand geändert?)"})
            continue
        if it["state"] == "exists":
            d = it["device"]
            _require_plan(me, access.site_of_device(d["id"]))
            db.execute("UPDATE devices SET openplan_ref = ?, updated_at = ? WHERE id = ?", (ref(pid, it["task_id"]), time.time(), d["id"]))
            audit.log(me.name, "device.openplan_link", "device", d["id"], f"OpenPlan-Projekt {pid}, Vorgang {it['task_id']}")
            err = _link_back(cfg, it["task_id"], d["id"], d["hostname"])
            linked.append({"id": d["id"], "hostname": d["hostname"]})
            if err:
                warnings.append(f"{d['hostname']}: Rückverweis in OpenPlan fehlgeschlagen ({err})")
            continue
        lid = p.get("location_id") or it["location_id"]
        loc = db.row("SELECT * FROM locations WHERE id = ?", (lid,)) if lid else None
        if not loc or loc["site_id"] != it["site_id"]:
            skipped.append({"task_id": it["task_id"], "hostname": it["hostname"], "why": "Ort fehlt (muss am Standort liegen)"})
            continue
        _require_plan(me, loc["site_id"])
        dtype = p.get("type") or it["type"]
        model = db.row("SELECT * FROM device_models WHERE id = ?", (it["model_id"],)) if it["model_id"] else None
        height = model["height_u"] if model else 1
        pos = it["rack_position"] if lid == it["location_id"] else None
        if pos and loc["kind"] in CONTAINER_KINDS:
            top = pos + height - 1
            if (loc["rack_units"] and top > loc["rack_units"]) or rackmount.rack_conflicts(loc, "horizontal", "both", "", pos, height):
                warnings.append(f"{it['hostname']}: HE {pos} ist belegt oder passt nicht – ohne HE-Position angelegt")
                pos = None
        elif loc["kind"] not in CONTAINER_KINDS:
            pos = None
        now = time.time()
        note = f"Aus OpenPlan übernommen: {pv['project']['name']}" + (f", ersetzt {it['alt_host']}" if it["alt_host"] else "")
        did = db.execute("""INSERT INTO devices(hostname, type, vendor, model, serial, mgmt_ip, location_id, rack_position, height_u, status, source, note,
                                                model_id, openplan_ref, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?, 'planned', 'openplan', ?,?,?,?,?)""",
                         (it["hostname"], dtype if dtype in _types() else "other", model["vendor"] if model else "", model["model"] if model else it["modell"],
                          it["serial"], it["ip"], lid, pos, height, note, model["id"] if model else None, ref(pid, it["task_id"]), now, now))
        ports = _apply_model_ports(did, model)[0] if model else 0
        audit.log(me.name, "device.from_openplan", "device", did, f"{it['hostname']} aus OpenPlan-Projekt {pid}, Vorgang {it['task_id']}" + (f", {ports} Ports" if ports else ""))
        err = _link_back(cfg, it["task_id"], did, it["hostname"])
        if err:
            warnings.append(f"{it['hostname']}: Rückverweis in OpenPlan fehlgeschlagen ({err})")
        created.append({"id": did, "hostname": it["hostname"], "ports": ports, "rack_position": pos})
    return {"created": created, "linked": linked, "skipped": skipped, "warnings": warnings}


def _types() -> tuple:
    from .schemas import DEVICE_TYPES
    return DEVICE_TYPES
