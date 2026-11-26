"""Assistenten: mehrstufige Anlage-Vorgänge, die das Frontend in einem Aufruf (mit Vorschau) auslöst."""
from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from .. import access, audit, cablelog, db, portcfg, reservations, workplace
from ..access import require_writer
from ..auth import Principal, current_principal
from ..schemas import CONTAINER_KINDS, DEVICE_TYPES, PASSIVE_TYPES, BulkCablesIn, BulkParseIn, CableWizardIn, PortListSpec, WorkplaceIn, DeviceIn, DeviceWizardIn, PortGroup, SiteWizardIn
from .. import rackmount
from . import masterdata, workorders
from .catalog import MAX_TEMPLATE_PORTS, check_cable_type

router = APIRouter(prefix="/api/wizards", tags=["assistenten"])

# Ebene: Kinder müssen tiefer liegen als ihre Eltern. Anlagen/Maschinen und mobile Maschinen stehen in Räumen/Gebäuden/am Standort,
# Racks, Wandgehäuse und Schaltschränke darin oder direkt im Raum.
RANK = {"building": 0, "floor": 1, "room": 2, "machine": 3, "vehicle": 3, "rack": 4, "wallrack": 4, "cabinet": 4}
LABEL = {"building": "Gebäude", "floor": "Etage", "room": "Raum", "machine": "Anlage/Maschine", "vehicle": "Mobile Maschine",
         "rack": "Rack", "wallrack": "Wandgehäuse", "cabinet": "Schaltschrank"}
DEFAULT_UNITS = {"rack": 42, "wallrack": 12, "cabinet": None}       # Vorgabe-HE je Art (Schaltschrank: keine HE-Teilung)
MAX_NODES = 500
DEFAULT_RACK_UNITS = 42


def _flatten(nodes, parent_rank: int, parent_path: str, existing: set[str], out: list[dict], depth: int = 0) -> None:
    """Prüft den Strukturbaum und macht daraus eine flache Liste (Eltern vor Kindern)."""
    seen: set[str] = set(existing)
    for n in nodes:
        name = n.name.strip()
        if not name:
            raise HTTPException(400, "Jede Location braucht einen Namen")
        if n.kind not in RANK:
            raise HTTPException(400, f"Art '{n.kind}' ist ungültig (erlaubt: {', '.join(RANK)})")
        if RANK[n.kind] <= parent_rank:
            where = parent_path or "dem Standort"
            raise HTTPException(400, f"{LABEL[n.kind]} „{name}“ kann nicht unter {where} liegen "
                                     f"(Reihenfolge: Gebäude → Etage → Raum → Rack)")
        if name.lower() in seen:
            raise HTTPException(400, f"„{name}“ kommt unter {parent_path or 'dem Standort'} doppelt vor")
        seen.add(name.lower())
        if n.kind in CONTAINER_KINDS:
            if n.children:
                raise HTTPException(400, f"{LABEL[n.kind]} „{name}“ kann keine Unterstruktur haben")
            units = n.rack_units or DEFAULT_UNITS.get(n.kind)
        else:
            if n.rack_units is not None:
                raise HTTPException(400, "Höheneinheiten gibt es nur bei Racks, Wandgehäusen und Schaltschränken")
            units = None
        path = f"{parent_path} / {name}" if parent_path else name
        out.append({"kind": n.kind, "name": name, "rack_units": units, "note": n.note.strip(), "path": path,
                    "depth": depth, "node": n})
        if len(out) > MAX_NODES:
            raise HTTPException(400, f"Zu viele Locations auf einmal (höchstens {MAX_NODES})")
        _flatten(n.children, RANK[n.kind], path, set(), out, depth + 1)


@router.post("/site")
def site_wizard(body: SiteWizardIn, me: Principal = Depends(require_writer)):
    """Legt einen Standort samt Gebäude-/Etagen-/Raum-/Rack-Struktur in einem Schritt an – oder ergänzt die Struktur
    eines vorhandenen Standorts (site_id, optional unter parent_id). dry_run=True prüft nur und liefert die Vorschau."""
    # Ziel bestimmen
    if body.site_id:
        site = db.row("SELECT * FROM sites WHERE id = ?", (body.site_id,))
        if not site:
            raise HTTPException(404, "Standort nicht gefunden")
        new_site = False
        access.require_write(me, site["id"])
    elif body.site:
        if not me.can_write_master:
            raise HTTPException(403, "Neue Standorte legen nur globale Administratoren an")
        code = body.site.code.strip()
        if not code or not body.site.name.strip():
            raise HTTPException(400, "Standort braucht Code und Namen")
        if db.row("SELECT id FROM sites WHERE code = ? COLLATE NOCASE", (code,)):
            raise HTTPException(409, f"Der Standortcode '{code}' existiert bereits")
        site, new_site = {"id": None, "code": code, "name": body.site.name.strip()}, True
    else:
        raise HTTPException(400, "Entweder site_id (vorhandener Standort) oder site (neuer Standort) angeben")

    parent = None
    parent_rank, parent_path, existing = -1, site["code"], set()
    if body.parent_id:
        if new_site:
            raise HTTPException(400, "parent_id gibt es nur bei einem vorhandenen Standort")
        parent = db.row("SELECT * FROM locations WHERE id = ?", (body.parent_id,))
        if not parent or parent["site_id"] != site["id"]:
            raise HTTPException(400, "Die übergeordnete Location muss zum selben Standort gehören")
        parent_rank = RANK.get(parent["kind"], 99)
        from .masterdata import location_path
        parent_path = location_path(parent["id"])
    if not new_site:
        rows = db.rows("SELECT name FROM locations WHERE site_id = ? AND parent_id IS ?", (site["id"], body.parent_id))
        existing = {r["name"].lower() for r in rows}

    flat: list[dict] = []
    _flatten(body.tree, parent_rank, parent_path, existing, flat)
    summary = {"standort": 1 if new_site else 0,
               **{k: sum(1 for f in flat if f["kind"] == k) for k in RANK}}
    preview = [{"kind": f["kind"], "name": f["name"], "rack_units": f["rack_units"], "path": f["path"], "depth": f["depth"]} for f in flat]
    result = {"site": {"id": site["id"], "code": site["code"], "name": site["name"], "new": new_site},
              "counts": summary, "items": preview, "dry_run": body.dry_run}
    if body.dry_run:
        return result

    # Anlegen: alles in einer Transaktion
    try:
        with db.transaction() as c:
            if new_site:
                site_id = c.execute("INSERT INTO sites(code, name, address, note) VALUES (?,?,?,?)",
                                    (site["code"], site["name"], body.site.address.strip(), body.site.note.strip())).lastrowid
            else:
                site_id = site["id"]
            ids: dict[int, int] = {}                    # id(Node) -> Location-ID
            parent_of = _parent_map(body.tree)
            for f in flat:
                node = f["node"]
                par = parent_of.get(id(node))
                parent_id = ids[id(par)] if par is not None else (body.parent_id if body.parent_id else None)
                ids[id(node)] = c.execute(
                    "INSERT INTO locations(site_id, parent_id, kind, name, rack_units, note) VALUES (?,?,?,?,?,?)",
                    (site_id, parent_id, f["kind"], f["name"], f["rack_units"], f["note"])).lastrowid
    except sqlite3.IntegrityError as e:
        raise HTTPException(409, f"Anlegen nicht möglich: {e}")
    result["site"]["id"] = site_id
    result["dry_run"] = False
    audit.log(me.name, "wizard.site", "site", site_id,
              f"{site['code']}: " + ", ".join(f"{summary[k]} {LABEL[k]}" for k in RANK if summary[k])
              + (" (neuer Standort)" if new_site else " (Struktur ergänzt)"))
    return result


def _parent_map(nodes, parent=None, out: Optional[dict] = None) -> dict:
    out = {} if out is None else out
    for n in nodes:
        out[id(n)] = parent
        _parent_map(n.children, n, out)
    return out


# ── Gerät platzieren (Switch, Patchfeld, …) ───────────────────────────────────

@router.get("/rack-slots/{location_id}")
def rack_slots(location_id: int, height_u: int = 1, mount_side: str = "both", orientation: str = "horizontal", side_slot: str = "",
               me: Principal = Depends(current_principal)):
    """Belegung eines Racks und die freien Startpositionen für ein Gerät der Höhe ``height_u`` in der gewählten Einbaulage
    (Einbauseite, 19 Zoll bzw. hochkant im Seitenkanal)."""
    loc = db.row("SELECT * FROM locations WHERE id = ?", (location_id,))
    if not loc:
        raise HTTPException(404, "Location nicht gefunden")
    access.require_read(me, loc["site_id"], "Rack")
    if loc["kind"] not in CONTAINER_KINDS:
        raise HTTPException(400, "Das ist kein Rack, Wandgehäuse oder Schaltschrank")
    side_slot = rackmount.check_mount(orientation, mount_side, side_slot)
    units = loc["rack_units"] or DEFAULT_RACK_UNITS
    devs = db.rows("""SELECT id, hostname, type, rack_position, height_u, orientation, mount_side, side_slot FROM devices
                      WHERE location_id = ? AND (rack_position IS NOT NULL OR orientation = 'vertical') ORDER BY rack_position""", (location_id,))
    leaving = rackmount.pending_removal_device_ids()
    for d in devs:
        d["pending_removal"] = d["id"] in leaving
    h = max(1, height_u)
    free = [p for p in range(1, units - h + 2) if not rackmount.rack_conflicts(loc, orientation, mount_side, side_slot, p, h)]
    return {"rack_units": units, "devices": devs, "free_starts": free, "height_u": h}


def _groups(body: DeviceWizardIn, model: Optional[dict]) -> list[PortGroup]:
    if model:
        return [PortGroup(**g) for g in json.loads(model["ports"] or "[]")]
    return list(body.ports)


def _port_names(groups: list[PortGroup]) -> list[str]:
    names = []
    for g in groups:
        for i in range(g.start, g.start + g.count):
            names.append(f"{g.prefix}{i}")
            if g.dual:
                names.append(f"{g.prefix}{i}{g.back_suffix}")
    return names


@router.post("/device")
def device_wizard(body: DeviceWizardIn, me: Principal = Depends(current_principal)):
    """Legt ein Gerät samt Ports an, platziert es im Rack und verbindet optional einen Port (Uplink).

    ``mode=direct``: alles sofort, Kabel direkt. ``mode=workorder``: Gerät als „geplant“; Einbau (und Kabel) werden Positionen eines
    Patchauftrags, nach dessen Bestätigung gilt das Gerät als eingebaut. ``dry_run=True`` prüft nur und liefert die Vorschau.

    Logikprüfung: Ist die HE von einem Gerät belegt oder der Zielport schon verkabelt, antwortet der Server mit 409 und
    ``detail.code`` = ``slot_busy`` bzw. ``port_busy``. Mit ``replace_devices`` / ``remove_old`` wird das Alte zurückgebaut –
    per automatisch angelegtem Rückbau-Patchauftrag (der neue Auftrag startet erst nach dessen Bestätigung) bzw. bei ``direct`` sofort."""
    if body.mode not in ("direct", "workorder"):
        raise HTTPException(400, "Umsetzung: direct oder workorder")
    if body.status not in ("planned", "active"):
        raise HTTPException(400, "Status: planned oder active")
    if body.type not in DEVICE_TYPES:
        raise HTTPException(400, f"Typ '{body.type}' ist ungültig (erlaubt: {', '.join(DEVICE_TYPES)})")
    loc = db.row("SELECT * FROM locations WHERE id = ?", (body.location_id,))
    if not loc:
        raise HTTPException(400, "Location nicht gefunden")
    site = loc["site_id"]

    # Berechtigung
    wo_mode = body.mode == "workorder"
    if wo_mode:
        if me.kind != "user" or not me.has_at(site, "planer"):
            raise HTTPException(403, "Für die Umsetzung per Patchauftrag ist die Rolle „Planer“ an diesem Standort nötig")
    else:
        access.require_write(me, site)
    status = "planned" if wo_mode else body.status

    # Modell und Ports
    model = None
    if body.model_id:
        model = db.row("SELECT * FROM device_models WHERE id = ?", (body.model_id,))
        if not model:
            raise HTTPException(400, "Katalogmodell nicht gefunden")
    groups = _groups(body, model)
    for g in groups:
        masterdata._one_of(g.medium, masterdata.PORT_MEDIA, "Medium")
    names = _port_names(groups)
    if len(names) > MAX_TEMPLATE_PORTS:
        raise HTTPException(400, f"Zu viele Ports ({len(names)}, höchstens {MAX_TEMPLATE_PORTS})")
    if len(set(n.lower() for n in names)) != len(names):
        raise HTTPException(400, "Portnamen der Vorlage sind nicht eindeutig")
    height = body.height_u or (model["height_u"] if model else 1)
    vendor = body.vendor.strip() or (model["vendor"] if model else "")
    model_name = body.model.strip() or (model["model"] if model else "")

    # Einbaulage: Seite, 19 Zoll oder hochkant im Seitenkanal (aus dem Modell, wenn nicht angegeben)
    orientation = body.orientation or (model["orientation"] if model else "horizontal")
    mount_side = body.mount_side or (model["mount_side"] if model else "both")
    side_slot = body.side_slot if body.side_slot is not None else (model["side_slot"] if model else "")
    side_slot = rackmount.check_mount(orientation, mount_side, side_slot)
    position = body.rack_position
    if orientation == "vertical":
        if loc["kind"] != "rack":
            raise HTTPException(400, "Hochkant eingebaute Geräte (z. B. PDU) brauchen ein Rack")
        position = position or 1
        height = max(1, min(height, (loc["rack_units"] or DEFAULT_RACK_UNITS) - position + 1))        # Länge höchstens bis zur Rackhöhe

    # Hostname (Platzhalter bekommen einen automatischen Namen)
    hostname = body.hostname.strip()
    if not hostname:
        if body.type not in PASSIVE_TYPES:
            raise HTTPException(400, "Hostname fehlt")
        hostname = _auto_name(body.type, loc, position, orientation, side_slot, mount_side)
    taken = db.row("SELECT id FROM devices WHERE hostname = ? COLLATE NOCASE", (hostname,))

    # Logikprüfung 1: Höheneinheiten belegt?
    overlaps = rackmount.rack_conflicts(loc, orientation, mount_side, side_slot, position, height) if loc["kind"] in CONTAINER_KINDS else []
    if overlaps and not body.replace_devices:
        txt = ", ".join(rackmount.describe(d) for d in overlaps)
        where = "Der Seitenkanal ist" if orientation == "vertical" else "Die Höheneinheiten sind"
        raise workorders.conflict_error("slot_busy", f"{where} belegt durch {txt}. Altes Gerät zurückbauen? "
                                        + ("Dafür wird automatisch ein Rückbau-Patchauftrag angelegt." if wo_mode else "Es wird sofort ausgebaut."),
                                        [{"id": d["id"], "hostname": d["hostname"], "type": d["type"], "rack_position": d["rack_position"],
                                          "height_u": d["height_u"], "orientation": d["orientation"], "mount_side": d["mount_side"],
                                          "side_slot": d["side_slot"]} for d in overlaps])
    for d in overlaps:                                          # Rückbau braucht Schreibrecht am Standort des alten Geräts
        if not (me.has_at(site, "planer") if wo_mode else access.can_write_site(me, site)):
            raise HTTPException(403, "Keine Berechtigung für diesen Standort")
    masterdata._check_device(DeviceIn(hostname=hostname, type=body.type, height_u=height, location_id=body.location_id,
                                      rack_position=position, status=status, orientation=orientation, mount_side=mount_side, side_slot=side_slot),
                             ignore_ids=tuple(d["id"] for d in overlaps))

    # Hostname: Ersetzt das neue Gerät ein altes mit gleichem Namen (Rückbau ist geplant bzw. beschlossen), trägt es bis zum
    # Rückbau einen vorläufigen Namen und übernimmt den Wunschnamen danach automatisch.
    db_hostname, planned_name = hostname, ""
    if taken:
        if taken["id"] in ({d["id"] for d in overlaps} | masterdata.pending_removal_device_ids()):
            planned_name = hostname
            db_hostname = workorders.unique_hostname(f"{hostname}~geplant")
        else:
            raise HTTPException(409, f"Ein Gerät mit dem Hostnamen '{hostname}' existiert bereits")

    # Kabel / Uplink (Logikprüfung 2: Zielport belegt?)
    links = ([body.uplink] if body.uplink else []) + list(body.links)
    link_rows: list = []                                        # (Verbindung, Zielport)
    lower_names = {n.lower() for n in names}
    seen_own, seen_target = set(), set()
    for up in links:
        if up.port_name.lower() not in lower_names:
            raise HTTPException(400, f"Der Port '{up.port_name}' ist am neuen Gerät nicht vorgesehen")
        if up.port_name.lower() in seen_own:
            raise HTTPException(400, f"Der Port '{up.port_name}' wird mehrfach verbunden")
        if up.target_port_id in seen_target:
            raise HTTPException(400, "Ein Zielport wird mehrfach verwendet")
        seen_own.add(up.port_name.lower()); seen_target.add(up.target_port_id)
        up.cable_type = check_cable_type(up.cable_type)
        target = db.row("""SELECT p.id, p.name, d.hostname, l.site_id FROM ports p JOIN devices d ON d.id = p.device_id
                           LEFT JOIN locations l ON l.id = d.location_id WHERE p.id = ?""", (up.target_port_id,))
        if not target:
            raise HTTPException(404, "Zielport nicht gefunden")
        if wo_mode:
            if not me.has_at(target["site_id"], "planer"):
                raise HTTPException(403, "Der Zielport liegt außerhalb deines Bereichs")
        else:
            access.require_write(me, target["site_id"])
        link_rows.append((up, target))
    # Logikprüfung 2: Zielports reserviert/verplant, dann belegt? (alle Verbindungen zusammen, je eine Rückfrage)
    reservations.check([t["id"] for _, t in link_rows], use_reserved=body.use_reserved, by=me.name,
                       workorder_id=body.workorder_id if wo_mode else None, dry_run=body.dry_run)
    cable_conflicts = workorders.port_conflicts([t["id"] for _, t in link_rows]) if link_rows else []
    unresolved = [c for c in cable_conflicts if not c["removal_order"]]
    if unresolved and not body.remove_old:
        msg = workorders.busy_message(unresolved)
        if not wo_mode:
            msg = msg.replace("Dafür wird automatisch ein Rückbau-Patchauftrag angelegt.", "Die alten Patches werden sofort entfernt.")
        raise workorders.conflict_error("port_busy", msg, cable_conflicts)

    # Auftrag
    wo = None
    if wo_mode and body.workorder_id:
        wo = workorders._wo_or_404(body.workorder_id, me)
        if wo["status"] not in ("draft", "rework"):
            raise HTTPException(409, "Positionen können nur in Entwürfen oder zurückgewiesenen Aufträgen ergänzt werden")
        workorders._require_role(me, ["planer", "admin"], wo)

    removals = {"devices": [d["hostname"] for d in overlaps],
                "cables": [f"{c['port']} ↔ {c['other']}" for c in cable_conflicts if not c["removal_order"]]}
    preview = {
        "device": {"hostname": hostname, "temporary_hostname": db_hostname if planned_name else None, "type": body.type, "vendor": vendor, "model": model_name, "height_u": height,
                   "status": status, "location_path": masterdata.location_path(body.location_id), "rack_position": position,
                   "orientation": orientation, "mount_side": mount_side, "side_slot": side_slot},
        "ports": {"count": len(names), "first": names[:3], "last": names[-2:] if len(names) > 3 else []},
        "cables": [{"from": f"{hostname}:{u.port_name}", "to": f"{t['hostname']}:{t['name']}", "type": u.cable_type, "label": u.cable_label,
                    "via": "Patchauftrag" if wo_mode else "direkt"} for u, t in link_rows],
        "cable": ({"from": f"{hostname}:{link_rows[0][0].port_name}", "to": f"{link_rows[0][1]['hostname']}:{link_rows[0][1]['name']}",
                   "type": link_rows[0][0].cable_type, "via": "Patchauftrag" if wo_mode else "direkt"} if link_rows else None),
        "workorder": ({"existing": wo["number"]} if wo else {"new": body.workorder_title.strip() or f"Einbau {hostname}"}) if wo_mode else None,
        "removals": {**removals, "via": "Rückbau-Patchauftrag" if wo_mode else "sofort"} if (removals["devices"] or removals["cables"]) else None,
    }
    if body.dry_run:
        return {"dry_run": True, **preview}

    # Anlegen (Gerät, Ports, Kabel bzw. Auftragspositionen); bei einem Fehler werden Gerät und neuer Auftrag wieder entfernt
    now = time.time()
    did, new_wo_id, out_wo, cable_ids, created = None, None, None, [], 0
    try:
        did = db.execute(
            """INSERT INTO devices(hostname, type, vendor, model, serial, mgmt_ip, location_id, rack_position, height_u, status,
                                   source, note, model_id, planned_hostname, mount_side, orientation, side_slot, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (db_hostname, body.type, vendor, model_name, body.serial.strip(), body.mgmt_ip.strip(), body.location_id,
             position, height, status, "manual", body.note.strip(), body.model_id, planned_name, mount_side, orientation, side_slot, now, now))
        created = sum(masterdata._create_port_group(did, g)[0] for g in groups)
        own_ids = {u.port_name: db.row("SELECT id FROM ports WHERE device_id = ? AND name = ? COLLATE NOCASE", (did, u.port_name))["id"]
                   for u, _ in link_rows}
        if wo_mode:
            if wo:
                wid = wo["id"]
            else:
                wid = new_wo_id = db.execute(
                    """INSERT INTO workorders(number, title, description, status, priority, location_id, note,
                                              openplan_project, openplan_task, openplan_link, created_by, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (workorders._next_number(), body.workorder_title.strip() or f"Einbau {hostname}",
                     f"Einbau von {hostname} ({model_name or body.type}) in {masterdata.location_path(body.location_id)}", "draft", "normal",
                     body.location_id, "", "", "", "", me.name, now, now))
            workorders._add_item_raw(wid, "install_device", device_id=did, note=f"Einbau {hostname}")
            for up, target in link_rows:
                workorders._add_item_raw(wid, "connect", port_a_id=own_ids[up.port_name], port_b_id=target["id"], cable_label=up.cable_label.strip(),
                                         cable_type=up.cable_type, fiber_count=up.fiber_count, length_m=up.length_m, color=up.color.strip(),
                                         note=up.note.strip())
            w_row = db.row("SELECT * FROM workorders WHERE id = ?", (wid,))
            if overlaps:
                workorders.schedule_device_removal(me, w_row, overlaps)
            if cable_conflicts:
                workorders.schedule_cable_removal(me, db.row("SELECT * FROM workorders WHERE id = ?", (wid,)), cable_conflicts)
            w = db.row("SELECT id, number, title, depends_on FROM workorders WHERE id = ?", (wid,))
            dep = db.row("SELECT id, number FROM workorders WHERE id = ?", (w["depends_on"],)) if w["depends_on"] else None
            out_wo = {"id": w["id"], "number": w["number"], "title": w["title"], "new": bool(new_wo_id),
                      "removal_order": {"id": dep["id"], "number": dep["number"]} if dep else None}
        else:
            for d in overlaps:                                  # sofort ausbauen (Kabel weg, HE frei)
                n = workorders.retire_device(d["id"], by=me.name)
                audit.log(me.name, "device.retire", "device", d["id"], f"{d['hostname']} zurückgebaut für {hostname} ({n} Kabel entfernt)")
            if planned_name:
                workorders.finalize_hostname(did)                          # alter Name ist jetzt frei
            for c in cable_conflicts:
                cablelog.remove_cable(c["cable_id"], by=me.name, reason="wizard")
                audit.log(me.name, "cable.remove", "cable", c["cable_id"], f"{c['port']} ↔ {c['other']} entfernt für {hostname}")
            for up, target in link_rows:
                own_id = own_ids[up.port_name]
                lo, hi = (own_id, target["id"]) if own_id < target["id"] else (target["id"], own_id)
                cid = db.execute(
                    """INSERT INTO cables(port_a_id, port_b_id, cable_label, cable_type, fiber_count, length_m, color, installed_at,
                                          measurement_ref, measurement_ok, note, created_by, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (lo, hi, up.cable_label.strip(), up.cable_type, up.fiber_count, up.length_m, up.color.strip(), None,
                     "", None, up.note.strip(), me.name, now))
                cable_ids.append(cid)
    except Exception:
        if new_wo_id:
            db.execute("DELETE FROM workorders WHERE id = ?", (new_wo_id,))
        if did:
            db.execute("DELETE FROM devices WHERE id = ?", (did,))               # Ports werden mit gelöscht
        raise
    audit.log(me.name, "wizard.device", "device", did,
              f"{hostname} ({body.type}) in {masterdata.location_path(body.location_id)}: {created} Ports"
              + (f", Auftrag {out_wo['number']}" if out_wo else "") + (f", {len(cable_ids)} Kabel direkt" if cable_ids else "")
              + (f", Rückbau: {', '.join(removals['devices'] + removals['cables'])}" if (removals["devices"] or removals["cables"]) else ""))
    return {"dry_run": False, **preview, "device_id": did, "ports_created": created, "cable_id": cable_ids[0] if cable_ids else None, "cable_ids": cable_ids,
            "workorder": out_wo}


PASSIVE_PREFIX = {"cable_mgmt": "KF", "blank_panel": "BB", "shelf": "FB"}


def _auto_name(dtype: str, loc: dict, position: Optional[int], orientation: str = "horizontal", side_slot: str = "", mount_side: str = "both") -> str:
    """Eindeutiger Name für Platzhalter, z. B. KF-R1-HE5 (Kabelführung im Rack R1 ab HE 5) bzw. KF-R1-HR-L (hinten links, hochkant)."""
    rack = re.sub(r"[^A-Za-z0-9]+", "", loc["name"])[:16] or "LOC"
    if orientation == "vertical":
        base = f"{PASSIVE_PREFIX.get(dtype, 'PH')}-{rack}-{'H' if mount_side == 'rear' else 'V'}{'L' if side_slot == 'left' else 'R'}"
    else:
        base = f"{PASSIVE_PREFIX.get(dtype, 'PH')}-{rack}" + (f"-HE{position}" if position else "")
    name, n = base, 1
    while db.row("SELECT id FROM devices WHERE hostname = ? COLLATE NOCASE", (name,)):
        n += 1
        name = f"{base}-{n}"
    return name


# ── Kabel einbauen ────────────────────────────────────────────────────────────

# Welche Port-Medien zu welcher Kabelkategorie passen (Medium „other“ passt immer; Abweichungen werden nur als Hinweis gemeldet)
CATEGORY_MEDIA = {
    "copper": {"RJ45", "SFP", "SFP+", "SFP28", "QSFP"},            # inkl. DAC
    "fiber":  {"LWL", "SFP", "SFP+", "SFP28", "QSFP"},
    "power":  {"C13", "C14", "Schuko"},
    "coax":   {"BNC"},
    "serial": {"RS232", "RS485", "RJ45", "RJ11"},
    "telco":  {"RJ11", "RJ45", "UP0E", "S0", "S2M", "a/b", "TAE", "LSA"},
}


def _port_full(pid: int) -> Optional[dict]:
    return db.row("""SELECT p.id, p.name, p.medium, d.id AS device_id, d.hostname, d.status, d.location_id, l.site_id
                     FROM ports p JOIN devices d ON d.id = p.device_id LEFT JOIN locations l ON l.id = d.location_id WHERE p.id = ?""", (pid,))


@router.post("/cable")
def cable_wizard(body: CableWizardIn, me: Principal = Depends(current_principal)):
    """Verbindet zwei Ports mit einem Kabel – sofort (``mode=direct``) oder als Position eines Patchauftrags (``workorder``).

    Logikprüfung: Sind Ports belegt, antwortet der Server mit 409 ``port_busy``; mit ``remove_old`` werden die alten Patches
    zurückgebaut (per automatisch angelegtem Rückbau-Auftrag bzw. bei ``direct`` sofort). Passen die Port-Medien nicht zur Kabelart
    (z. B. RJ45-Port für ein Stromkabel), kommt ein Hinweis in ``warnings`` – kein Fehler."""
    if body.mode not in ("direct", "workorder"):
        raise HTTPException(400, "Umsetzung: direct oder workorder")
    if body.port_a_id == body.port_b_id:
        raise HTTPException(400, "Ein Port kann nicht mit sich selbst verbunden werden")
    a, b = _port_full(body.port_a_id), _port_full(body.port_b_id)
    if not a or not b:
        raise HTTPException(404, "Port nicht gefunden")
    for x in (a, b):
        if x["status"] == "retired":
            raise HTTPException(400, f"Das Gerät {x['hostname']} ist außer Betrieb")
    ctype = check_cable_type(body.cable_type)
    ct = db.row("SELECT * FROM cable_types WHERE name = ?", (ctype,))

    wo_mode = body.mode == "workorder"
    if wo_mode:
        if me.kind != "user" or not (me.has_at(a["site_id"], "planer") and me.has_at(b["site_id"], "planer")):
            raise HTTPException(403, "Für Patchaufträge ist die Rolle „Planer“ an den Standorten beider Ports nötig")
    else:
        access.require_write(me, a["site_id"])
        access.require_write(me, b["site_id"])

    if db.row("SELECT id FROM cables WHERE (port_a_id = ? AND port_b_id = ?) OR (port_a_id = ? AND port_b_id = ?)",
              (a["id"], b["id"], b["id"], a["id"])):
        raise HTTPException(409, "Diese beiden Ports sind bereits miteinander verbunden")

    # Logikprüfung: reservierte/verplante, dann belegte Ports
    reservations.check([a["id"], b["id"]], use_reserved=body.use_reserved, by=me.name,
                       workorder_id=body.workorder_id if wo_mode else None, dry_run=body.dry_run)
    conflicts = workorders.port_conflicts([a["id"], b["id"]])
    unresolved = [c for c in conflicts if not c["removal_order"]]
    if unresolved and not body.remove_old:
        msg = workorders.busy_message(unresolved)
        if not wo_mode:
            msg = msg.replace("Dafür wird automatisch ein Rückbau-Patchauftrag angelegt.", "Der alte Patch wird sofort entfernt.")
        raise workorders.conflict_error("port_busy", msg, conflicts)

    # Hinweise: Medium passt nicht zur Kabelart
    warnings = []
    allowed = CATEGORY_MEDIA.get(ct["category"])
    if allowed:
        for x in (a, b):
            if x["medium"] not in allowed and x["medium"] != "other":
                warnings.append(f"Port {x['hostname']}:{x['name']} hat das Medium {x['medium']}, das normalerweise nicht zu „{ctype}“ passt")
    count = body.fiber_count if ct["count_label"] else None

    # Auftrag
    wo = None
    if wo_mode and body.workorder_id:
        wo = workorders._wo_or_404(body.workorder_id, me)
        if wo["status"] not in ("draft", "rework"):
            raise HTTPException(409, "Positionen können nur in Entwürfen oder zurückgewiesenen Aufträgen ergänzt werden")
        workorders._require_role(me, ["planer", "admin"], wo)
    loc_id = a["location_id"] or b["location_id"]
    if wo_mode and not wo and not loc_id and not me.is_global:
        raise HTTPException(400, "Ohne Location an den Geräten kann kein Auftrag in deinem Bereich angelegt werden")

    label = body.cable_label.strip()
    title = body.workorder_title.strip() or f"Kabel {a['hostname']} ↔ {b['hostname']}"
    removals = [f"{c['port']} ↔ {c['other']}" for c in conflicts if not c["removal_order"]]
    preview = {
        "cable": {"from": f"{a['hostname']}:{a['name']}", "to": f"{b['hostname']}:{b['name']}", "type": ctype, "category": ct["category"],
                  "label": label, "via": "Patchauftrag" if wo_mode else "direkt"},
        "warnings": warnings,
        "workorder": ({"existing": wo["number"]} if wo else {"new": title}) if wo_mode else None,
        "removals": {"cables": removals, "via": "Rückbau-Patchauftrag" if wo_mode else "sofort"} if removals else None,
    }
    if body.dry_run:
        return {"dry_run": True, **preview}

    now = time.time()
    new_wo_id, out_wo, cable_id = None, None, None
    try:
        if wo_mode:
            if wo:
                wid = wo["id"]
            else:
                wid = new_wo_id = db.execute(
                    """INSERT INTO workorders(number, title, description, status, priority, location_id, note,
                                              openplan_project, openplan_task, openplan_link, created_by, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (workorders._next_number(), title, f"{ctype}: {a['hostname']}:{a['name']} ↔ {b['hostname']}:{b['name']}", "draft", "normal",
                     loc_id, "", "", "", "", me.name, now, now))
            workorders._add_item_raw(wid, "connect", port_a_id=a["id"], port_b_id=b["id"], cable_label=label, cable_type=ctype,
                                     fiber_count=count, length_m=body.length_m, color=body.color.strip(), note=body.note.strip())
            if conflicts:
                workorders.schedule_cable_removal(me, db.row("SELECT * FROM workorders WHERE id = ?", (wid,)), conflicts)
            w = db.row("SELECT id, number, title, depends_on FROM workorders WHERE id = ?", (wid,))
            dep = db.row("SELECT id, number FROM workorders WHERE id = ?", (w["depends_on"],)) if w["depends_on"] else None
            out_wo = {"id": w["id"], "number": w["number"], "title": w["title"], "new": bool(new_wo_id),
                      "removal_order": {"id": dep["id"], "number": dep["number"]} if dep else None}
        else:
            for c in conflicts:
                cablelog.remove_cable(c["cable_id"], by=me.name, reason="wizard")
                audit.log(me.name, "cable.remove", "cable", c["cable_id"], f"{c['port']} ↔ {c['other']} entfernt für neues Kabel")
            lo, hi = (a["id"], b["id"]) if a["id"] < b["id"] else (b["id"], a["id"])
            cable_id = db.execute(
                """INSERT INTO cables(port_a_id, port_b_id, cable_label, cable_type, fiber_count, length_m, color, installed_at,
                                      measurement_ref, measurement_ok, note, created_by, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (lo, hi, label, ctype, count, body.length_m, body.color.strip(), body.installed_at, "", None, body.note.strip(), me.name, now))
    except Exception:
        if new_wo_id:
            db.execute("DELETE FROM workorders WHERE id = ?", (new_wo_id,))
        raise
    audit.log(me.name, "wizard.cable", "cable" if cable_id else "workorder", cable_id or (out_wo or {}).get("id", ""),
              f"{a['hostname']}:{a['name']} ↔ {b['hostname']}:{b['name']} ({ctype})" + (f", Auftrag {out_wo['number']}" if out_wo else ", direkt")
              + (f", Rückbau: {', '.join(removals)}" if removals else ""))
    return {"dry_run": False, **preview, "cable_id": cable_id, "workorder": out_wo}


# ── Massenverkabelung ─────────────────────────────────────────────────────────

MAX_PORT_LIST = 2000


def _chunks(items: list, n: int = 500):
    for i in range(0, len(items), n):
        yield items[i:i + n]


@router.post("/port-list")
def port_list(spec: PortListSpec, me: Principal = Depends(current_principal)):
    """Ports einer Quelle (ein Gerät oder alle Geräte einer Location) in natürlicher Reihenfolge – Grundlage der Massenverkabelung.
    Für Patchfelder trennt ``side`` Vorderseite und Rückseite (Rückseiten-Ports enden auf ``-back``)."""
    if spec.side not in ("all", "front", "back"):
        raise HTTPException(400, "side: all, front oder back")
    if spec.device_id:
        d = db.row("SELECT id, location_id FROM devices WHERE id = ?", (spec.device_id,))
        if not d:
            raise HTTPException(404, "Gerät nicht gefunden")
        access.require_read(me, access.site_of_location(d["location_id"]), "Gerät")
        dev_ids = [d["id"]]
    elif spec.location_id:
        loc = db.row("SELECT * FROM locations WHERE id = ?", (spec.location_id,))
        if not loc:
            raise HTTPException(404, "Location nicht gefunden")
        access.require_read(me, loc["site_id"], "Location")
        locs = masterdata._location_and_children(spec.location_id)
        dev_ids = []
        for part in _chunks(locs):
            sql = f"SELECT id FROM devices WHERE status <> 'retired' AND location_id IN ({','.join('?' * len(part))})"
            args = list(part)
            if spec.device_types:
                sql += f" AND type IN ({','.join('?' * len(spec.device_types))})"; args += spec.device_types
            dev_ids += [r["id"] for r in db.rows(sql, tuple(args))]
    else:
        raise HTTPException(400, "device_id oder location_id angeben")
    rows = []
    for part in _chunks(dev_ids):
        rows += db.rows(f"""SELECT p.id, p.name, p.medium, d.id AS device_id, d.hostname, d.type, d.location_id,
                                   EXISTS(SELECT 1 FROM cables c WHERE c.port_a_id = p.id OR c.port_b_id = p.id) AS busy
                            FROM ports p JOIN devices d ON d.id = p.device_id WHERE d.id IN ({','.join('?' * len(part))})""", tuple(part))
    out, paths = [], {}
    res, plan = reservations.active(r["id"] for r in rows), reservations.planned(r["id"] for r in rows)
    for r in rows:
        back = r["name"].lower().endswith("-back")
        if (spec.side == "front" and back) or (spec.side == "back" and not back):
            continue
        if spec.only_free and (r["busy"] or r["id"] in res or r["id"] in plan):    # frei = nicht verbunden, nicht reserviert, nicht verplant
            continue
        if spec.medium and r["medium"] != spec.medium:
            continue
        if not access.can_read_site(me, access.site_of_location(r["location_id"])):
            continue
        if r["location_id"] not in paths:
            paths[r["location_id"]] = masterdata.location_path(r["location_id"])
        out.append({"id": r["id"], "name": r["name"], "medium": r["medium"], "device_id": r["device_id"], "hostname": r["hostname"],
                    "type": r["type"], "busy": bool(r["busy"]), "side": "back" if back else "front", "location_path": paths[r["location_id"]],
                    "reserved": res[r["id"]]["purpose"] if r["id"] in res else None,
                    "planned": plan[r["id"]]["number"] if r["id"] in plan else None})
    out.sort(key=lambda x: masterdata._natural_key(f"{x['hostname']} {x['name']}"))
    return {"total": len(out), "truncated": len(out) > MAX_PORT_LIST, "ports": out[:MAX_PORT_LIST]}


@router.post("/bulk-cables/parse")
def bulk_parse(body: BulkParseIn, me: Principal = Depends(current_principal)):
    """Liste (CSV/TSV aus Excel) einlesen: Gerät A; Port A; Gerät B; Port B; [Kabelnummer] – je Zeile ein Kabel.
    Liefert die aufgelösten Paare und eine Fehlerliste (unbekannte Geräte/Ports, Doppelungen)."""
    text = body.text.lstrip("\ufeff")
    first = text.split("\n", 1)[0]
    delim = max((";", "\t", ","), key=lambda c: first.count(c))
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    pairs, errors, seen = [], [], set()
    start = 0
    if rows and any(re.search(r"port|gerät|geraet|device|host", c, re.I) for c in rows[0]):
        start = 1                                                  # Kopfzeile überspringen

    def find(host: str, port: str):
        d = db.row("SELECT id, location_id FROM devices WHERE hostname = ? COLLATE NOCASE", (host.strip(),))
        if not d or not access.can_read_site(me, access.site_of_location(d["location_id"])):
            return None, f"Gerät „{host.strip()}“ nicht gefunden"
        p = db.row("SELECT id, name FROM ports WHERE device_id = ? AND name = ? COLLATE NOCASE", (d["id"], port.strip()))
        if not p:
            return None, f"Port „{port.strip()}“ an {host.strip()} nicht gefunden"
        return p["id"], ""

    for i, r in enumerate(rows[start:], start + 1):
        if not any(c.strip() for c in r):
            continue
        if len(r) < 4:
            errors.append({"line": i, "message": "mindestens 4 Spalten nötig: Gerät A; Port A; Gerät B; Port B"}); continue
        a, ea = find(r[0], r[1]); b, eb = find(r[2], r[3])
        if ea or eb:
            errors.append({"line": i, "message": "; ".join(x for x in (ea, eb) if x)}); continue
        if a == b or a in seen or b in seen:
            errors.append({"line": i, "message": "Port kommt mehrfach vor oder ist mit sich selbst verbunden"}); continue
        seen.add(a); seen.add(b)
        pairs.append({"port_a_id": a, "port_b_id": b, "cable_label": (r[4].strip() if len(r) > 4 else ""),
                      "a": f"{r[0].strip()}:{r[1].strip()}", "b": f"{r[2].strip()}:{r[3].strip()}", "line": i})
    return {"pairs": pairs, "errors": errors, "total": len(pairs) + len(errors)}


@router.post("/bulk-cables")
def bulk_cables(body: BulkCablesIn, me: Principal = Depends(current_principal)):
    """Viele Kabel auf einmal anlegen. ``mode=workorder`` erzeugt **einen** Patchauftrag mit einer Position je Kabel (eine Arbeitsliste für
    die Ausführenden), ``mode=direct`` schreibt alle Kabel sofort (atomar). Belegte Ports führen zu einer einzigen Rückfrage (409 ``port_busy``);
    mit ``remove_old`` werden die alten Patches zurückgebaut (automatischer Rückbau-Auftrag bzw. sofort). Bereits bestehende Verbindungen
    zwischen genau diesen Ports werden übersprungen."""
    if body.mode not in ("direct", "workorder"):
        raise HTTPException(400, "Umsetzung: direct oder workorder")
    wo_mode = body.mode == "workorder"
    ctype = check_cable_type(body.cable_type)
    ct = db.row("SELECT * FROM cable_types WHERE name = ?", (ctype,))
    count = body.fiber_count if ct["count_label"] else None

    # Ports laden und prüfen
    ids = [x for p in body.pairs for x in (p.port_a_id, p.port_b_id)]
    if len(set(ids)) != len(ids):
        dup = next(i for i in ids if ids.count(i) > 1)
        raise HTTPException(400, f"Der Port {_port_label_by_id(dup)} kommt mehrfach in der Liste vor")
    info = {}
    for part in _chunks(ids):
        for r in db.rows(f"""SELECT p.id, p.name, p.medium, d.hostname, d.status, d.location_id, l.site_id
                             FROM ports p JOIN devices d ON d.id = p.device_id LEFT JOIN locations l ON l.id = d.location_id
                             WHERE p.id IN ({','.join('?' * len(part))})""", tuple(part)):
            info[r["id"]] = r
    for p in body.pairs:
        if p.port_a_id == p.port_b_id:
            raise HTTPException(400, "Ein Port kann nicht mit sich selbst verbunden werden")
    missing = [i for i in ids if i not in info]
    if missing:
        raise HTTPException(404, f"Port {missing[0]} nicht gefunden")
    retired = {r["hostname"] for r in info.values() if r["status"] == "retired"}
    if retired:
        raise HTTPException(400, f"Geräte außer Betrieb können nicht verkabelt werden: {', '.join(sorted(retired))}")

    # Berechtigung je beteiligtem Standort
    for site in {r["site_id"] for r in info.values()}:
        if wo_mode:
            if me.kind != "user" or not me.has_at(site, "planer"):
                raise HTTPException(403, "Für Patchaufträge ist die Rolle „Planer“ an allen beteiligten Standorten nötig")
        else:
            access.require_write(me, site)

    # bereits bestehende Verbindungen überspringen
    pairs, skipped = [], []
    for p in body.pairs:
        if db.row("SELECT id FROM cables WHERE (port_a_id = ? AND port_b_id = ?) OR (port_a_id = ? AND port_b_id = ?)",
                  (p.port_a_id, p.port_b_id, p.port_b_id, p.port_a_id)):
            skipped.append(f"{_lbl(info[p.port_a_id])} ↔ {_lbl(info[p.port_b_id])}")
        else:
            pairs.append(p)
    if not pairs:
        raise HTTPException(409, "Alle Verbindungen bestehen bereits")

    # Logikprüfung: reservierte/verplante, dann belegte Ports (je eine Rückfrage für alle)
    reservations.check([x for p in pairs for x in (p.port_a_id, p.port_b_id)], use_reserved=body.use_reserved, by=me.name,
                       workorder_id=body.workorder_id if wo_mode else None, dry_run=body.dry_run)
    conflicts = workorders.port_conflicts([x for p in pairs for x in (p.port_a_id, p.port_b_id)])
    unresolved = [c for c in conflicts if not c["removal_order"]]
    if unresolved and not body.remove_old:
        shown = unresolved[:5]
        msg = (f"{len(unresolved)} Port(s) sind bereits verbunden, z. B. " + "; ".join(f"{c['port']} mit {c['other']}" for c in shown)
               + (" …" if len(unresolved) > 5 else "") + ". Alte Patches zurückbauen? "
               + ("Dafür wird automatisch ein Rückbau-Patchauftrag angelegt." if wo_mode else "Sie werden sofort entfernt."))
        raise workorders.conflict_error("port_busy", msg, conflicts)

    # Hinweise: Medium passt nicht zur Kabelart
    allowed = CATEGORY_MEDIA.get(ct["category"])
    warn = []
    if allowed:
        for r in info.values():
            if r["medium"] not in allowed and r["medium"] != "other":
                warn.append(f"{_lbl(r)} (Medium {r['medium']})")
    warnings = ([f"{len(warn)} Port(s) haben ein Medium, das normalerweise nicht zu „{ctype}“ passt, z. B. " + ", ".join(warn[:3])] if warn else [])

    # Auftrag
    wo = None
    if wo_mode and body.workorder_id:
        wo = workorders._wo_or_404(body.workorder_id, me)
        if wo["status"] not in ("draft", "rework"):
            raise HTTPException(409, "Positionen können nur in Entwürfen oder zurückgewiesenen Aufträgen ergänzt werden")
        workorders._require_role(me, ["planer", "admin"], wo)
    first = info[pairs[0].port_a_id]
    loc_id = first["location_id"] or info[pairs[0].port_b_id]["location_id"]
    title = body.workorder_title.strip() or f"Massenverkabelung {first['hostname']} ↔ {info[pairs[0].port_b_id]['hostname']} ({len(pairs)} Kabel)"
    if wo_mode and not wo and not loc_id and not me.is_global:
        raise HTTPException(400, "Ohne Location an den Geräten kann kein Auftrag in deinem Bereich angelegt werden")
    removals = [f"{c['port']} ↔ {c['other']}" for c in conflicts if not c["removal_order"]]
    sample = [pairs[0], pairs[-1]] if len(pairs) > 1 else pairs
    preview = {
        "count": len(pairs), "skipped": skipped, "type": ctype,
        "cables": [{"from": _lbl(info[p.port_a_id]), "to": _lbl(info[p.port_b_id]), "label": p.cable_label} for p in sample],
        "warnings": warnings, "via": "Patchauftrag" if wo_mode else "direkt",
        "workorder": ({"existing": wo["number"]} if wo else {"new": title}) if wo_mode else None,
        "removals": {"count": len(removals), "cables": removals[:5], "via": "Rückbau-Patchauftrag" if wo_mode else "sofort"} if removals else None,
    }
    if body.dry_run:
        return {"dry_run": True, **preview}

    now = time.time()
    new_wo_id, out_wo, cable_ids = None, None, []
    try:
        if wo_mode:
            if wo:
                wid = wo["id"]
            else:
                wid = new_wo_id = db.execute(
                    """INSERT INTO workorders(number, title, description, status, priority, location_id, note,
                                              openplan_project, openplan_task, openplan_link, created_by, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (workorders._next_number(), title, f"{len(pairs)} x {ctype} (Massenverkabelung)", "draft", "normal", loc_id, "", "", "", "", me.name, now, now))
            with db.transaction() as c:
                n = c.execute("SELECT COUNT(*) AS n FROM workitems WHERE workorder_id = ?", (wid,)).fetchone()["n"]
                for k, p in enumerate(pairs):
                    c.execute("""INSERT INTO workitems(workorder_id, action, port_a_id, port_b_id, cable_label, cable_type, fiber_count, length_m, color, note, idx)
                                 VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                              (wid, "connect", p.port_a_id, p.port_b_id, p.cable_label.strip(), ctype, count, body.length_m, body.color.strip(), body.note.strip(), n + k))
                c.execute("UPDATE workorders SET updated_at = ? WHERE id = ?", (now, wid))
            if conflicts:
                workorders.schedule_cable_removal(me, db.row("SELECT * FROM workorders WHERE id = ?", (wid,)), conflicts)
            w = db.row("SELECT id, number, title, depends_on FROM workorders WHERE id = ?", (wid,))
            dep = db.row("SELECT id, number FROM workorders WHERE id = ?", (w["depends_on"],)) if w["depends_on"] else None
            out_wo = {"id": w["id"], "number": w["number"], "title": w["title"], "new": bool(new_wo_id), "items": len(pairs),
                      "removal_order": {"id": dep["id"], "number": dep["number"]} if dep else None}
        else:
            with db.transaction() as c:                               # alles oder nichts
                for cf in conflicts:
                    cablelog.remove_cable(cf["cable_id"], by=me.name, reason="wizard", c=c)
                for p in pairs:
                    lo, hi = sorted((p.port_a_id, p.port_b_id))
                    cable_ids.append(c.execute(
                        """INSERT INTO cables(port_a_id, port_b_id, cable_label, cable_type, fiber_count, length_m, color, installed_at,
                                              measurement_ref, measurement_ok, note, created_by, created_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (lo, hi, p.cable_label.strip(), ctype, count, body.length_m, body.color.strip(), None, "", None, body.note.strip(), me.name, now)).lastrowid)
    except Exception:
        if new_wo_id:
            db.execute("DELETE FROM workorders WHERE id = ?", (new_wo_id,))
        raise
    audit.log(me.name, "wizard.bulk_cables", "workorder" if out_wo else "cable", (out_wo or {}).get("id", cable_ids[0] if cable_ids else ""),
              f"{len(pairs)} x {ctype}: {_lbl(info[pairs[0].port_a_id])} ↔ {_lbl(info[pairs[0].port_b_id])} …"
              + (f", Auftrag {out_wo['number']}" if out_wo else ", direkt") + (f", Rückbau von {len(removals)} Patches" if removals else ""))
    return {"dry_run": False, **preview, "cable_ids": cable_ids, "workorder": out_wo}


def _lbl(r: dict) -> str:
    return f"{r['hostname']}:{r['name']}"


def _port_label_by_id(pid: int) -> str:
    r = db.row("SELECT d.hostname, p.name FROM ports p JOIN devices d ON d.id = p.device_id WHERE p.id = ?", (pid,))
    return f"{r['hostname']}:{r['name']}" if r else str(pid)


# ── Arbeitsplatz-Assistent ────────────────────────────────────────────────────

@router.post("/workplace")
def workplace_wizard(body: WorkplaceIn, me: Principal = Depends(current_principal)):
    """Neuer Arbeitsplatz an einer Dose: Strecke bis zum Patchfeld, freier Switchport (Vorschlag oder Auswahl), Profil/VLAN →
    Patchauftrag mit „herstellen“ (Patchfeld ↔ Switch, Ziel-Konfiguration am Switchport) und optional „herstellen“ Dose ↔ Endgerät.
    Ist die Dose schon bis zum Switch verbunden, wird nur „Port umkonfigurieren“ angelegt. ``dry_run`` liefert Analyse und Vorschläge."""
    info = workplace.analyse(body.outlet_port_id, me)
    cfg = workplace.target_cfg(body.profile_id, body.cfg)
    user_port = info["user_port"]
    out: dict = {"state": info["state"], "why": info["why"], "path": info["path"], "user_port": workplace.label(user_port),
                 "patch_point": None, "candidates": [], "switch_port": None, "items": [], "warnings": []}
    if info["state"] == "undocumented":
        if body.dry_run:
            return {"dry_run": True, **out}
        raise HTTPException(400, info["why"])

    items: list[dict] = []
    if info["state"] == "connected":
        sp = info["switch_port"]
        out["switch_port"] = {"port_id": sp["id"], "label": workplace.label(sp)} if sp else None
        if sp and cfg:
            items.append({"action": "configure", "port_a_id": sp["id"], "port_b_id": None, "cfg": cfg, "cfg_port_id": sp["id"],
                          "text": f"{workplace.label(sp)} umkonfigurieren → {portcfg.describe(cfg)}"})
        elif not body.dry_run:
            raise HTTPException(400, "Die Dose ist bereits verbunden – für eine Änderung ein Profil oder VLAN wählen")
    else:
        pp = info["patch_point"]
        out["patch_point"] = {"port_id": pp["id"], "label": workplace.label(pp)}
        out["candidates"] = workplace.candidates(pp, me)
        sw_id = body.switch_port_id or (out["candidates"][0]["port_id"] if out["candidates"] else None)
        if not sw_id:
            if body.dry_run:
                out["warnings"].append("Kein freier Switchport am Standort gefunden")
                return {"dry_run": True, **out}
            raise HTTPException(409, "Kein freier Switchport am Standort gefunden – Switchport bitte auswählen")
        sp = workplace._port(sw_id)
        if not sp or sp["type"] not in portcfg.SWITCH_TYPES:
            raise HTTPException(400, "Der gewählte Port gehört zu keinem Switch/Router/Firewall")
        out["switch_port"] = {"port_id": sp["id"], "label": workplace.label(sp)}
        items.append({"action": "connect", "port_a_id": pp["id"], "port_b_id": sp["id"], "cfg": cfg, "cfg_port_id": sp["id"] if cfg else None,
                      "patch_cable": True, "text": f"{workplace.label(pp)} ↔ {workplace.label(sp)}" + (f" · VLAN: {portcfg.describe(cfg)}" if cfg else "")})
    if body.endpoint_port_id:
        ep = workplace._port(body.endpoint_port_id)
        if not ep:
            raise HTTPException(404, "Endgerät-Port nicht gefunden")
        items.append({"action": "connect", "port_a_id": user_port["id"], "port_b_id": ep["id"], "cfg": None, "cfg_port_id": None,
                      "text": f"{workplace.label(user_port)} ↔ {workplace.label(ep)} (Endgerät)"})
    out["items"] = [{"action": i["action"], "text": i["text"]} for i in items]

    # Rechte und Prüfungen wie bei den anderen Assistenten
    site = user_port["site_id"]
    if me.kind != "user" or not me.has_at(site, "planer"):
        raise HTTPException(403, "Für Patchaufträge ist die Rolle „Planer“ am Standort nötig")
    ports = [p for i in items if i["action"] == "connect" for p in (i["port_a_id"], i["port_b_id"])]
    reservations.check(ports, use_reserved=body.use_reserved, by=me.name, workorder_id=body.workorder_id, dry_run=body.dry_run)
    busy = workorders.port_conflicts(ports)
    if busy:
        raise workorders.conflict_error("port_busy", workorders.busy_message(busy).split(". Alten Patch")[0] + ". Bitte einen anderen Port wählen.", busy)
    ctype = check_cable_type(body.cable_type)
    wo = None
    if body.workorder_id:
        wo = workorders._wo_or_404(body.workorder_id, me)
        if wo["status"] not in ("draft", "rework"):
            raise HTTPException(409, "Positionen können nur in Entwürfen oder zurückgewiesenen Aufträgen ergänzt werden")
        workorders._require_role(me, ["planer", "admin"], wo)
    title = body.workorder_title.strip() or f"Arbeitsplatz {workplace.label(user_port)}"
    out["workorder"] = {"existing": wo["number"]} if wo else {"new": title}
    if body.dry_run:
        return {"dry_run": True, **out}

    now = time.time()
    if wo:
        wid = wo["id"]
    else:
        wid = db.execute("""INSERT INTO workorders(number, title, description, status, priority, location_id, note, openplan_project, openplan_task,
                                                   openplan_link, created_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                         (workorders._next_number(), title, f"Arbeitsplatz-Assistent: {workplace.label(user_port)}", "draft", "normal",
                          user_port["location_id"], "", "", "", "", me.name, now, now))
    for i in items:
        if i.get("patch_cable"):                                         # Kabeldaten gehören zum Patchkabel Patchfeld ↔ Switch
            cable = {"cable_label": body.cable_label.strip(), "cable_type": ctype, "length_m": body.length_m, "color": body.color.strip()}
        else:
            cable = {"cable_type": ctype if i["action"] == "connect" else "other"}
        workorders._add_item_raw(wid, i["action"], port_a_id=i["port_a_id"], port_b_id=i["port_b_id"], note=body.note.strip(),
                                 cfg=workplace.cfg_json(i["cfg"]), cfg_port_id=i["cfg_port_id"], **cable)
    w = db.row("SELECT id, number, title FROM workorders WHERE id = ?", (wid,))
    audit.log(me.name, "wizard.workplace", "workorder", wid, f"{w['number']}: " + "; ".join(i["text"] for i in items))
    return {**out, "dry_run": False, "workorder": {"id": w["id"], "number": w["number"], "title": w["title"], "new": not wo}}
