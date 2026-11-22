"""Patchaufträge (WorkOrders) mit Workflow und Positionen (WorkItems).

Rollen:
  planer    – Aufträge anlegen, einreichen (eigene)
  freigeber – Aufträge freigeben/ablehnen, bestätigen/zurückweisen
  techniker – Ausführung starten, Positionen abhaken
  admin     – alles; kann auch direkt Kabel über die masterdata-API setzen
"""
from __future__ import annotations

import json
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .. import access, audit, cablelog, db, openplan
from . import wan
from ..auth import Principal, current_principal
from .catalog import check_cable_type
from ..schemas import (PRIORITIES, WORKITEM_ACTIONS, WORKITEM_STATUSES,
                       WORKORDER_STATUSES, WorkItemExec, WorkItemIn, WorkOrderIn)

router = APIRouter(prefix="/api/workorders", tags=["aufträge"])

# ── Status-Übergänge: {aktueller Status: {aktion: (neuer Status, erlaubte Rollen)}} ──────

TRANSITIONS: dict[str, dict[str, tuple[str, list[str]]]] = {
    "draft":       {"submit":   ("submitted",   ["planer", "admin"])},
    "submitted":   {"approve":  ("approved",    ["freigeber", "admin"]),
                    "reject":   ("rejected",    ["freigeber", "admin"])},
    "approved":    {"start":    ("in_progress", ["techniker", "admin"])},
    "in_progress": {"finish":   ("done",        ["techniker", "admin"])},
    "done":        {"confirm":  ("confirmed",   ["freigeber", "admin"]),
                    "rework":   ("rework",      ["freigeber", "admin"])},
    "rework":      {"start":    ("in_progress", ["techniker", "admin"])},
}

STATUS_LABELS = {
    "draft": "Entwurf", "submitted": "Eingereicht", "approved": "Freigegeben",
    "rejected": "Abgelehnt", "in_progress": "In Ausführung", "done": "Ausgeführt",
    "confirmed": "Bestätigt", "rework": "Nacharbeit",
}

ACTION_LABELS = {"connect": "Verbindung herstellen", "disconnect": "Verbindung trennen", "move": "Verbindung umstecken",
                 "install_device": "Gerät einbauen", "remove_device": "Gerät zurückbauen",
                 "wan_activate": "WAN in Betrieb nehmen", "wan_change": "WAN ändern", "wan_terminate": "WAN kündigen"}
OPEN_STATES = ("draft", "submitted", "approved", "in_progress", "done", "rework")      # Aufträge, die noch nicht abgeschlossen sind


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _next_number() -> str:
    row = db.row("SELECT MAX(CAST(SUBSTR(number,4) AS INTEGER)) AS n FROM workorders WHERE number LIKE 'PA-%'")
    n = (row["n"] or 0) + 1
    return f"PA-{n:04d}"


def _wo_site(w: dict) -> Optional[int]:
    return access.site_of_location(w["location_id"])


def _wo_visible(me: Principal, w: dict) -> bool:
    return access.can_read_site(me, _wo_site(w))


def _require_role(me: Principal, roles: list[str], w: Optional[dict] = None) -> None:
    """Rolle global oder – bei einem Auftrag mit Standort – am Standort des Auftrags."""
    if me.is_admin or me.has(*roles):
        return
    if w is not None and me.has_at(_wo_site(w), *roles):
        return
    raise HTTPException(403, f"Fehlende Rolle (erforderlich: {', '.join(roles)})")


def _check_wo_location(me: Principal, location_id: Optional[int]) -> None:
    """Bereichs-Planer dürfen Aufträge nur für Locations ihres Standorts anlegen."""
    if me.is_global:
        return
    if not me.has_at(access.site_of_location(location_id), "planer"):
        raise HTTPException(403, "Für einen Patchauftrag ist eine Location in deinem Bereich nötig")


def _check_item_ports(me: Principal, body) -> None:
    """Bereichs-Planer dürfen nur Ports ihres Standorts verbinden."""
    if me.is_global:
        return
    for pid in (body.port_a_id, body.port_b_id, body.old_port_b_id):
        if pid and not me.has_at(access.site_of_port(pid), "planer"):
            raise HTTPException(403, "Ein Port liegt außerhalb deines Bereichs")


def _port_label(pid: int) -> str:
    r = db.row("SELECT d.hostname, p.name FROM ports p JOIN devices d ON d.id = p.device_id WHERE p.id = ?", (pid,))
    return f"{r['hostname']}:{r['name']}" if r else f"Port {pid}"


def _pending_removal_order(port_ids: list[int]) -> Optional[dict]:
    """Offener Auftrag, der eine Verbindung an einem dieser Ports ohnehin abbaut (disconnect/move)."""
    ids = [p for p in port_ids if p]
    if not ids:
        return None
    ph = ",".join("?" * len(ids))
    return db.row(f"""SELECT DISTINCT w.* FROM workitems i JOIN workorders w ON w.id = i.workorder_id
                      WHERE i.action IN ('disconnect', 'move') AND w.status IN ({",".join("?" * len(OPEN_STATES))})
                        AND (i.port_a_id IN ({ph}) OR i.port_b_id IN ({ph}) OR i.old_port_b_id IN ({ph}))
                      ORDER BY w.id LIMIT 1""", (*OPEN_STATES, *ids, *ids, *ids))


def port_conflicts(port_ids: list, ignore_pair: Optional[tuple] = None) -> list[dict]:
    """Belegte Ports unter ``port_ids`` (mit dem vorhandenen Kabel) – für die Rückfrage „alten Patch zurückbauen?“."""
    out, seen = [], set()
    for pid in [p for p in port_ids if p]:
        c = db.row("SELECT * FROM cables WHERE port_a_id = ? OR port_b_id = ?", (pid, pid))
        if not c or c["id"] in seen:
            continue
        seen.add(c["id"])
        if ignore_pair and {c["port_a_id"], c["port_b_id"]} == set(ignore_pair):
            continue                                               # genau diese Verbindung besteht schon
        other = c["port_b_id"] if c["port_a_id"] == pid else c["port_a_id"]
        pend = _pending_removal_order([c["port_a_id"], c["port_b_id"]])
        out.append({"port_id": pid, "port": _port_label(pid), "cable_id": c["id"], "cable_label": c["cable_label"],
                    "cable_type": c["cable_type"], "other_port_id": other, "other": _port_label(other),
                    "removal_order": {"id": pend["id"], "number": pend["number"]} if pend else None})
    return out


def conflict_error(code: str, message: str, conflicts: list) -> HTTPException:
    """409 mit strukturierter Beschreibung; die Oberfläche stellt daraus die Rückfrage."""
    return HTTPException(409, detail={"code": code, "message": message, "conflicts": conflicts})


def busy_message(conflicts: list) -> str:
    parts = [f"{c['port']} ist mit {c['other']} verbunden" + (f" (Kabel {c['cable_label']})" if c["cable_label"] else "") for c in conflicts]
    return "; ".join(parts) + ". Alten Patch zurückbauen? Dafür wird automatisch ein Rückbau-Patchauftrag angelegt."


def removal_order_for(me: Principal, w: dict) -> dict:
    """Rückbau-Auftrag, der vor ``w`` ausgeführt werden muss. Er wird bei Bedarf angelegt und als Voraussetzung von ``w`` eingetragen
    (``w`` kann erst starten, wenn der Rückbau bestätigt ist). Ein vorhandener Entwurf wird wiederverwendet."""
    w = db.row("SELECT * FROM workorders WHERE id = ?", (w["id"],))
    dep = db.row("SELECT * FROM workorders WHERE id = ?", (w["depends_on"],)) if w["depends_on"] else None
    if dep and dep["status"] in ("draft", "rework"):
        return dep
    now = time.time()
    rid = db.execute(
        """INSERT INTO workorders(number, title, description, status, priority, location_id, note, openplan_project, openplan_task,
                                  openplan_link, created_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (_next_number(), f"Rückbau vor {w['number']}",
         f"Automatisch angelegt: Alte Patches bzw. Geräte zurückbauen, bevor {w['number']} ({w['title']}) ausgeführt werden kann.",
         "draft", w["priority"], w["location_id"], "", "", "", "", me.name, now, now))
    db.execute("UPDATE workorders SET depends_on = ?, updated_at = ? WHERE id = ?", (rid, now, w["id"]))
    rem = db.row("SELECT * FROM workorders WHERE id = ?", (rid,))
    audit.log(me.name, "workorder.create_removal", "workorder", rid, f"{rem['number']} für {w['number']}")
    return rem


def _link_dependency(w: dict, other: dict) -> None:
    if other["id"] != w["id"] and not db.row("SELECT depends_on FROM workorders WHERE id = ?", (w["id"],))["depends_on"]:
        db.execute("UPDATE workorders SET depends_on = ?, updated_at = ? WHERE id = ?", (other["id"], time.time(), w["id"]))


def _add_item_raw(wid: int, action: str, **cols) -> None:
    n = db.row("SELECT COUNT(*) AS n FROM workitems WHERE workorder_id = ?", (wid,))["n"]
    names = ["workorder_id", "action", "idx"] + list(cols)
    db.execute(f"INSERT INTO workitems({', '.join(names)}) VALUES ({','.join('?' * len(names))})", (wid, action, n, *cols.values()))
    db.execute("UPDATE workorders SET updated_at = ? WHERE id = ?", (time.time(), wid))


def schedule_cable_removal(me: Principal, w: dict, conflicts: list) -> None:
    """Alte Patches der Konflikte per Rückbau-Auftrag entfernen; ohnehin geplante Rückbauten werden nur als Voraussetzung verknüpft."""
    for c in conflicts:
        if c["removal_order"]:
            _link_dependency(w, db.row("SELECT * FROM workorders WHERE id = ?", (c["removal_order"]["id"],)))
            continue
        rem = removal_order_for(me, w)
        if not db.row("SELECT 1 AS x FROM workitems WHERE workorder_id = ? AND action = 'disconnect' AND port_a_id = ?", (rem["id"], c["port_id"])):
            _add_item_raw(rem["id"], "disconnect", port_a_id=c["port_id"], port_b_id=c["other_port_id"],
                          cable_label=c["cable_label"], cable_type=c["cable_type"], note=f"Alter Patch: {c['port']} ↔ {c['other']}")


def schedule_device_removal(me: Principal, w: dict, devices: list[dict]) -> None:
    """Geräte per Rückbau-Auftrag entfernen (HE wird frei); bereits geplante Rückbauten werden nur als Voraussetzung verknüpft."""
    for d in devices:
        pend = db.row("""SELECT DISTINCT w.* FROM workitems i JOIN workorders w ON w.id = i.workorder_id
                         WHERE i.action = 'remove_device' AND i.device_id = ? AND w.status IN (%s) LIMIT 1""" % ",".join("?" * len(OPEN_STATES)),
                      (d["id"], *OPEN_STATES))
        if pend:
            _link_dependency(w, pend)
            continue
        rem = removal_order_for(me, w)
        _add_item_raw(rem["id"], "remove_device", device_id=d["id"], note=f"Rückbau {d['hostname']}")


def unique_hostname(base: str) -> str:
    name, n = base, 1
    while db.row("SELECT id FROM devices WHERE hostname = ? COLLATE NOCASE", (name,)):
        n += 1
        name = f"{base}-{n}"
    return name


def finalize_hostname(did: int) -> bool:
    """Ein Ersatzgerät übernimmt seinen Wunschnamen (``planned_hostname``), sobald der Name frei ist."""
    d = db.row("SELECT id, planned_hostname FROM devices WHERE id = ?", (did,))
    if not d or not d["planned_hostname"]:
        return False
    if db.row("SELECT id FROM devices WHERE hostname = ? COLLATE NOCASE AND id <> ?", (d["planned_hostname"], did)):
        return False
    db.execute("UPDATE devices SET hostname = ?, planned_hostname = '', updated_at = ? WHERE id = ?", (d["planned_hostname"], time.time(), did))
    return True


def retire_device(did: int, by: str = "", workorder_id: Optional[int] = None) -> int:
    """Gerät ausbauen: Kabel an allen Ports entfernen, Status „außer Betrieb“, HE-Position frei. Das Gerät bleibt als Historie erhalten,
    gibt aber seinen Hostnamen frei (er wird zu „<Name>~zurückgebaut-<Datum>“, der ursprüngliche Name steht in ``former_hostname``);
    wartet ein Ersatzgerät auf den Namen, übernimmt es ihn jetzt."""
    n = cablelog.remove("port_a_id IN (SELECT id FROM ports WHERE device_id = ?) OR port_b_id IN (SELECT id FROM ports WHERE device_id = ?)",
                        (did, did), by=by, workorder_id=workorder_id, reason="retire")
    d = db.row("SELECT hostname, former_hostname FROM devices WHERE id = ?", (did,))
    now = time.time()
    if d and not d["former_hostname"]:                                       # erstmaliger Rückbau: Namen freigeben
        new_name = unique_hostname(f"{d['hostname']}~zurückgebaut-{time.strftime('%Y%m%d', time.localtime(now))}")
        db.execute("UPDATE devices SET hostname = ?, former_hostname = ?, retired_at = ? WHERE id = ?", (new_name, d["hostname"], now, did))
    db.execute("UPDATE devices SET status = 'retired', rack_position = NULL, updated_at = ? WHERE id = ?", (now, did))
    if d and not d["former_hostname"]:
        for r in db.rows("SELECT id FROM devices WHERE planned_hostname = ? COLLATE NOCASE", (d["hostname"],)):
            finalize_hostname(r["id"])
    return n


def _resolve_item_conflicts(me: Principal, w: dict, body) -> None:
    """Neue Verbindung auf belegtem Port: Rückfrage (409) – mit ``remove_old`` wird der Rückbau automatisch als Auftrag angelegt."""
    if body.action == "connect":
        conflicts = port_conflicts([body.port_a_id, body.port_b_id], ignore_pair=(body.port_a_id, body.port_b_id))
    elif body.action == "move":
        conflicts = port_conflicts([body.port_b_id])
    else:
        return
    if not conflicts:
        return
    if not body.remove_old and any(not c["removal_order"] for c in conflicts):
        raise conflict_error("port_busy", busy_message([c for c in conflicts if not c["removal_order"]]), conflicts)
    schedule_cable_removal(me, w, conflicts)


def _check_item_wan(me: Principal, body) -> dict:
    """WAN-Positionen: Verbindung/Rechte/Zustand prüfen; liefert die bereinigten Änderungswerte."""
    if not body.action.startswith("wan_"):
        return {}
    return wan.validate_item(me, body.action, body.wan_link_id, body.wan_patch)


def _check_item_device(me: Principal, body) -> None:
    if body.action not in ("install_device", "remove_device"):
        return
    d = db.row("SELECT id, location_id FROM devices WHERE id = ?", (body.device_id,)) if body.device_id else None
    if not d:
        raise HTTPException(400, "Für Einbau/Rückbau eines Geräts muss ein vorhandenes Gerät gewählt werden")
    if not me.is_global and not me.has_at(access.site_of_location(d["location_id"]), "planer"):
        raise HTTPException(403, "Das Gerät liegt außerhalb deines Bereichs")


def _wo_or_404(wid: int, me: Optional[Principal] = None) -> dict:
    w = db.row("SELECT * FROM workorders WHERE id = ?", (wid,))
    if not w or (me is not None and not _wo_visible(me, w)):
        raise HTTPException(404, "Patchauftrag nicht gefunden")
    return w


def _item_or_404(iid: int, wid: int) -> dict:
    item = db.row("SELECT * FROM workitems WHERE id = ? AND workorder_id = ?", (iid, wid))
    if not item:
        raise HTTPException(404, "Position nicht gefunden")
    return item


def _port_info(pid: Optional[int]) -> Optional[dict]:
    if not pid:
        return None
    r = db.row(
        "SELECT p.id, p.name, p.device_id, d.hostname FROM ports p JOIN devices d ON d.id = p.device_id WHERE p.id = ?",
        (pid,)
    )
    return {"id": r["id"], "name": r["name"], "device_id": r["device_id"], "device_hostname": r["hostname"]} if r else None


def _device_info(did: Optional[int]) -> Optional[dict]:
    if not did:
        return None
    r = db.row("SELECT id, hostname, type, status FROM devices WHERE id = ?", (did,))
    return dict(r) if r else None


def _wan_info(lid: Optional[int]) -> Optional[dict]:
    r = db.row("SELECT * FROM wan_links WHERE id = ?", (lid,)) if lid else None
    return {k: v for k, v in wan.out(r).items() if k in ("id", "name", "status", "status_label", "provider", "circuit_id", "site_a", "site_b",
                                                          "bandwidth_down", "bandwidth_up", "technology_label")} if r else None


def _wan_patch(raw) -> dict:
    try:
        return json.loads(raw) if raw else {}
    except ValueError:
        return {}


def _item_out(item: dict) -> dict:
    return {
        "id":           item["id"],
        "workorder_id": item["workorder_id"],
        "action":       item["action"],
        "action_label": ACTION_LABELS.get(item["action"], item["action"]),
        "device":       _device_info(item.get("device_id")),
        "wan":          _wan_info(item.get("wan_link_id")),
        "wan_patch":    _wan_patch(item.get("wan_patch")),
        "port_a":       _port_info(item["port_a_id"]),
        "port_b":       _port_info(item["port_b_id"]),
        "old_port_b":   _port_info(item["old_port_b_id"]),
        "cable_label":  item["cable_label"],
        "cable_type":   item["cable_type"],
        "fiber_count":  item["fiber_count"],
        "length_m":     item["length_m"],
        "color":        item["color"],
        "note":         item["note"],
        "item_status":  item["item_status"],
        "deviation_note": item["deviation_note"],
        "executed_by":  item["executed_by"],
        "executed_at":  item["executed_at"],
        "idx":          item["idx"],
    }


def _progress(wid: int) -> dict:
    r = db.row("""SELECT COUNT(*) AS total, SUM(item_status = 'done') AS done, SUM(item_status = 'deviation') AS deviation
                  FROM workitems WHERE workorder_id = ?""", (wid,))
    return {"total": r["total"] or 0, "done": r["done"] or 0, "deviation": r["deviation"] or 0}


def _openplan_out(w: dict) -> dict:
    return {"linked": bool(w.get("openplan_project") and w.get("openplan_task")), "project": w.get("openplan_project") or "", "task": w.get("openplan_task") or "",
            "link": w.get("openplan_link") or "", "status": w.get("openplan_status") or "", "percent": w.get("openplan_percent"),
            "synced_at": w.get("openplan_synced_at"), "error": w.get("openplan_error") or ""}


def _assignee(uid: Optional[int]) -> Optional[dict]:
    if not uid:
        return None
    r = db.row("SELECT id, username, full_name FROM users WHERE id = ?", (uid,))
    return dict(r) if r else None


def _wo_ref(wid: Optional[int]) -> Optional[dict]:
    """Voraussetzung eines Auftrags (Rückbau): ``blocking`` solange sie nicht bestätigt ist."""
    if not wid:
        return None
    r = db.row("SELECT id, number, title, status FROM workorders WHERE id = ?", (wid,))
    if not r:
        return None
    return {**r, "status_label": STATUS_LABELS.get(r["status"], r["status"]), "blocking": r["status"] != "confirmed"}


def _wo_out(w: dict, with_items: bool = False) -> dict:
    loc = None
    if w["location_id"]:
        loc = db.row("SELECT id, name, kind FROM locations WHERE id = ?", (w["location_id"],))
    out = {
        "id":           w["id"],
        "number":       w["number"],
        "title":        w["title"],
        "description":  w["description"],
        "status":       w["status"],
        "status_label": STATUS_LABELS.get(w["status"], w["status"]),
        "priority":     w["priority"],
        "location":     dict(loc) if loc else None,
        "planned_from": w["planned_from"],
        "planned_to":   w["planned_to"],
        "note":         w["note"],
        "openplan_project": w["openplan_project"],
        "openplan_task":    w["openplan_task"],
        "openplan_link":    w["openplan_link"],
        "created_by":   w["created_by"],
        "created_at":   w["created_at"],
        "updated_at":   w["updated_at"],
        "progress":     _progress(w["id"]),
        "openplan":     _openplan_out(w),
        "assigned_to":  _assignee(w.get("assigned_to")),
        "assigned_at":  w.get("assigned_at"),
        "depends_on":   _wo_ref(w.get("depends_on")),
        "required_by":  [dict(r) for r in db.rows("SELECT id, number, status FROM workorders WHERE depends_on = ? ORDER BY id", (w["id"],))],
    }
    if with_items:
        out["items"] = [_item_out(i) for i in db.rows(
            "SELECT * FROM workitems WHERE workorder_id = ? ORDER BY idx, id", (w["id"],)
        )]
    return out


def _apply_workorder(w: dict, me: Principal) -> None:
    """Führt alle Positionen eines bestätigten Auftrags auf den Kabelbestand aus."""
    items = db.rows("SELECT * FROM workitems WHERE workorder_id = ? ORDER BY idx, id", (w["id"],))
    for item in items:
        if item["action"] in ("connect", "move") and item["item_status"] != "deviation":      # verkabelt = eingebaut
            for pid in (item["port_a_id"], item["port_b_id"]):
                if pid:
                    db.execute("UPDATE devices SET status = 'active', updated_at = ? WHERE status = 'planned' "
                               "AND id = (SELECT device_id FROM ports WHERE id = ?)", (time.time(), pid))
        if item["item_status"] == "deviation":
            continue  # Abweichungen nicht automatisch ausführen
        action = item["action"]
        a_id   = item["port_a_id"]
        b_id   = item["port_b_id"]

        if action == "connect" and a_id and b_id:
            # bestehende Verbindungen an beiden Ports entfernen
            cablelog.remove_at_ports([a_id, b_id], by=me.name, workorder_id=w["id"], reason="workorder")
            lo, hi = (a_id, b_id) if a_id < b_id else (b_id, a_id)
            db.execute(
                """INSERT INTO cables(port_a_id, port_b_id, cable_label, cable_type, fiber_count, length_m,
                                      color, installed_at, measurement_ref, measurement_ok, note,
                                      created_by, created_at, workorder_id)
                   VALUES (?,?,?,?,?,?,?,NULL,'',NULL,?,?,?,?)""",
                (lo, hi, item["cable_label"], item["cable_type"], item["fiber_count"], item["length_m"],
                 item["color"], item["note"], me.name, time.time(), w["id"]),
            )

        elif action.startswith("wan_"):
            wan.apply_item(item)

        elif action == "install_device" and item["device_id"]:
            db.execute("UPDATE devices SET status = 'active', updated_at = ? WHERE id = ? AND status = 'planned'", (time.time(), item["device_id"]))
            finalize_hostname(item["device_id"])

        elif action == "remove_device" and item["device_id"]:
            retire_device(item["device_id"], by=me.name, workorder_id=w["id"])

        elif action == "disconnect" and a_id:
            cablelog.remove_at_ports([a_id, b_id], by=me.name, workorder_id=w["id"], reason="workorder")

        elif action == "move" and a_id and b_id:
            # alten Zielport lösen, neuen verbinden
            cablelog.remove_at_ports([a_id, item["old_port_b_id"], b_id], by=me.name, workorder_id=w["id"], reason="workorder")
            lo, hi = (a_id, b_id) if a_id < b_id else (b_id, a_id)
            db.execute(
                """INSERT INTO cables(port_a_id, port_b_id, cable_label, cable_type, fiber_count, length_m,
                                      color, installed_at, measurement_ref, measurement_ok, note,
                                      created_by, created_at, workorder_id)
                   VALUES (?,?,?,?,?,?,?,NULL,'',NULL,?,?,?,?)""",
                (lo, hi, item["cable_label"], item["cable_type"], item["fiber_count"], item["length_m"],
                 item["color"], item["note"], me.name, time.time(), w["id"]),
            )


# ── CRUD Aufträge ─────────────────────────────────────────────────────────────

@router.get("")
def list_workorders(
    status: Optional[str] = None,
    q: Optional[str] = None,
    assigned: Optional[str] = None,
    me: Principal = Depends(current_principal),
):
    where, args = [], []
    if assigned:                                         # "me" oder Benutzer-ID
        uid = me.user_id if assigned == "me" else (int(assigned) if assigned.isdigit() else None)
        if uid is None:
            return []
        where.append("assigned_to = ?"); args.append(uid)
    if status and status in WORKORDER_STATUSES:
        where.append("status = ?"); args.append(status)
    if q:
        where.append("(number LIKE ? OR title LIKE ? OR created_by LIKE ?)"); args += [f"%{q}%"] * 3
    w = ("WHERE " + " AND ".join(where)) if where else ""
    rows = db.rows(f"SELECT * FROM workorders {w} ORDER BY id DESC", tuple(args))
    return [_wo_out(r) for r in rows if _wo_visible(me, r)]


@router.post("", status_code=201)
def create_workorder(body: WorkOrderIn, me: Principal = Depends(current_principal)):
    if not (me.has("planer") or me.has_at(access.site_of_location(body.location_id), "planer")):
        raise HTTPException(403, "Fehlende Rolle (erforderlich: planer)")
    _check_wo_location(me, body.location_id)
    if body.priority not in PRIORITIES:
        raise HTTPException(400, f"Ungültige Priorität: {body.priority}")
    now = time.time()
    wid = db.execute(
        """INSERT INTO workorders(number, title, description, status, priority, location_id,
                                  planned_from, planned_to, note, openplan_project, openplan_task, openplan_link,
                                  created_by, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (_next_number(), body.title.strip(), body.description.strip(), "draft", body.priority,
         body.location_id, body.planned_from, body.planned_to, body.note.strip(),
         body.openplan_project.strip(), body.openplan_task.strip(), body.openplan_link.strip(),
         me.name, now, now),
    )
    audit.log(me.name, "workorder.create", "workorder", wid, body.title)
    return _wo_out(db.row("SELECT * FROM workorders WHERE id = ?", (wid,)), with_items=True)


@router.get("/{wid}")
def get_workorder(wid: int, me: Principal = Depends(current_principal)):
    return _wo_out(_wo_or_404(wid, me), with_items=True)


@router.put("/{wid}")
def update_workorder(wid: int, body: WorkOrderIn, me: Principal = Depends(current_principal)):
    w = _wo_or_404(wid, me)
    if w["status"] not in ("draft", "rework"):
        raise HTTPException(409, "Nur Entwürfe und zurückgewiesene Aufträge können bearbeitet werden")
    _require_role(me, ["planer", "admin"], w)
    _check_wo_location(me, body.location_id)
    if body.priority not in PRIORITIES:
        raise HTTPException(400, f"Ungültige Priorität: {body.priority}")
    db.execute(
        """UPDATE workorders SET title=?, description=?, priority=?, location_id=?, planned_from=?, planned_to=?,
                                 note=?, openplan_project=?, openplan_task=?, openplan_link=?, updated_at=?
           WHERE id=?""",
        (body.title.strip(), body.description.strip(), body.priority, body.location_id,
         body.planned_from, body.planned_to, body.note.strip(),
         body.openplan_project.strip(), body.openplan_task.strip(), body.openplan_link.strip(),
         time.time(), wid),
    )
    audit.log(me.name, "workorder.update", "workorder", wid, body.title)
    return _wo_out(db.row("SELECT * FROM workorders WHERE id = ?", (wid,)), with_items=True)


@router.delete("/{wid}")
def delete_workorder(wid: int, me: Principal = Depends(current_principal)):
    w = _wo_or_404(wid, me)
    if w["status"] not in ("draft", "rejected"):
        raise HTTPException(409, "Nur Entwürfe oder abgelehnte Aufträge können gelöscht werden")
    _require_role(me, ["planer", "admin"], w)
    db.execute("DELETE FROM workorders WHERE id = ?", (wid,))
    audit.log(me.name, "workorder.delete", "workorder", wid, w["number"])
    return {"ok": True}


# ── Status-Übergänge ─────────────────────────────────────────────────────────

@router.post("/{wid}/transition/{action}")
def transition(wid: int, action: str, me: Principal = Depends(current_principal)):
    w = _wo_or_404(wid, me)
    trans = TRANSITIONS.get(w["status"], {})
    if action not in trans:
        raise HTTPException(409,
            f"Aktion '{action}' nicht möglich bei Status '{STATUS_LABELS.get(w['status'], w['status'])}' "
            f"(möglich: {', '.join(trans.keys()) or '–'})")
    new_status, roles = trans[action]
    _require_role(me, roles, w)
    if action == "start":
        dep = _wo_ref(w["depends_on"])
        if dep and dep["blocking"]:
            raise HTTPException(409, f"Vor dem Start muss der Rückbau-Auftrag {dep['number']} bestätigt sein (aktuell: {dep['status_label']})")

    if action == "confirm":
        _apply_workorder(w, me)
        audit.log(me.name, "workorder.confirm", "workorder", wid, w["number"])

    db.execute("UPDATE workorders SET status = ?, updated_at = ? WHERE id = ?", (new_status, time.time(), wid))
    audit.log(me.name, f"workorder.{action}", "workorder", wid, w["number"])
    openplan.schedule_sync(wid, me.name)
    return _wo_out(db.row("SELECT * FROM workorders WHERE id = ?", (wid,)), with_items=True)


# ── Positionen (WorkItems) ────────────────────────────────────────────────────

@router.get("/{wid}/items")
def list_items(wid: int, me: Principal = Depends(current_principal)):
    _wo_or_404(wid, me)
    return [_item_out(i) for i in db.rows(
        "SELECT * FROM workitems WHERE workorder_id = ? ORDER BY idx, id", (wid,)
    )]


@router.post("/{wid}/items", status_code=201)
def add_item(wid: int, body: WorkItemIn, me: Principal = Depends(current_principal)):
    w = _wo_or_404(wid, me)
    if w["status"] not in ("draft", "rework"):
        raise HTTPException(409, "Positionen können nur in Entwürfen oder zurückgewiesenen Aufträgen ergänzt werden")
    _require_role(me, ["planer", "admin"], w)
    _check_item_ports(me, body)
    if body.action not in WORKITEM_ACTIONS:
        raise HTTPException(400, f"Ungültige Aktion: {body.action}")
    _check_item_device(me, body)
    checked = _check_item_wan(me, body)
    wan_patch = json.dumps(checked, ensure_ascii=False) if body.action == "wan_change" else ""
    body.cable_type = check_cable_type(body.cable_type)
    _resolve_item_conflicts(me, w, body)
    iid = db.execute(
        """INSERT INTO workitems(workorder_id, action, device_id, port_a_id, port_b_id, old_port_b_id,
                                  cable_label, cable_type, fiber_count, length_m, color, note, idx, wan_link_id, wan_patch)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (wid, body.action, body.device_id, body.port_a_id, body.port_b_id, body.old_port_b_id,
         body.cable_label.strip(), body.cable_type, body.fiber_count, body.length_m,
         body.color.strip(), body.note.strip(), body.idx, body.wan_link_id if body.action.startswith("wan_") else None, wan_patch),
    )
    db.execute("UPDATE workorders SET updated_at = ? WHERE id = ?", (time.time(), wid))
    audit.log(me.name, "workitem.add", "workorder", wid, f"item {iid}")
    return _item_out(db.row("SELECT * FROM workitems WHERE id = ?", (iid,)))


@router.put("/{wid}/items/{iid}")
def update_item(wid: int, iid: int, body: WorkItemIn, me: Principal = Depends(current_principal)):
    w = _wo_or_404(wid, me)
    if w["status"] not in ("draft", "rework"):
        raise HTTPException(409, "Positionen können nur in Entwürfen oder zurückgewiesenen Aufträgen bearbeitet werden")
    _require_role(me, ["planer", "admin"], w)
    _check_item_ports(me, body)
    _item_or_404(iid, wid)
    if body.action not in WORKITEM_ACTIONS:
        raise HTTPException(400, f"Ungültige Aktion: {body.action}")
    _check_item_device(me, body)
    checked = _check_item_wan(me, body)
    wan_patch = json.dumps(checked, ensure_ascii=False) if body.action == "wan_change" else ""
    body.cable_type = check_cable_type(body.cable_type)
    _resolve_item_conflicts(me, w, body)
    db.execute(
        """UPDATE workitems SET action=?, device_id=?, port_a_id=?, port_b_id=?, old_port_b_id=?,
                                cable_label=?, cable_type=?, fiber_count=?, length_m=?,
                                color=?, note=?, idx=?, wan_link_id=?, wan_patch=? WHERE id=?""",
        (body.action, body.device_id, body.port_a_id, body.port_b_id, body.old_port_b_id,
         body.cable_label.strip(), body.cable_type, body.fiber_count, body.length_m,
         body.color.strip(), body.note.strip(), body.idx, body.wan_link_id if body.action.startswith("wan_") else None, wan_patch, iid),
    )
    db.execute("UPDATE workorders SET updated_at = ? WHERE id = ?", (time.time(), wid))
    audit.log(me.name, "workitem.update", "workorder", wid, f"item {iid}")
    return _item_out(db.row("SELECT * FROM workitems WHERE id = ?", (iid,)))


@router.delete("/{wid}/items/{iid}")
def delete_item(wid: int, iid: int, me: Principal = Depends(current_principal)):
    w = _wo_or_404(wid, me)
    if w["status"] not in ("draft", "rework"):
        raise HTTPException(409, "Positionen können nur in Entwürfen oder zurückgewiesenen Aufträgen gelöscht werden")
    _require_role(me, ["planer", "admin"], w)
    _item_or_404(iid, wid)
    db.execute("DELETE FROM workitems WHERE id = ?", (iid,))
    db.execute("UPDATE workorders SET updated_at = ? WHERE id = ?", (time.time(), wid))
    audit.log(me.name, "workitem.delete", "workorder", wid, f"item {iid}")
    return {"ok": True}


@router.post("/{wid}/items/{iid}/execute")
def execute_item(wid: int, iid: int, body: WorkItemExec, me: Principal = Depends(current_principal)):
    """Techniker hakt eine Position ab (erledigt oder Abweichung)."""
    w = _wo_or_404(wid, me)
    if w["status"] != "in_progress":
        raise HTTPException(409, "Positionen können nur bei Status 'In Ausführung' abgehakt werden")
    _require_role(me, ["techniker", "admin"], w)
    item = _item_or_404(iid, wid)
    if body.item_status not in ("done", "deviation"):
        raise HTTPException(400, "item_status muss 'done' oder 'deviation' sein")
    db.execute(
        """UPDATE workitems SET item_status=?, deviation_note=?, executed_by=?, executed_at=? WHERE id=?""",
        (body.item_status, body.deviation_note.strip(), me.name, time.time(), iid),
    )
    db.execute("UPDATE workorders SET updated_at = ? WHERE id = ?", (time.time(), wid))
    audit.log(me.name, f"workitem.{body.item_status}", "workorder", wid, f"item {iid}")
    openplan.schedule_sync(wid, me.name)
    return _item_out(db.row("SELECT * FROM workitems WHERE id = ?", (iid,)))


@router.post("/{wid}/items/{iid}/reopen")
def reopen_item(wid: int, iid: int, me: Principal = Depends(current_principal)):
    """Abhakung einer Position rückgängig machen (nur in in_progress)."""
    w = _wo_or_404(wid, me)
    if w["status"] != "in_progress":
        raise HTTPException(409, "Nur bei Status 'In Ausführung' möglich")
    _require_role(me, ["techniker", "admin"], w)
    _item_or_404(iid, wid)
    db.execute("UPDATE workitems SET item_status='open', deviation_note='', executed_by='', executed_at=NULL WHERE id=?", (iid,))
    db.execute("UPDATE workorders SET updated_at = ? WHERE id = ?", (time.time(), wid))
    openplan.schedule_sync(wid, me.name)
    return _item_out(db.row("SELECT * FROM workitems WHERE id = ?", (iid,)))



# ── Arbeitslisten: Sammelaktionen und Export ──────────────────────────────────

class BulkItemAction(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=2000)
    action: str                                  # execute | reopen | delete
    item_status: str = "done"                    # bei execute: done | deviation
    deviation_note: str = ""


@router.post("/{wid}/items/bulk")
def bulk_items(wid: int, body: BulkItemAction, me: Principal = Depends(current_principal)):
    """Mehrere Positionen auf einmal abhaken, zurücksetzen oder (im Entwurf) löschen – für große Arbeitslisten."""
    w = _wo_or_404(wid, me)
    if body.action not in ("execute", "reopen", "delete"):
        raise HTTPException(400, "action: execute, reopen oder delete")
    ids = sorted(set(body.ids))
    ph = ",".join("?" * len(ids))
    found = {r["id"] for r in db.rows(f"SELECT id FROM workitems WHERE workorder_id = ? AND id IN ({ph})", (wid, *ids))}
    if found != set(ids):
        raise HTTPException(404, "Mindestens eine Position gehört nicht zu diesem Auftrag")
    now = time.time()
    if body.action == "delete":
        if w["status"] not in ("draft", "rework"):
            raise HTTPException(409, "Positionen können nur in Entwürfen oder zurückgewiesenen Aufträgen gelöscht werden")
        _require_role(me, ["planer", "admin"], w)
        db.execute(f"DELETE FROM workitems WHERE id IN ({ph})", tuple(ids))
    else:
        if w["status"] != "in_progress":
            raise HTTPException(409, "Positionen können nur bei Status 'In Ausführung' abgehakt oder zurückgesetzt werden")
        _require_role(me, ["techniker", "admin"], w)
        if body.action == "execute":
            if body.item_status not in ("done", "deviation"):
                raise HTTPException(400, "item_status muss 'done' oder 'deviation' sein")
            if body.item_status == "deviation" and not body.deviation_note.strip():
                raise HTTPException(400, "Bitte eine Abweichungsnotiz angeben")
            db.execute(f"UPDATE workitems SET item_status = ?, deviation_note = ?, executed_by = ?, executed_at = ? WHERE id IN ({ph})",
                       (body.item_status, body.deviation_note.strip(), me.name, now, *ids))
        else:
            db.execute(f"UPDATE workitems SET item_status = 'open', deviation_note = '', executed_by = '', executed_at = NULL WHERE id IN ({ph})", tuple(ids))
    db.execute("UPDATE workorders SET updated_at = ? WHERE id = ?", (now, wid))
    audit.log(me.name, f"workitem.bulk_{body.action}", "workorder", wid, f"{len(ids)} Positionen" + (f" ({body.item_status})" if body.action == "execute" else ""))
    openplan.schedule_sync(wid, me.name)
    return _wo_out(db.row("SELECT * FROM workorders WHERE id = ?", (wid,)), with_items=True)


def worklist_csv(w: dict) -> str:
    """Arbeitsliste eines Auftrags als CSV-Text (Semikolon): eine Zeile je Position mit Spalte zum Abhaken."""
    import csv as _csv
    import io as _io
    buf = _io.StringIO()
    wr = _csv.writer(buf, delimiter=";")
    wr.writerow(["Auftrag", w["number"], w["title"], STATUS_LABELS.get(w["status"], w["status"])])
    wr.writerow([])
    wr.writerow(["Nr", "Aktion", "Gerät/Port A", "Gerät/Port B", "Kabelnummer", "Kabelart", "Länge (m)", "Farbe", "Notiz", "Status", "Erledigt von", "Erledigt am", "erledigt ☐"])
    for n, it in enumerate(db.rows("SELECT * FROM workitems WHERE workorder_id = ? ORDER BY idx, id", (w["id"],)), 1):
        o = _item_out(it)
        a = f"{o['port_a']['device_hostname']}:{o['port_a']['name']}" if o["port_a"] else (o["device"]["hostname"] if o["device"] else "")
        b = f"{o['port_b']['device_hostname']}:{o['port_b']['name']}" if o["port_b"] else ""
        done = time.strftime("%d.%m.%Y %H:%M", time.localtime(it["executed_at"])) if it["executed_at"] else ""
        wr.writerow([n, o["action_label"], a, b, it["cable_label"], it["cable_type"] if it["cable_type"] != "other" else "", it["length_m"] or "",
                     it["color"], it["note"], {"open": "offen", "done": "erledigt", "deviation": "Abweichung"}.get(it["item_status"], ""), it["executed_by"], done, ""])
    return buf.getvalue()


@router.get("/{wid}/export")
def export_workorder(wid: int, me: Principal = Depends(current_principal)):
    """Arbeitsliste als CSV (Semikolon, UTF-8 mit BOM – öffnet direkt in Excel): eine Zeile je Position mit Spalte zum Abhaken."""
    from fastapi.responses import Response
    w = _wo_or_404(wid, me)
    audit.log(me.name, "workorder.export", "workorder", wid, w["number"])
    return Response("\ufeff" + worklist_csv(w), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{w["number"]}-arbeitsliste.csv"'})
