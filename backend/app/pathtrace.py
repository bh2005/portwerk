"""Pfad-Verfolgung: vollständige Kette ab einem Port in beide Richtungen – Kabel, Patchfeld (vorn ↔ hinten), Kabel … bis zum aktiven
Gerät oder einem offenen Ende. Je Station Ort/HE, je Kabel die Kabeldaten, je Port geplante Änderungen und Reservierungen,
an den Enden der LLDP/CDP-Abgleich (sieht das eine Ende wirklich das andere?).
"""
from __future__ import annotations

from typing import Optional

from . import access, db, reservations
from .auth import Principal
from .compare import THROUGH_TYPES, norm_port, short_host

MAX_STEPS = 60
ACTIVE_FIRST = ("switch", "router", "firewall")                     # diese Seite steht links, wenn nur ein Ende so ein Gerät ist
ACTION_LABELS = {"connect": "herstellen", "disconnect": "trennen", "move": "umstecken"}


def _port(pid: int) -> Optional[dict]:
    return db.row("""SELECT p.id, p.name, p.peer_port_id, d.id AS device_id, d.hostname, d.type, d.status, d.location_id, d.rack_position,
                            d.mgmt_ip, d.neighbors_at, l.site_id
                     FROM ports p JOIN devices d ON d.id = p.device_id LEFT JOIN locations l ON l.id = d.location_id WHERE p.id = ?""", (pid,))


def _cable(pid: int) -> Optional[dict]:
    return db.row("SELECT * FROM cables WHERE port_a_id = ? OR port_b_id = ?", (pid, pid))


def _walk(start: dict, first: str) -> tuple[list, str]:
    """Von ``start`` aus abwechselnd Kabel/Durchschleifung folgen. Liefert [(Verbindung, Port), …] und den Grund für das Ende."""
    out, cur, step, seen = [], start, first, {start["id"]}
    for _ in range(MAX_STEPS):
        if step == "through":
            if cur["type"] not in THROUGH_TYPES:
                return out, ""                                          # aktives Gerät: reguläres Ende
            if not cur["peer_port_id"]:
                return out, "open"                                      # Patchfeld/Dose ohne dokumentierte Gegenseite
            nxt = _port(cur["peer_port_id"])
            link = {"kind": "through"}
        else:
            c = _cable(cur["id"])
            if not c:
                return out, ("open" if cur["type"] in THROUGH_TYPES else "")
            nxt = _port(c["port_b_id"] if c["port_a_id"] == cur["id"] else c["port_a_id"])
            link = {"kind": "cable", "cable_id": c["id"], "label": c["cable_label"], "type": c["cable_type"] if c["cable_type"] != "other" else "",
                    "length_m": c["length_m"], "color": c["color"], "measurement_ok": c["measurement_ok"], "workorder_id": c["workorder_id"]}
        if not nxt or nxt["id"] in seen:
            return out, "loop"
        seen.add(nxt["id"])
        out.append((link, nxt))
        cur, step = nxt, ("cable" if step == "through" else "through")
    return out, "too_long"


def _planned(port_ids: list[int]) -> dict[int, list[dict]]:
    ids = [p for p in port_ids if p]
    if not ids:
        return {}
    ph = ",".join("?" * len(ids))
    out: dict[int, list[dict]] = {}
    for r in db.rows(f"""SELECT i.action, i.port_a_id, i.port_b_id, i.old_port_b_id, w.id, w.number, w.status FROM workitems i
                         JOIN workorders w ON w.id = i.workorder_id
                         WHERE i.action IN ('connect', 'disconnect', 'move') AND w.status IN ({",".join("?" * len(reservations.PLANNING_STATES))})
                           AND (i.port_a_id IN ({ph}) OR i.port_b_id IN ({ph}) OR i.old_port_b_id IN ({ph}))
                         ORDER BY w.id""", (*reservations.PLANNING_STATES, *ids, *ids, *ids)):
        for pid in {r["port_a_id"], r["port_b_id"], r["old_port_b_id"]} & set(ids):
            out.setdefault(pid, []).append({"workorder": {"id": r["id"], "number": r["number"]}, "action": ACTION_LABELS[r["action"]]})
    return out


def _lldp(end: dict, other: dict) -> dict:
    """Sieht ``end`` per LLDP/CDP das Gerät ``other`` am erwarteten Port?"""
    if end["type"] in THROUGH_TYPES or other["type"] in THROUGH_TYPES:
        return {"status": "n/a"}
    if not end["neighbors_at"]:
        return {"status": "unknown", "text": f"keine LLDP-Daten von {end['hostname']}"}
    obs = db.rows("SELECT neighbor_name, neighbor_port, neighbor_address FROM observations WHERE port_id = ?", (end["id"],))
    want_host, want_port = short_host(other["hostname"]), norm_port(other["name"])
    ip = str(other["mgmt_ip"] or "").split("/")[0]
    host_hits = [o for o in obs if short_host(o["neighbor_name"]) == want_host or (ip and o["neighbor_address"] == ip)]
    if any(norm_port(o["neighbor_port"]) == want_port for o in host_hits):
        return {"status": "ok", "text": f"{end['hostname']} sieht {other['hostname']}:{other['name']}"}
    if host_hits:
        return {"status": "port_mismatch", "text": f"{end['hostname']} sieht {other['hostname']}, aber an {host_hits[0]['neighbor_port']}"}
    if obs:
        seen = ", ".join(f"{o['neighbor_name']}:{o['neighbor_port']}" for o in obs[:3])
        return {"status": "mismatch", "text": f"{end['hostname']}:{end['name']} sieht stattdessen {seen}"}
    return {"status": "not_seen", "text": f"{end['hostname']}:{end['name']} meldet keinen Nachbarn"}


def trace(port_id: int, me: Principal) -> dict:
    start = _port(port_id)
    if not start:
        return {}
    right, right_end = _walk(start, "cable")
    left, left_end = _walk(start, "through")
    # Kette als Folge von Ports mit Verbindungen dazwischen: links (umgedreht) · Start · rechts
    ports = [p for _, p in reversed(left)] + [start] + [p for _, p in right]
    links = [lk for lk, _ in reversed(left)] + [lk for lk, _ in right]
    ends = [left_end, right_end]
    first_active, last_active = ports[0]["type"] in ACTIVE_FIRST, ports[-1]["type"] in ACTIVE_FIRST
    if last_active and not first_active:                                   # aktives Netzgerät nach links
        ports.reverse(); links.reverse(); ends.reverse()

    planned = _planned([p["id"] for p in ports])
    res = reservations.active(p["id"] for p in ports)
    vis = access.visible_sites(me)

    def visible(p: dict) -> bool:
        return vis is None or p["site_id"] in vis

    # Ports zu Stationen zusammenfassen: Durchschleifung = gleiche Station (Patchfeld vorn/hinten)
    nodes: list[dict] = []
    node_links: list[dict] = []
    for i, p in enumerate(ports):
        port_out = {"id": p["id"], "name": p["name"], "start": p["id"] == port_id, "planned": planned.get(p["id"], []),
                    "reservation": res[p["id"]]["purpose"] if p["id"] in res else None}
        if i > 0 and links[i - 1]["kind"] == "through":
            nodes[-1]["ports"].append(port_out)
            continue
        if i > 0:
            node_links.append(links[i - 1])
        ok = visible(p)
        nodes.append({"device": {"id": p["device_id"] if ok else None, "hostname": p["hostname"] if ok else "(außerhalb deines Bereichs)",
                                 "type": p["type"], "status": p["status"],
                                 "location": (_loc(p["location_id"]) if ok else ""), "unit": p["rack_position"] if ok else None},
                      "ports": [port_out] if ok else [{**port_out, "name": "…", "id": None}],
                      "passive": p["type"] in THROUGH_TYPES})
    a, b = ports[0], ports[-1]
    complete = not any(ends) and a["type"] not in THROUGH_TYPES and b["type"] not in THROUGH_TYPES and len(ports) > 1
    reasons = {"open": "offenes Ende", "loop": "Schleife in der Verkabelung", "too_long": "Kette zu lang"}
    shown = lambda n, k: f"{n['device']['hostname']}:{n['ports'][k]['name']}"  # noqa: E731 – sichtbare Namen (fremde anonymisiert)
    return {
        "start_port_id": port_id, "nodes": nodes, "links": node_links, "complete": complete,
        "ends": [reasons.get(e, "") for e in ends],
        "lldp": [_lldp(a, b), _lldp(b, a)] if complete and visible(a) and visible(b) else [],
        "summary": f"{shown(nodes[0], 0)} → {shown(nodes[-1], -1)}" if len(ports) > 1 else f"{shown(nodes[0], 0)} (nicht verbunden)",
        "hops": max(0, len(nodes) - 2),
    }


def _loc(location_id: Optional[int]) -> str:
    from .routers.masterdata import location_path                       # spät importieren (Router importiert dieses Modul nicht)
    return location_path(location_id) if location_id else ""
