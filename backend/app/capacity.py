"""Kapazitätsplanung: freie Ports je Kategorie und freie Höheneinheiten je Rack, über die Location-Hierarchie zusammengezählt.

Ports
* Kategorien: Switchports (Switch/Router/Firewall), Patchfeld, Dose, PDU. Bei Patchfeldern/Dosen zählt nur die Vorderseite
  (die Gegenseite ``…-back`` eines verknüpften Paares wäre sonst doppelt).
* Je Port genau ein Zustand, in dieser Rangfolge: belegt (Kabel) › verplant (offener Auftrag will ihn verbinden) › reserviert › frei.

Höheneinheiten (19-Zoll-Racks; hochkant und Hutschiene zählen nicht)
* belegt = mindestens eine Seite belegt; „ganz frei“ = vorne und hinten frei; größter zusammenhängender ganz freier Block.
* „verplant“: Geräte im Status geplant; „wird frei“: Geräte mit offenem Rückbau-Auftrag.
"""
from __future__ import annotations

from typing import Optional

from . import access, db, reservations
from .auth import Principal
from .rackmount import DEFAULT_RACK_UNITS, pending_removal_device_ids, sides
from .schemas import CONTAINER_KINDS

CATEGORIES = {"switch": "switch", "router": "switch", "firewall": "switch", "patchpanel": "patchpanel", "outlet": "outlet", "pdu": "pdu"}
CATEGORY_LABELS = {"switch": "Switchports", "patchpanel": "Patchfeld-Ports", "outlet": "Dosen", "pdu": "PDU-Abgänge"}
STATES = ("used", "planned", "reserved", "free")


def _empty() -> dict:
    return {c: {s: 0 for s in STATES} | {"total": 0} for c in CATEGORY_LABELS}


def _add(into: dict, other: dict) -> None:
    for c, v in other.items():
        for k, n in v.items():
            into[c][k] += n


def _rack_units(loc: dict, devices: list[dict], removing: set) -> dict:
    units = loc["rack_units"] or DEFAULT_RACK_UNITS
    front, rear = [None] * (units + 1), [None] * (units + 1)
    planned = freed = 0
    for d in devices:
        if d["orientation"] != "horizontal" or not d["rack_position"]:
            continue
        lo, hi = d["rack_position"], min(units, d["rack_position"] + (d["height_u"] or 1) - 1)
        for side in sides(d["mount_side"]):
            arr = front if side == "front" else rear
            for u in range(lo, hi + 1):
                arr[u] = d["id"]
        if d["status"] == "planned":
            planned += hi - lo + 1
        if d["id"] in removing:
            freed += hi - lo + 1
    used = sum(1 for u in range(1, units + 1) if front[u] or rear[u])
    free_both = [u for u in range(1, units + 1) if not front[u] and not rear[u]]
    block = best = 0
    for u in range(1, units + 1):
        block = block + 1 if (not front[u] and not rear[u]) else 0
        best = max(best, block)
    return {"total": units, "used": used, "free": len(free_both), "largest_block": best,
            "half_free": sum(1 for u in range(1, units + 1) if bool(front[u]) != bool(rear[u])), "planned": planned, "freed": freed}


def _pct(free: int, total: int) -> Optional[float]:
    return round(100 * free / total, 1) if total else None


def report(me: Principal, site_id: Optional[int] = None, warn: float = 10.0) -> dict:
    vis = access.visible_sites(me)
    sites = [s for s in db.rows("SELECT id, code, name FROM sites ORDER BY code COLLATE NOCASE")
             if (vis is None or s["id"] in vis) and (site_id is None or s["id"] == site_id)]
    site_ids = {s["id"] for s in sites}
    locs = {l["id"]: l for l in db.rows("SELECT id, site_id, parent_id, kind, name, rack_units FROM locations") if l["site_id"] in site_ids}

    planned_ports = {p for r in db.rows(f"""SELECT i.port_a_id, i.port_b_id FROM workitems i JOIN workorders w ON w.id = i.workorder_id
                                           WHERE i.action IN ('connect', 'move')
                                             AND w.status IN ({','.join('?' * len(reservations.PLANNING_STATES))})""",
                                        reservations.PLANNING_STATES) for p in (r["port_a_id"], r["port_b_id"]) if p}
    reserved_ports = {r["port_id"] for r in db.rows("SELECT port_id FROM port_reservations WHERE until IS NULL OR until >= ?", (reservations.today(),))}

    per_loc: dict[int, dict] = {lid: _empty() for lid in locs}
    for p in db.rows("""SELECT p.id, p.name, p.peer_port_id, d.type, d.location_id,
                               EXISTS(SELECT 1 FROM cables c WHERE c.port_a_id = p.id OR c.port_b_id = p.id) AS busy
                        FROM ports p JOIN devices d ON d.id = p.device_id
                        WHERE d.status <> 'retired' AND d.location_id IS NOT NULL"""):
        cat = CATEGORIES.get(p["type"])
        if not cat or p["location_id"] not in per_loc:
            continue
        if cat in ("patchpanel", "outlet") and p["peer_port_id"] and p["name"].lower().endswith("-back"):
            continue                                                         # Rückseite eines verknüpften Paares
        state = "used" if p["busy"] else "planned" if p["id"] in planned_ports else "reserved" if p["id"] in reserved_ports else "free"
        s = per_loc[p["location_id"]][cat]
        s[state] += 1
        s["total"] += 1

    removing = pending_removal_device_ids()
    devs_by_loc: dict[int, list] = {}
    for d in db.rows("SELECT id, location_id, rack_position, height_u, orientation, mount_side, status FROM devices WHERE status <> 'retired'"):
        devs_by_loc.setdefault(d["location_id"], []).append(d)

    children: dict[Optional[int], list[int]] = {}
    for l in sorted(locs.values(), key=lambda x: x["name"].casefold()):
        children.setdefault(l["parent_id"], []).append(l["id"])

    alerts: list[dict] = []

    def check(path: str, link: dict, stats: dict, units: Optional[dict]) -> list[str]:
        flags = []
        for c, v in stats.items():
            pct = _pct(v["free"], v["total"])
            if pct is not None and pct < warn:
                flags.append(c)
                alerts.append({"path": path, **link, "kind": "ports", "category": c, "label": CATEGORY_LABELS[c],
                               "free": v["free"], "total": v["total"], "free_pct": pct})
        if units:
            pct = _pct(units["free"], units["total"])
            if pct is not None and pct < warn:
                flags.append("units")
                alerts.append({"path": path, **link, "kind": "units", "label": "Höheneinheiten", "free": units["free"],
                               "total": units["total"], "free_pct": pct, "largest_block": units["largest_block"]})
        return flags

    def node(lid: int, prefix: str) -> dict:
        l = locs[lid]
        path = f"{prefix} / {l['name']}"
        kids = [node(c, path) for c in children.get(lid, [])]
        stats = _empty()
        _add(stats, per_loc[lid])
        for k in kids:
            _add(stats, k["stats"])
        units = _rack_units(l, devs_by_loc.get(lid, []), removing) if l["kind"] in CONTAINER_KINDS else None
        flags = check(path, {"location_id": lid}, per_loc[lid], units)      # Port-Engpass dort melden, wo die Ports stecken (nicht je Ebene)
        return {"id": lid, "name": l["name"], "kind": l["kind"], "path": path, "stats": stats, "units": units, "warn": flags, "children": kids}

    out_sites = []
    for s in sites:
        roots = [node(lid, s["code"]) for lid in children.get(None, []) if locs[lid]["site_id"] == s["id"]]
        stats = _empty()
        for r in roots:
            _add(stats, r["stats"])
        racks = [n for r in roots for n in _flatten(r) if n["units"]]
        out_sites.append({"id": s["id"], "code": s["code"], "name": s["name"], "stats": stats, "children": roots,
                          "units": {"racks": len(racks), "total": sum(n["units"]["total"] for n in racks),
                                    "free": sum(n["units"]["free"] for n in racks)}})
    alerts.sort(key=lambda a: (a["free_pct"], a["path"]))
    return {"warn": warn, "categories": CATEGORY_LABELS, "sites": out_sites, "alerts": alerts}


def _flatten(n: dict) -> list[dict]:
    return [n] + [x for c in n["children"] for x in _flatten(c)]
