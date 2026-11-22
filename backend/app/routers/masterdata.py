"""Standorte, Locations (Gebäude/Etage/Raum/Rack), Geräte und Ports."""
from __future__ import annotations

import json
import re
import sqlite3
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import access, audit, cablelog, db, reservations
from ..access import require_writer
from ..rackmount import check_mount, describe, pending_removal_device_ids, rack_conflicts
from ..auth import Principal, current_principal, require_master_write
from .catalog import check_cable_type
from ..schemas import (CONTAINER_KINDS, DEVICE_STATUS, DEVICE_TYPES, LOCATION_KINDS, PORT_MEDIA, MoveIn, CableIn, DeviceIn,
                       LocationIn, ModelRef, PeerIn, PortBulkIn, PortGroup, PortIn, SiteIn)

router = APIRouter(prefix="/api", tags=["stammdaten"])


def _one_of(value: str, allowed: tuple, label: str) -> str:
    if value not in allowed:
        raise HTTPException(400, f"{label}: '{value}' ist ungültig (erlaubt: {', '.join(allowed)})")
    return value


def _natural_key(name: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name or "")]


def sort_ports(ports: list[dict]) -> list[dict]:
    """Natürliche Sortierung nach Portname (Gi1/0/2 vor Gi1/0/10)."""
    return sorted(ports, key=lambda p: _natural_key(p["name"]))


# ── Standorte ─────────────────────────────────────────────────────────────────

@router.get("/sites")
def list_sites(me: Principal = Depends(current_principal)):
    cl, args = access.sites_clause(me, "s.id")
    return db.rows(f"""SELECT s.*, (SELECT COUNT(*) FROM locations l WHERE l.site_id = s.id) AS locations,
                             (SELECT COUNT(*) FROM devices d JOIN locations l ON l.id = d.location_id WHERE l.site_id = s.id) AS devices
                      FROM sites s {('WHERE ' + cl) if cl else ''} ORDER BY s.code""", tuple(args))


@router.post("/sites", status_code=201)
def create_site(body: SiteIn, me: Principal = Depends(require_master_write)):
    try:
        sid = db.execute("INSERT INTO sites(code, name, address, note) VALUES (?,?,?,?)",
                         (body.code.strip(), body.name.strip(), body.address.strip(), body.note.strip()))
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"Der Standortcode '{body.code}' existiert bereits")
    audit.log(me.name, "site.create", "site", sid, body.code)
    return db.row("SELECT * FROM sites WHERE id = ?", (sid,))


@router.put("/sites/{sid}")
def update_site(sid: int, body: SiteIn, me: Principal = Depends(require_writer)):
    if not db.row("SELECT id FROM sites WHERE id = ?", (sid,)):
        raise HTTPException(404, "Standort nicht gefunden")
    access.require_write(me, sid)
    try:
        db.execute("UPDATE sites SET code=?, name=?, address=?, note=? WHERE id=?",
                   (body.code.strip(), body.name.strip(), body.address.strip(), body.note.strip(), sid))
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"Der Standortcode '{body.code}' existiert bereits")
    audit.log(me.name, "site.update", "site", sid, body.code)
    return db.row("SELECT * FROM sites WHERE id = ?", (sid,))


@router.delete("/sites/{sid}")
def delete_site(sid: int, me: Principal = Depends(require_master_write)):
    s = db.row("SELECT * FROM sites WHERE id = ?", (sid,))
    if not s:
        raise HTTPException(404, "Standort nicht gefunden")
    n = db.row("SELECT COUNT(*) AS n FROM devices d JOIN locations l ON l.id = d.location_id WHERE l.site_id = ?", (sid,))["n"]
    if n:
        raise HTTPException(409, f"Der Standort enthält noch {n} Gerät(e) – diese zuerst verschieben oder löschen")
    db.execute("DELETE FROM sites WHERE id = ?", (sid,))
    audit.log(me.name, "site.delete", "site", sid, s["code"])
    return {"ok": True}


# ── Locations ─────────────────────────────────────────────────────────────────

def location_path(location_id: Optional[int]) -> str:
    """„Standort / Gebäude / Raum / Rack“ für eine Location."""
    if not location_id:
        return ""
    parts: list[str] = []
    cur = db.row("SELECT * FROM locations WHERE id = ?", (location_id,))
    site = db.row("SELECT code FROM sites WHERE id = ?", (cur["site_id"],)) if cur else None
    guard = 0
    while cur and guard < 20:
        parts.append(cur["name"])
        cur = db.row("SELECT * FROM locations WHERE id = ?", (cur["parent_id"],)) if cur["parent_id"] else None
        guard += 1
    if site:
        parts.append(site["code"])
    return " / ".join(reversed(parts))


def _check_location(body: LocationIn, own_id: Optional[int] = None) -> None:
    _one_of(body.kind, LOCATION_KINDS, "Art")
    if not db.row("SELECT id FROM sites WHERE id = ?", (body.site_id,)):
        raise HTTPException(400, "Standort nicht gefunden")
    if body.kind not in CONTAINER_KINDS and body.rack_units is not None:
        raise HTTPException(400, "Höheneinheiten gibt es nur bei Racks, Wandgehäusen und Schaltschränken")
    if body.parent_id:
        p = db.row("SELECT * FROM locations WHERE id = ?", (body.parent_id,))
        if not p or p["site_id"] != body.site_id:
            raise HTTPException(400, "Die übergeordnete Location muss zum selben Standort gehören")
        if own_id:                                  # Zyklus verhindern
            cur, guard = p, 0
            while cur and guard < 20:
                if cur["id"] == own_id:
                    raise HTTPException(400, "Eine Location kann nicht in sich selbst enthalten sein")
                cur = db.row("SELECT * FROM locations WHERE id = ?", (cur["parent_id"],)) if cur["parent_id"] else None
                guard += 1


@router.get("/locations")
def list_locations(site_id: Optional[int] = None, me: Principal = Depends(current_principal)):
    where, args = [], []
    if site_id:
        where.append("l.site_id = ?"); args.append(site_id)
    cl, a2 = access.sites_clause(me, "l.site_id")
    if cl:
        where.append(cl); args += a2
    rows = db.rows("SELECT l.*, (SELECT COUNT(*) FROM devices d WHERE d.location_id = l.id) AS devices FROM locations l"
                   + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY l.site_id, l.parent_id, l.name", tuple(args))
    for r in rows:
        r["path"] = location_path(r["id"])
    return rows


@router.post("/locations", status_code=201)
def create_location(body: LocationIn, me: Principal = Depends(require_writer)):
    access.require_write(me, body.site_id)
    _check_location(body)
    lid = db.execute("INSERT INTO locations(site_id, parent_id, kind, name, rack_units, note, ident) VALUES (?,?,?,?,?,?,?)",
                     (body.site_id, body.parent_id, body.kind, body.name.strip(), body.rack_units, body.note.strip(), body.ident.strip()))
    audit.log(me.name, "location.create", "location", lid, f"{body.kind} {body.name}")
    return {**db.row("SELECT * FROM locations WHERE id = ?", (lid,)), "path": location_path(lid)}


@router.put("/locations/{lid}")
def update_location(lid: int, body: LocationIn, me: Principal = Depends(require_writer)):
    cur = db.row("SELECT * FROM locations WHERE id = ?", (lid,))
    if not cur:
        raise HTTPException(404, "Location nicht gefunden")
    access.require_write(me, cur["site_id"])
    access.require_write(me, body.site_id)
    _check_location(body, own_id=lid)
    db.execute("UPDATE locations SET site_id=?, parent_id=?, kind=?, name=?, rack_units=?, note=?, ident=? WHERE id=?",
               (body.site_id, body.parent_id, body.kind, body.name.strip(), body.rack_units, body.note.strip(), body.ident.strip(), lid))
    audit.log(me.name, "location.update", "location", lid, body.name)
    return {**db.row("SELECT * FROM locations WHERE id = ?", (lid,)), "path": location_path(lid)}


@router.post("/locations/{lid}/move")
def move_location(lid: int, body: MoveIn, me: Principal = Depends(require_writer)):
    """Verlegt eine Location (z. B. eine mobile Maschine/ein Lader) samt allem darunter – Gehäuse und Geräte – an einen anderen
    Standort bzw. unter eine andere Location. Beide Standorte müssen für dich beschreibbar sein."""
    loc = db.row("SELECT * FROM locations WHERE id = ?", (lid,))
    if not loc:
        raise HTTPException(404, "Location nicht gefunden")
    access.require_write(me, loc["site_id"])
    access.require_write(me, body.site_id)
    new_site = db.row("SELECT * FROM sites WHERE id = ?", (body.site_id,))
    if not new_site:
        raise HTTPException(400, "Standort nicht gefunden")
    if body.parent_id:
        parent = db.row("SELECT * FROM locations WHERE id = ?", (body.parent_id,))
        if not parent or parent["site_id"] != body.site_id:
            raise HTTPException(400, "Die übergeordnete Location muss zum Zielstandort gehören")
        if parent["kind"] in CONTAINER_KINDS:
            raise HTTPException(400, "Racks, Wandgehäuse und Schaltschränke nehmen nur Geräte auf")
        subtree = _location_and_children(lid)
        if parent["id"] in subtree:
            raise HTTPException(400, "Eine Location kann nicht in sich selbst oder ihre Unterstruktur verlegt werden")
    old_path = location_path(lid)
    subtree = _location_and_children(lid)
    db.execute(f"UPDATE locations SET site_id = ? WHERE id IN ({','.join('?' * len(subtree))})", (body.site_id, *subtree))
    db.execute("UPDATE locations SET parent_id = ? WHERE id = ?", (body.parent_id, lid))
    new_path = location_path(lid)
    audit.log(me.name, "location.move", "location", lid, f"{old_path} -> {new_path} ({len(subtree)} Locations, "
              f"{db.row('SELECT COUNT(*) AS n FROM devices WHERE location_id IN (%s)' % ','.join('?' * len(subtree)), tuple(subtree))['n']} Geräte)")
    return {**db.row("SELECT * FROM locations WHERE id = ?", (lid,)), "path": new_path, "old_path": old_path}


@router.delete("/locations/{lid}")
def delete_location(lid: int, me: Principal = Depends(require_writer)):
    loc = db.row("SELECT * FROM locations WHERE id = ?", (lid,))
    if not loc:
        raise HTTPException(404, "Location nicht gefunden")
    access.require_write(me, loc["site_id"])
    if db.row("SELECT COUNT(*) AS n FROM locations WHERE parent_id = ?", (lid,))["n"]:
        raise HTTPException(409, "Die Location enthält noch untergeordnete Locations")
    n = db.row("SELECT COUNT(*) AS n FROM devices WHERE location_id = ?", (lid,))["n"]
    if n:
        raise HTTPException(409, f"Die Location enthält noch {n} Gerät(e)")
    db.execute("DELETE FROM locations WHERE id = ?", (lid,))
    audit.log(me.name, "location.delete", "location", lid, loc["name"])
    return {"ok": True}


# ── Geräte ────────────────────────────────────────────────────────────────────

def _location_and_children(location_id: int) -> list[int]:
    ids, todo = [], [location_id]
    while todo:
        cur = todo.pop()
        ids.append(cur)
        todo += [r["id"] for r in db.rows("SELECT id FROM locations WHERE parent_id = ?", (cur,))]
    return ids


def _device_out(d: dict) -> dict:
    d["location_path"] = location_path(d["location_id"])
    d["port_count"] = db.row("SELECT COUNT(*) AS n FROM ports WHERE device_id = ?", (d["id"],))["n"]
    return d


@router.get("/devices")
def list_devices(
    q: str = "", type: str = "", status: str = "", source: str = "",
    site_id: Optional[int] = None, location_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
    me: Principal = Depends(current_principal),
):
    where, args = [], []
    cl, a2 = access.device_clause(me, "d")
    if cl:
        where.append(cl); args += a2
    if q.strip():
        like = f"%{q.strip()}%"
        where.append("(d.hostname LIKE ? OR d.model LIKE ? OR d.serial LIKE ? OR d.mgmt_ip LIKE ? OR d.note LIKE ?)")
        args += [like] * 5
    for col, val in (("type", type), ("status", status), ("source", source)):
        if val:
            where.append(f"d.{col} = ?"); args.append(val)
    if location_id:
        ids = _location_and_children(location_id)
        where.append(f"d.location_id IN ({','.join('?' * len(ids))})"); args += ids
    elif site_id:
        where.append("d.location_id IN (SELECT id FROM locations WHERE site_id = ?)"); args.append(site_id)
    w = (" WHERE " + " AND ".join(where)) if where else ""
    total = db.row(f"SELECT COUNT(*) AS n FROM devices d{w}", tuple(args))["n"]
    items = db.rows(f"SELECT d.* FROM devices d{w} ORDER BY d.hostname COLLATE NOCASE LIMIT ? OFFSET ?", (*args, limit, offset))
    return {"total": total, "items": [_device_out(d) for d in items]}


def _model_or_400(model_id: Optional[int]) -> Optional[dict]:
    if not model_id:
        return None
    m = db.row("SELECT * FROM device_models WHERE id = ?", (model_id,))
    if not m:
        raise HTTPException(400, "Katalogmodell nicht gefunden")
    return m


def _check_device(body: DeviceIn, own_id: Optional[int] = None, ignore_ids: tuple = ()) -> None:
    _one_of(body.type, DEVICE_TYPES, "Typ")
    _one_of(body.status, DEVICE_STATUS, "Status")
    body.side_slot = check_mount(body.orientation, body.mount_side, body.side_slot)
    loc = db.row("SELECT * FROM locations WHERE id = ?", (body.location_id,)) if body.location_id else None
    if body.location_id and not loc:
        raise HTTPException(400, "Location nicht gefunden")
    in_container = bool(loc and loc["kind"] in CONTAINER_KINDS)
    if body.orientation == "vertical" and not (loc and loc["kind"] == "rack"):
        raise HTTPException(400, "Hochkant eingebaute Geräte (z. B. PDU) brauchen ein Rack (Seitenkanäle gibt es nur dort)")
    if body.orientation == "din_rail" and not loc:
        raise HTTPException(400, "Für die Montage auf Hutschiene/Montageplatte ist eine Location (Schaltschrank, Maschine …) nötig")
    if body.rack_position:
        if not loc:
            raise HTTPException(400, "Eine HE-Position braucht eine Location (Rack)")
        if not in_container:
            raise HTTPException(400, "Eine HE-Position ist nur in einem Rack, Wandgehäuse oder Schaltschrank möglich")
        top = body.rack_position + body.height_u - 1
        if loc["rack_units"] and top > loc["rack_units"]:
            raise HTTPException(400, f"Das Gerät passt nicht ins Rack ({loc['rack_units']} HE): belegt HE {body.rack_position}–{top}")
    if in_container:
        hit = rack_conflicts(loc, body.orientation, body.mount_side, body.side_slot, body.rack_position, body.height_u, own_id, ignore_ids)
        if hit:
            o = hit[0]
            if body.orientation == "vertical":
                raise HTTPException(409, f"Der Seitenkanal ist an dieser Stelle belegt durch {describe(o)}")
            raise HTTPException(409, f"HE {body.rack_position}–{body.rack_position + body.height_u - 1} überschneidet sich mit {describe(o)}")


@router.get("/devices/{did}")
def get_device(did: int, me: Principal = Depends(current_principal)):
    d = db.row("SELECT * FROM devices WHERE id = ?", (did,))
    if not d:
        raise HTTPException(404, "Gerät nicht gefunden")
    access.require_read(me, access.site_of_location(d["location_id"]), "Gerät")
    d = _device_out(d)
    d["ports"] = sort_ports(_ports_with_cables(db.rows("SELECT * FROM ports WHERE device_id = ?", (did,))))
    return d


@router.post("/devices", status_code=201)
def create_device(body: DeviceIn, me: Principal = Depends(require_writer)):
    access.require_write(me, access.site_of_location(body.location_id))
    _check_device(body)
    model = _model_or_400(body.model_id)
    vendor = body.vendor.strip() or (model["vendor"] if model else "")
    model_name = body.model.strip() or (model["model"] if model else "")
    now = time.time()
    try:
        did = db.execute(
            """INSERT INTO devices(hostname, type, vendor, model, serial, mgmt_ip, location_id, rack_position, height_u, status,
                                   source, note, model_id, mount_side, orientation, side_slot, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (body.hostname.strip(), body.type, vendor, model_name, body.serial.strip(), body.mgmt_ip.strip(),
             body.location_id, body.rack_position, body.height_u, body.status, "manual", body.note.strip(),
             body.model_id, body.mount_side, body.orientation, body.side_slot, now, now))
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"Ein Gerät mit dem Hostnamen '{body.hostname}' existiert bereits")
    audit.log(me.name, "device.create", "device", did, body.hostname)
    if model and body.apply_model_ports:
        created, _skipped = _apply_model_ports(did, model)
        audit.log(me.name, "port.from_model", "device", did, f"{model['vendor']} {model['model']}: {created} angelegt")
    return _device_out(db.row("SELECT * FROM devices WHERE id = ?", (did,)))


@router.put("/devices/{did}")
def update_device(did: int, body: DeviceIn, me: Principal = Depends(require_writer)):
    cur = db.row("SELECT * FROM devices WHERE id = ?", (did,))
    if not cur:
        raise HTTPException(404, "Gerät nicht gefunden")
    access.require_write(me, access.site_of_location(cur["location_id"]))           # bisheriger Standort
    access.require_write(me, access.site_of_location(body.location_id))              # Ziel-Standort (Verschieben)
    for f in ("mount_side", "orientation", "side_slot"):                      # nicht mitgesendete Felder bleiben unverändert
        if f not in body.model_fields_set:
            setattr(body, f, cur[f])
    _check_device(body, own_id=did)
    _model_or_400(body.model_id)
    if "model_id" in body.model_fields_set:
        model_id = body.model_id
    else:
        model_id = db.row("SELECT model_id FROM devices WHERE id = ?", (did,))["model_id"]
    try:
        db.execute(
            """UPDATE devices SET hostname=?, type=?, vendor=?, model=?, serial=?, mgmt_ip=?, location_id=?, rack_position=?,
                                  height_u=?, status=?, note=?, model_id=?, mount_side=?, orientation=?, side_slot=?, updated_at=? WHERE id=?""",
            (body.hostname.strip(), body.type, body.vendor.strip(), body.model.strip(), body.serial.strip(), body.mgmt_ip.strip(),
             body.location_id, body.rack_position, body.height_u, body.status, body.note.strip(), model_id, body.mount_side, body.orientation, body.side_slot, time.time(), did))
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"Ein Gerät mit dem Hostnamen '{body.hostname}' existiert bereits")
    audit.log(me.name, "device.update", "device", did, body.hostname)
    return _device_out(db.row("SELECT * FROM devices WHERE id = ?", (did,)))


@router.delete("/devices/{did}")
def delete_device(did: int, me: Principal = Depends(require_writer)):
    d = db.row("SELECT * FROM devices WHERE id = ?", (did,))
    if not d:
        raise HTTPException(404, "Gerät nicht gefunden")
    access.require_write(me, access.site_of_location(d["location_id"]))
    db.execute("DELETE FROM devices WHERE id = ?", (did,))          # Ports werden mit gelöscht (ON DELETE CASCADE)
    audit.log(me.name, "device.delete", "device", did, d["hostname"])
    return {"ok": True}


# ── Ports ─────────────────────────────────────────────────────────────────────

def _check_port(body: PortIn) -> None:
    _one_of(body.medium, PORT_MEDIA, "Medium")


def _port_with_cable(port: dict) -> dict:
    """Reichert einen Port-Dict mit Kabel-Info und Peer-Name an."""
    out = dict(port)
    if port.get("peer_port_id"):
        peer = db.row("SELECT name FROM ports WHERE id = ?", (port["peer_port_id"],))
        out["peer_port_name"] = peer["name"] if peer else None
    else:
        out["peer_port_name"] = None
    cable = db.row(
        """SELECT c.*,
                  CASE WHEN c.port_a_id = :pid THEN c.port_b_id ELSE c.port_a_id END AS other_port_id
           FROM cables c WHERE c.port_a_id = :pid OR c.port_b_id = :pid""",
        {"pid": port["id"]}
    )
    if cable:
        other = db.row(
            """SELECT p.id, p.name, p.device_id, d.hostname
               FROM ports p JOIN devices d ON d.id = p.device_id WHERE p.id = ?""",
            (cable["other_port_id"],)
        )
        out["cable"] = {
            "id": cable["id"],
            "cable_label": cable["cable_label"],
            "cable_type": cable["cable_type"],
            "fiber_count": cable["fiber_count"],
            "length_m": cable["length_m"],
            "color": cable["color"],
            "installed_at": cable["installed_at"],
            "measurement_ref": cable["measurement_ref"],
            "measurement_ok": None if cable["measurement_ok"] is None else bool(cable["measurement_ok"]),
            "note": cable["note"],
            "port_id": other["id"],
            "port_name": other["name"],
            "device_id": other["device_id"],
            "device_hostname": other["hostname"],
        }
    else:
        out["cable"] = None
    r = reservations.active([port["id"]]).get(port["id"])
    out["reservation"] = ({"id": r["id"], "purpose": r["purpose"], "reserved_by": r["reserved_by"], "until": r["until"],
                           "workorder": {"id": r["workorder_id"], "number": r["wo_number"]} if r["workorder_id"] else None} if r else None)
    out["planned"] = reservations.planned([port["id"]]).get(port["id"])
    return out


def _ports_with_cables(ports: list[dict]) -> list[dict]:
    return [_port_with_cable(p) for p in ports]


@router.get("/ports/{pid}/path")
def port_path(pid: int, at: Optional[str] = None, me: Principal = Depends(current_principal)):
    """Vollständiger Pfad ab diesem Port (beide Richtungen, über Patchfelder/Dosen) mit Kabeldaten, Planungen und LLDP-Abgleich der Enden."""
    if not db.row("SELECT id FROM ports WHERE id = ?", (pid,)):
        raise HTTPException(404, "Port nicht gefunden")
    access.require_read(me, access.site_of_port(pid), "Port")
    from .. import pathtrace
    from .history import _parse_at
    return pathtrace.trace(pid, me, _parse_at(at))


@router.get("/devices/{did}/ports")
def list_ports(did: int, me: Principal = Depends(current_principal)):
    if not db.row("SELECT id FROM devices WHERE id = ?", (did,)):
        raise HTTPException(404, "Gerät nicht gefunden")
    access.require_read(me, access.site_of_device(did), "Gerät")
    return sort_ports(_ports_with_cables(db.rows("SELECT * FROM ports WHERE device_id = ?", (did,))))


@router.post("/devices/{did}/ports", status_code=201)
def create_port(did: int, body: PortIn, me: Principal = Depends(require_writer)):
    access.require_write(me, access.site_of_device(did))
    if not db.row("SELECT id FROM devices WHERE id = ?", (did,)):
        raise HTTPException(404, "Gerät nicht gefunden")
    _check_port(body)
    try:
        pid = db.execute(
            """INSERT INTO ports(device_id, name, idx, medium, speed_mbps, description, admin_status, oper_status)
               VALUES (?,?,?,?,?,?,?,?)""",
            (did, body.name.strip(), body.idx, body.medium, body.speed_mbps, body.description.strip(),
             body.admin_status, body.oper_status))
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"Der Port '{body.name}' existiert an diesem Gerät bereits")
    audit.log(me.name, "port.create", "port", pid, f"device {did}: {body.name}")
    return _port_with_cable(db.row("SELECT * FROM ports WHERE id = ?", (pid,)))


def _create_port_group(did: int, g) -> tuple[int, int]:
    """Legt die Ports einer Gruppe (PortBulkIn oder PortGroup) an. dual=True erzeugt je einen Vorder- (<prefix><n>) und
    Rückseiten-Port (<prefix><n><back_suffix>) und setzt automatisch den Peer. Liefert (angelegt, übersprungen)."""
    created = skipped = 0
    for i in range(g.start, g.start + g.count):
        front_name = f"{g.prefix}{i}"
        try:
            front_id = db.execute("INSERT INTO ports(device_id, name, idx, medium, speed_mbps) VALUES (?,?,?,?,?)",
                                  (did, front_name, i, g.medium, g.speed_mbps))
            created += 1
        except sqlite3.IntegrityError:
            front_id = None
            skipped += 1
        if g.dual:
            back_name = f"{g.prefix}{i}{g.back_suffix}"
            try:
                back_id = db.execute("INSERT INTO ports(device_id, name, idx, medium, speed_mbps) VALUES (?,?,?,?,?)",
                                     (did, back_name, i, g.medium, g.speed_mbps))
                created += 1
                if front_id:
                    db.execute("UPDATE ports SET peer_port_id = ? WHERE id = ?", (back_id, front_id))
                    db.execute("UPDATE ports SET peer_port_id = ? WHERE id = ?", (front_id, back_id))
            except sqlite3.IntegrityError:
                skipped += 1
    return created, skipped


@router.post("/devices/{did}/ports/bulk", status_code=201)
def create_ports_bulk(did: int, body: PortBulkIn, me: Principal = Depends(require_writer)):
    access.require_write(me, access.site_of_device(did))
    """Legt count Ports an (siehe _create_port_group)."""
    if not db.row("SELECT id FROM devices WHERE id = ?", (did,)):
        raise HTTPException(404, "Gerät nicht gefunden")
    _one_of(body.medium, PORT_MEDIA, "Medium")
    created, skipped = _create_port_group(did, body)
    audit.log(me.name, "port.bulk_create", "device", did,
              f"{body.prefix}{body.start}..: {created} angelegt, {skipped} übersprungen" + (" (dual)" if body.dual else ""))
    return {"created": created, "skipped": skipped}


def _apply_model_ports(did: int, model: dict) -> tuple[int, int]:
    created = skipped = 0
    for g in json.loads(model["ports"] or "[]"):
        c, s = _create_port_group(did, PortGroup(**g))
        created += c; skipped += s
    return created, skipped


@router.post("/devices/{did}/ports/from-model", status_code=201)
def create_ports_from_model(did: int, body: ModelRef, me: Principal = Depends(require_writer)):
    access.require_write(me, access.site_of_device(did))
    """Erzeugt die Ports aus der Vorlage eines Katalogmodells (bereits vorhandene Portnamen werden übersprungen)."""
    if not db.row("SELECT id FROM devices WHERE id = ?", (did,)):
        raise HTTPException(404, "Gerät nicht gefunden")
    model = db.row("SELECT * FROM device_models WHERE id = ?", (body.model_id,))
    if not model:
        raise HTTPException(404, "Modell nicht gefunden")
    created, skipped = _apply_model_ports(did, model)
    audit.log(me.name, "port.from_model", "device", did, f"{model['vendor']} {model['model']}: {created} angelegt, {skipped} übersprungen")
    return {"created": created, "skipped": skipped}


@router.put("/ports/{pid}")
def update_port(pid: int, body: PortIn, me: Principal = Depends(require_writer)):
    p = db.row("SELECT * FROM ports WHERE id = ?", (pid,))
    if not p:
        raise HTTPException(404, "Port nicht gefunden")
    access.require_write(me, access.site_of_device(p["device_id"]))
    _check_port(body)
    try:
        db.execute(
            """UPDATE ports SET name=?, idx=?, medium=?, speed_mbps=?, description=?, admin_status=?, oper_status=? WHERE id=?""",
            (body.name.strip(), body.idx, body.medium, body.speed_mbps, body.description.strip(),
             body.admin_status, body.oper_status, pid))
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"Der Port '{body.name}' existiert an diesem Gerät bereits")
    audit.log(me.name, "port.update", "port", pid, body.name)
    return _port_with_cable(db.row("SELECT * FROM ports WHERE id = ?", (pid,)))


@router.delete("/ports/{pid}")
def delete_port(pid: int, me: Principal = Depends(require_writer)):
    p = db.row("SELECT * FROM ports WHERE id = ?", (pid,))
    if not p:
        raise HTTPException(404, "Port nicht gefunden")
    access.require_write(me, access.site_of_device(p["device_id"]))
    db.execute("DELETE FROM ports WHERE id = ?", (pid,))
    audit.log(me.name, "port.delete", "port", pid, p["name"])
    return {"ok": True}


@router.put("/ports/{pid}/peer")
def set_peer(pid: int, body: PeerIn, me: Principal = Depends(require_writer)):
    """Durchschleifung (z. B. Vorder-/Rückseite eines Patchfelds): symmetrisch, nur innerhalb desselben Geräts."""
    p = db.row("SELECT * FROM ports WHERE id = ?", (pid,))
    if not p:
        raise HTTPException(404, "Port nicht gefunden")
    access.require_write(me, access.site_of_device(p["device_id"]))
    if p["peer_port_id"]:                                                   # bisherige Verknüpfung lösen
        db.execute("UPDATE ports SET peer_port_id = NULL WHERE id IN (?, ?)", (pid, p["peer_port_id"]))
    if body.peer_port_id:
        q = db.row("SELECT * FROM ports WHERE id = ?", (body.peer_port_id,))
        if not q:
            raise HTTPException(404, "Gegenport nicht gefunden")
        if q["id"] == pid:
            raise HTTPException(400, "Ein Port kann nicht mit sich selbst durchgeschleift werden")
        if q["device_id"] != p["device_id"]:
            raise HTTPException(400, "Durchgeschleifte Ports müssen zum selben Gerät gehören")
        if q["peer_port_id"]:
            db.execute("UPDATE ports SET peer_port_id = NULL WHERE id = ?", (q["peer_port_id"],))
        db.execute("UPDATE ports SET peer_port_id = ? WHERE id = ?", (q["id"], pid))
        db.execute("UPDATE ports SET peer_port_id = ? WHERE id = ?", (pid, q["id"]))
    audit.log(me.name, "port.peer", "port", pid, f"-> {body.peer_port_id}")
    return _port_with_cable(db.row("SELECT * FROM ports WHERE id = ?", (pid,)))


@router.get("/cables")
def list_cables(
    cable_type: Optional[str] = None,
    measurement_ok: Optional[str] = None,
    q: Optional[str] = None,
    me: Principal = Depends(current_principal),
):
    """Alle Kabel (für Bereichs-Benutzer: Kabel, von denen mindestens ein Ende im eigenen Standort liegt), optional gefiltert."""
    where, args = [], []
    ca, aa = access.device_clause(me, "da")
    cb, ab = access.device_clause(me, "db_")
    if ca:
        where.append(f"({ca} OR {cb})"); args += aa + ab
    if cable_type:
        where.append("c.cable_type = ?"); args.append(cable_type)
    if measurement_ok == "yes":
        where.append("c.measurement_ok = 1")
    elif measurement_ok == "no":
        where.append("c.measurement_ok = 0")
    elif measurement_ok == "none":
        where.append("c.measurement_ok IS NULL")
    if q:
        where.append("(c.cable_label LIKE ? OR c.note LIKE ? OR c.measurement_ref LIKE ?)")
        args += [f"%{q}%", f"%{q}%", f"%{q}%"]
    w = ("WHERE " + " AND ".join(where)) if where else ""
    rows = db.rows(
        f"""SELECT c.*,
                   pa.name AS port_a_name, da.hostname AS device_a_hostname, da.id AS device_a_id,
                   pb.name AS port_b_name, db_.hostname AS device_b_hostname, db_.id AS device_b_id
            FROM cables c
            JOIN ports pa ON pa.id = c.port_a_id
            JOIN devices da ON da.id = pa.device_id
            JOIN ports pb ON pb.id = c.port_b_id
            JOIN devices db_ ON db_.id = pb.device_id
            {w}
            ORDER BY c.cable_label COLLATE NOCASE, c.id""",
        tuple(args),
    )
    return [_cable_out(r) for r in rows]


def _cable_out(c: dict) -> dict:
    return {
        "id": c["id"],
        "cable_label": c["cable_label"],
        "cable_type": c["cable_type"],
        "fiber_count": c["fiber_count"],
        "length_m": c["length_m"],
        "color": c["color"],
        "installed_at": c["installed_at"],
        "measurement_ref": c["measurement_ref"],
        "measurement_ok": None if c["measurement_ok"] is None else bool(c["measurement_ok"]),
        "note": c["note"],
        "created_by": c["created_by"],
        "created_at": c["created_at"],
        "port_a": {"id": c["port_a_id"], "name": c["port_a_name"],
                   "device_id": c["device_a_id"], "device_hostname": c["device_a_hostname"]},
        "port_b": {"id": c["port_b_id"], "name": c["port_b_name"],
                   "device_id": c["device_b_id"], "device_hostname": c["device_b_hostname"]},
        "workorder_id": c.get("workorder_id"),
    }


@router.put("/cables/{cid}")
def update_cable(cid: int, body: CableIn, me: Principal = Depends(require_writer)):
    """Kabelattribute aktualisieren (ohne die Port-Verbindung zu ändern)."""
    c = db.row("SELECT * FROM cables WHERE id = ?", (cid,))
    if not c:
        raise HTTPException(404, "Kabel nicht gefunden")
    if not (access.can_write_site(me, access.site_of_port(c["port_a_id"])) or access.can_write_site(me, access.site_of_port(c["port_b_id"]))):
        raise HTTPException(403, "Keine Berechtigung für diesen Standort")           # eines der beiden Enden genügt
    body.cable_type = check_cable_type(body.cable_type)
    db.execute(
        """UPDATE cables SET cable_label=?, cable_type=?, fiber_count=?, length_m=?, color=?,
                             installed_at=?, measurement_ref=?, measurement_ok=?, note=? WHERE id=?""",
        (body.cable_label.strip(), body.cable_type, body.fiber_count, body.length_m,
         body.color.strip(), body.installed_at, body.measurement_ref.strip(),
         None if body.measurement_ok is None else int(body.measurement_ok),
         body.note.strip(), cid),
    )
    audit.log(me.name, "cable.update", "cable", cid, body.cable_label)
    row = db.row(
        """SELECT c.*,
                  pa.name AS port_a_name, da.hostname AS device_a_hostname, da.id AS device_a_id,
                  pb.name AS port_b_name, db_.hostname AS device_b_hostname, db_.id AS device_b_id
           FROM cables c
           JOIN ports pa ON pa.id = c.port_a_id JOIN devices da ON da.id = pa.device_id
           JOIN ports pb ON pb.id = c.port_b_id JOIN devices db_ ON db_.id = pb.device_id
           WHERE c.id = ?""", (cid,))
    return _cable_out(row)


@router.put("/ports/{pid}/cable")
def set_cable(pid: int, body: CableIn, me: Principal = Depends(require_writer)):
    """Verbindet zwei Ports mit einem Kabel (symmetrisch). port_b_id=None löst die Verbindung."""
    p = db.row("SELECT * FROM ports WHERE id = ?", (pid,))
    if not p:
        raise HTTPException(404, "Port nicht gefunden")
    access.require_write(me, access.site_of_device(p["device_id"]))
    if body.port_b_id:
        access.require_write(me, access.site_of_port(body.port_b_id))              # beide Enden müssen im eigenen Bereich liegen
    body.cable_type = check_cable_type(body.cable_type)
    if body.port_b_id:
        reservations.check([pid, body.port_b_id], use_reserved=body.use_reserved, by=me.name)
    cablelog.remove_at_ports([pid], by=me.name, reason="manual")
    if body.port_b_id:
        q = db.row("SELECT * FROM ports WHERE id = ?", (body.port_b_id,))
        if not q:
            raise HTTPException(404, "Zielport nicht gefunden")
        if q["id"] == pid:
            raise HTTPException(400, "Ein Port kann nicht mit sich selbst verbunden werden")
        cablelog.remove_at_ports([q["id"]], by=me.name, reason="manual")
        a, b = (pid, q["id"]) if pid < q["id"] else (q["id"], pid)
        db.execute(
            """INSERT INTO cables(port_a_id, port_b_id, cable_label, cable_type, fiber_count, length_m,
                                  color, installed_at, measurement_ref, measurement_ok, note, created_by, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (a, b, body.cable_label.strip(), body.cable_type, body.fiber_count, body.length_m,
             body.color.strip(), body.installed_at,
             body.measurement_ref.strip(),
             None if body.measurement_ok is None else int(body.measurement_ok),
             body.note.strip(), me.name, time.time()),
        )
    audit.log(me.name, "cable.set", "port", pid, f"-> {body.port_b_id} [{body.cable_label}]")
    return _port_with_cable(db.row("SELECT * FROM ports WHERE id = ?", (pid,)))
