"""Zeitreise über die Verbindungs-Historie: Stand zu einem Zeitpunkt und Vergleich zweier Zeitpunkte (neu / entfernt / umgesteckt).

Historisiert sind nur Verbindungen (``cable_history``). Geräte-Orte, Namen und Patchfeld-Gegenseiten sind der heutige Stand;
Geräte- und Portnamen der Verbindungen stammen aus dem Zeitpunkt des Steckens.
"""
from __future__ import annotations

from typing import Optional

from . import access, db
from .auth import Principal

ROW_SQL = """SELECT h.*, pa.device_id AS dev_a, pb.device_id AS dev_b, wo.number AS wo_number, we.number AS ended_wo_number
             FROM cable_history h
             LEFT JOIN ports pa ON pa.id = h.port_a_id LEFT JOIN ports pb ON pb.id = h.port_b_id
             LEFT JOIN workorders wo ON wo.id = h.workorder_id LEFT JOIN workorders we ON we.id = h.ended_workorder_id"""


def scope_devices(site_id: Optional[int], location_id: Optional[int], device_id: Optional[int]) -> Optional[set]:
    """Geräte im gewählten Ausschnitt (``None`` = alle)."""
    if device_id:
        return {device_id}
    if location_id:
        from .routers.masterdata import _location_and_children
        locs = list(_location_and_children(location_id))
        return {r["id"] for r in db.rows(f"SELECT id FROM devices WHERE location_id IN ({','.join('?' * len(locs))})", tuple(locs))} if locs else set()
    if site_id:
        return {r["id"] for r in db.rows("SELECT d.id FROM devices d JOIN locations l ON l.id = d.location_id WHERE l.site_id = ?", (site_id,))}
    return None


def _visible_devices(me: Principal) -> Optional[set]:
    clause, args = access.device_clause(me, "d")
    if not clause:
        return None
    return {r["id"] for r in db.rows(f"SELECT d.id FROM devices d WHERE {clause}", tuple(args))}


def _filter(rows: list[dict], me: Principal, scope: Optional[set]) -> list[dict]:
    vis = _visible_devices(me)
    out = []
    for r in rows:
        ends = {r["dev_a"], r["dev_b"]} - {None}
        if scope is not None and not (ends & scope):
            continue
        if vis is not None and not (ends & vis):
            continue                                                     # gelöschte Ports (ohne Gerät) nur mit globaler Sicht
        out.append(r)
    return out


def _end(r: dict, side: str) -> dict:
    return {"port_id": r[f"port_{side}_id"], "device_id": r[f"dev_{side}"], "hostname": r[f"host_{side}"], "port": r[f"port_{side}_name"]}


def conn(r: dict) -> dict:
    return {"id": r["id"], "cable_id": r["cable_id"], "a": _end(r, "a"), "b": _end(r, "b"), "cable_label": r["cable_label"],
            "cable_type": r["cable_type"] if r["cable_type"] != "other" else "", "length_m": r["length_m"], "color": r["color"],
            "valid_from": r["valid_from"], "valid_to": r["valid_to"], "created_by": r["created_by"],
            "workorder": {"id": r["workorder_id"], "number": r["wo_number"]} if r["workorder_id"] else None,
            "ended_by": r["ended_by"], "end_reason": r["end_reason"],
            "ended_workorder": {"id": r["ended_workorder_id"], "number": r["ended_wo_number"]} if r["ended_workorder_id"] else None}


def active_at(t: float, me: Principal, scope: Optional[set]) -> list[dict]:
    rows = db.rows(f"{ROW_SQL} WHERE h.valid_from <= ? AND (h.valid_to IS NULL OR h.valid_to > ?) ORDER BY h.host_a, h.port_a_name", (t, t))
    return _filter(rows, me, scope)


def _key(r: dict) -> tuple:
    """Identität einer Verbindung: das Port-Paar (bei gelöschten Ports die damaligen Namen)."""
    a = r["port_a_id"] or f"{r['host_a']}:{r['port_a_name']}"
    b = r["port_b_id"] or f"{r['host_b']}:{r['port_b_name']}"
    return tuple(sorted((str(a), str(b))))


def diff(t1: float, t2: float, me: Principal, scope: Optional[set]) -> dict:
    if t1 > t2:
        t1, t2 = t2, t1
    before = {_key(r): r for r in active_at(t1, me, scope)}
    after = {_key(r): r for r in active_at(t2, me, scope)}
    removed = [before[k] for k in before if k not in after]
    added = [after[k] for k in after if k not in before]
    changed = [{"before": conn(before[k]), "after": conn(after[k])} for k in before
               if k in after and (before[k]["cable_label"], before[k]["cable_type"]) != (after[k]["cable_label"], after[k]["cable_type"])]

    # Umgesteckt: ein Port war vorher mit X und ist nachher mit Y verbunden
    moved, used_r, used_a = [], set(), set()
    for r in removed:
        for a in added:
            if a["id"] in used_a or r["id"] in used_r:
                continue
            common = ({r["port_a_id"], r["port_b_id"]} & {a["port_a_id"], a["port_b_id"]}) - {None}
            if not common:
                continue
            pid = common.pop()
            side_r = "a" if r["port_a_id"] == pid else "b"
            side_a = "a" if a["port_a_id"] == pid else "b"
            other = lambda s: "b" if s == "a" else "a"  # noqa: E731
            moved.append({"port": _end(r, side_r), "from": _end(r, other(side_r)), "to": _end(a, other(side_a)),
                          "before": conn(r), "after": conn(a)})
            used_r.add(r["id"]); used_a.add(a["id"])
    removed = [r for r in removed if r["id"] not in used_r]
    added = [a for a in added if a["id"] not in used_a]

    # Nur zwischenzeitlich: gesteckt und wieder getrennt, beides zwischen t1 und t2
    temp = _filter(db.rows(f"{ROW_SQL} WHERE h.valid_from > ? AND h.valid_to IS NOT NULL AND h.valid_to <= ? ORDER BY h.valid_from",
                           (t1, t2)), me, scope)
    by_time = lambda x: x["valid_from"]  # noqa: E731
    return {"from": t1, "to": t2,
            "added": [conn(a) for a in sorted(added, key=by_time)],
            "removed": [conn(r) for r in sorted(removed, key=lambda x: x["valid_to"] or 0)],
            "moved": moved, "changed": changed, "temporary": [conn(r) for r in temp],
            "summary": {"added": len(added), "removed": len(removed), "moved": len(moved), "changed": len(changed),
                        "temporary": len(temp), "before": len(before), "after": len(after)}}
