"""Autorouting: fehlende Patchungen von einem Quellport zu einem Zielport automatisch planen (Patchauftrag).

``dry_run`` (Standard) liefert nur die gefundenen Wege; ohne ``dry_run`` entsteht der Patchauftrag mit einer Position „herstellen“ je neuem Patchkabel.
Als Quelle dient ein vorhandener Port oder ein **neues Gerät**, das als „geplant“ (samt Einbau-Position) mit angelegt wird – dafür wird der Geräte-Assistent genutzt.
"""
from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import audit, db, reservations, routing
from ..auth import Principal, current_principal
from ..compare import THROUGH_TYPES
from ..schemas import DeviceWizardIn, PortGroup, UplinkIn
from . import wizards, workorders
from .catalog import check_cable_type

router = APIRouter(tags=["routing"])


class NewDeviceIn(BaseModel):
    """Geräteangaben für ein Gerät, das mit der Route zusammen als „geplant“ angelegt wird."""
    hostname: str = Field(min_length=1, max_length=120)
    type: str = "server"
    location_id: int                                              # Rack/Schrank, in den das Gerät kommt
    rack_position: Optional[int] = Field(default=None, ge=1, le=100)
    height_u: Optional[int] = Field(default=None, ge=1, le=50)
    model_id: Optional[int] = None                                # Katalogmodell (Ports aus der Vorlage) …
    vendor: str = ""
    model: str = ""
    nic_prefix: str = Field(default="NIC", min_length=1, max_length=48)   # … sonst NIC1 … NICn
    nic_count: int = Field(default=2, ge=1, le=64)
    medium: str = "RJ45"
    mgmt_ip: str = ""
    note: str = ""


class RouteIn(BaseModel):
    source_port_id: Optional[int] = None                          # vorhandener Quellport …
    new_device: Optional[NewDeviceIn] = None                      # … oder ein neues (geplantes) Gerät
    source_port_name: str = ""                                    # bei neuem Gerät: welcher Port (Standard: <Präfix>1)
    target_port_id: int
    cable_type: str = ""                                          # leer = passend zum Medium
    route_index: int = Field(default=0, ge=0, le=9)
    dry_run: bool = True
    workorder_id: Optional[int] = None                            # vorhandenen Entwurf ergänzen …
    workorder_title: str = ""                                     # … oder neuen Auftrag anlegen
    use_reserved: bool = False


def _port(pid: int) -> Optional[dict]:
    return db.row("""SELECT p.id, p.name, p.medium, d.id AS device_id, d.hostname, d.type, d.status, d.location_id, l.site_id
                     FROM ports p JOIN devices d ON d.id = p.device_id LEFT JOIN locations l ON l.id = d.location_id WHERE p.id = ?""", (pid,))


def auto_cable_type(medium: str) -> str:
    """Kabelart passend zum Medium: Glasfaser → erste aktive Glasfaser-Kabelart, sonst Cat6 (oder die erste aktive Kupferart)."""
    if routing.medium_group(medium) == "fiber":
        r = db.row("SELECT name FROM cable_types WHERE active = 1 AND category = 'fiber' ORDER BY sort, name LIMIT 1")
        if r:
            return r["name"]
    r = db.row("SELECT name FROM cable_types WHERE active = 1 AND name = 'Cat6'") or db.row("SELECT name FROM cable_types WHERE active = 1 AND category = 'copper' ORDER BY sort, name LIMIT 1")
    return r["name"] if r else "Cat6"


@router.post("/api/routing/plan")
def plan(body: RouteIn, me: Principal = Depends(current_principal)):
    if bool(body.source_port_id) == bool(body.new_device):
        raise HTTPException(400, "Entweder einen vorhandenen Quellport oder ein neues Gerät angeben")
    tgt = _port(body.target_port_id)
    if not tgt:
        raise HTTPException(404, "Zielport nicht gefunden")
    if tgt["type"] in THROUGH_TYPES:
        raise HTTPException(400, "Der Zielport muss an einem aktiven Gerät liegen (nicht an Patchfeld oder Dose)")
    if not tgt["site_id"]:
        raise HTTPException(400, "Das Zielgerät hat keine Location – ohne Standort lässt sich nicht routen")
    nd, src_name = body.new_device, ""
    if body.source_port_id:
        sp = _port(body.source_port_id)
        if not sp:
            raise HTTPException(404, "Quellport nicht gefunden")
        if not sp["site_id"]:
            raise HTTPException(400, "Das Quellgerät hat keine Location – ohne Standort lässt sich nicht routen")
        if sp["device_id"] == tgt["device_id"]:
            raise HTTPException(400, "Quelle und Ziel gehören zum selben Gerät")
        src = {"port_id": sp["id"], "location_id": sp["location_id"], "medium": sp["medium"], "label": f"{sp['hostname']}:{sp['name']}"}
        site = sp["site_id"]
    else:
        loc = db.row("SELECT id, site_id FROM locations WHERE id = ?", (nd.location_id,))
        if not loc:
            raise HTTPException(400, "Location für das neue Gerät nicht gefunden")
        if db.row("SELECT 1 AS x FROM devices WHERE hostname = ? COLLATE NOCASE", (nd.hostname.strip(),)):
            raise HTTPException(409, f"Ein Gerät mit dem Hostnamen '{nd.hostname.strip()}' existiert bereits")
        src_name = body.source_port_name.strip() or f"{nd.nic_prefix}1"
        src = {"port_id": None, "location_id": nd.location_id, "medium": nd.medium, "label": f"{nd.hostname.strip()}:{src_name}"}
        site = loc["site_id"]
    if tgt["site_id"] != site:
        raise HTTPException(400, "Quelle und Ziel liegen an verschiedenen Standorten – Autorouting plant nur innerhalb eines Standorts")
    if me.kind != "user" or not me.has_at(site, "planer"):
        raise HTTPException(403, "Für Patchaufträge ist die Rolle „Planer“ an diesem Standort nötig")

    w = routing.World(site, exclude_workorder=body.workorder_id)
    routes = routing.find_routes(w, src, tgt["id"], limit=3)
    out = {"source": src["label"], "target": f"{tgt['hostname']}:{tgt['name']}", "site_id": site, "routes": routes,
           "cable_type": body.cable_type.strip() or auto_cable_type(src["medium"]), "new_device": bool(nd)}
    if not routes:
        why = routing.explain_none(w, src, tgt["id"])
        if body.dry_run:
            return {**out, "dry_run": True, "why": why}
        raise HTTPException(409, why)
    if body.dry_run:
        return {**out, "dry_run": True}

    # ── Auftrag anlegen ──────────────────────────────────────────────────────
    if body.route_index >= len(routes):
        raise HTTPException(400, "Die gewählte Route gibt es nicht (mehr) – bitte neu berechnen")
    chosen = routes[body.route_index]
    ctype = check_cable_type(out["cable_type"])
    cords = chosen["cords"]
    if not cords:
        raise HTTPException(409, "Quelle und Ziel sind bereits durchgängig verbunden – es ist nichts zu planen")
    ports = [p for c in cords for p in (c["a"], c["b"]) if p]
    reservations.check(ports, use_reserved=body.use_reserved, by=me.name, workorder_id=body.workorder_id)
    busy = workorders.port_conflicts(ports)
    if busy:
        raise workorders.conflict_error("port_busy", workorders.busy_message(busy).split(". Alten Patch")[0] + ". Bitte neu berechnen.", busy)
    title = body.workorder_title.strip() or f"Route {src['label']} → {out['target']}"
    device_id, rest = None, cords
    if nd:                                                        # neues Gerät als „geplant“ + Einbau + erstes Patchkabel (Quelle → erstes Ziel)
        first = cords[0]
        groups = [] if nd.model_id else [PortGroup(prefix=nd.nic_prefix, start=1, count=nd.nic_count, medium=nd.medium)]
        res = wizards.device_wizard(DeviceWizardIn(
            hostname=nd.hostname.strip(), type=nd.type, model_id=nd.model_id, vendor=nd.vendor, model=nd.model, height_u=nd.height_u, ports=groups,
            location_id=nd.location_id, rack_position=nd.rack_position, mgmt_ip=nd.mgmt_ip, note=nd.note, status="planned", mode="workorder",
            links=[UplinkIn(port_name=src_name, target_port_id=first["b"], cable_type=ctype, note="Autorouting")],
            workorder_id=body.workorder_id, workorder_title=title, use_reserved=body.use_reserved), me)
        wid, device_id, rest = res["workorder"]["id"], res["device_id"], cords[1:]
    else:
        now = time.time()
        wo = None
        if body.workorder_id:
            wo = workorders._wo_or_404(body.workorder_id, me)
            if wo["status"] not in ("draft", "rework"):
                raise HTTPException(409, "Positionen können nur in Entwürfen oder zurückgewiesenen Aufträgen ergänzt werden")
            workorders._require_role(me, ["planer", "admin"], wo)
        if wo:
            wid = wo["id"]
        else:
            wid = db.execute("""INSERT INTO workorders(number, title, description, status, priority, location_id, note, openplan_project, openplan_task,
                                                       openplan_link, created_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                             (workorders._next_number(), title, f"Autorouting: {src['label']} → {out['target']}", "draft", "normal",
                              src["location_id"], "", "", "", "", me.name, now, now))
    for c in rest:
        workorders._add_item_raw(wid, "connect", port_a_id=c["a"], port_b_id=c["b"], cable_type=ctype, note=f"Autorouting: {c['a_label']} ↔ {c['b_label']}")
    w_row = db.row("SELECT id, number, title FROM workorders WHERE id = ?", (wid,))
    audit.log(me.name, "routing.plan", "workorder", wid, f"{w_row['number']}: {src['label']} → {out['target']} ({chosen['summary']})")
    return {**out, "dry_run": False, "route": chosen, "device_id": device_id,
            "workorder": {"id": w_row["id"], "number": w_row["number"], "title": w_row["title"], "new": not body.workorder_id}}
