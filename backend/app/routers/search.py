"""Schnellsuche über Geräte, Standorte, Orte, WAN-Verbindungen, Patchaufträge und Kabelnummern – beschränkt auf den eigenen Bereich."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from .. import access, db
from ..auth import Principal, current_principal
from . import masterdata

router = APIRouter(prefix="/api/search", tags=["suche"])
PER_KIND = 8


def _like(q: str) -> str:
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


@router.get("")
def search(q: str = Query("", max_length=100), me: Principal = Depends(current_principal)):
    q = q.strip()
    out: dict = {"q": q, "devices": [], "sites": [], "locations": [], "wan": [], "trunks": [], "orders": [], "cables": []}
    if len(q) < 2:
        return out
    pat = _like(q)
    vs = access.visible_sites(me)

    where = ("(d.hostname LIKE ?1 ESCAPE '\\' OR d.mgmt_ip LIKE ?1 ESCAPE '\\' OR d.serial LIKE ?1 ESCAPE '\\' OR d.model LIKE ?1 ESCAPE '\\' "
             "OR d.planned_hostname LIKE ?1 ESCAPE '\\' OR d.former_hostname LIKE ?1 ESCAPE '\\')")
    sql = f"""SELECT d.id, d.hostname, d.type, d.status, d.model, d.vendor, d.mgmt_ip, d.location_id, d.rack_position, d.height_u, d.mount_side, l.site_id,
                     l.kind AS loc_kind, l.rack_units
              FROM devices d LEFT JOIN locations l ON l.id = d.location_id WHERE {where}"""
    rows = db.rows(f"{sql} ORDER BY (d.hostname LIKE ?2 ESCAPE '\\') DESC, d.hostname COLLATE NOCASE LIMIT 60", (pat, q.replace("\\", "").replace("%", "") + "%"))
    for d in rows:
        if vs is not None and d["site_id"] not in vs:
            continue
        site = db.row("SELECT code, name FROM sites WHERE id = ?", (d["site_id"],)) if d["site_id"] else None
        out["devices"].append({
            "id": d["id"], "hostname": d["hostname"], "type": d["type"], "status": d["status"], "model": " ".join(x for x in (d["vendor"], d["model"]) if x),
            "mgmt_ip": d["mgmt_ip"], "site": f"{site['code']} – {site['name']}" if site else "", "location": masterdata.location_path(d["location_id"]),
            "location_id": d["location_id"], "position": d["rack_position"], "height_u": d["height_u"], "in_rack": bool(d["location_id"]),
        })
        if len(out["devices"]) >= PER_KIND:
            break

    sc, sa = access.sites_clause(me, "id")
    out["sites"] = [dict(r) for r in db.rows(
        f"SELECT id, code, name, address FROM sites WHERE (code LIKE ? ESCAPE '\\' OR name LIKE ? ESCAPE '\\' OR address LIKE ? ESCAPE '\\')"
        + (f" AND {sc}" if sc else "") + f" ORDER BY code LIMIT {PER_KIND}", (pat, pat, pat, *sa))]

    lc, la = access.sites_clause(me, "l.site_id")
    for r in db.rows("SELECT l.id, l.name, l.kind, l.ident, l.site_id FROM locations l WHERE (l.name LIKE ? ESCAPE '\\' OR l.ident LIKE ? ESCAPE '\\')"
                     + (f" AND {lc}" if lc else "") + f" ORDER BY l.name COLLATE NOCASE LIMIT {PER_KIND}", (pat, pat, *la)):
        out["locations"].append({"id": r["id"], "name": r["name"], "kind": r["kind"], "ident": r["ident"], "path": masterdata.location_path(r["id"])})

    for r in db.rows("SELECT * FROM wan_links WHERE (name LIKE ? ESCAPE '\\' OR circuit_id LIKE ? ESCAPE '\\' OR provider LIKE ? ESCAPE '\\' "
                     "OR contract_number LIKE ? ESCAPE '\\') ORDER BY name COLLATE NOCASE LIMIT 40", (pat, pat, pat, pat)) if me.can_see("wan") else []:
        if not (access.can_read_site(me, r["site_a_id"]) or access.can_read_site(me, r["site_b_id"])):
            continue
        out["wan"].append({"id": r["id"], "name": r["name"], "status": r["status"], "provider": r["provider"], "circuit_id": r["circuit_id"]})
        if len(out["wan"]) >= PER_KIND:
            break

    for r in db.rows("SELECT * FROM sip_trunks WHERE (name LIKE ? ESCAPE '\\' OR trunk_ident LIKE ? ESCAPE '\\' OR provider LIKE ? ESCAPE '\\' "
                     "OR numbers LIKE ? ESCAPE '\\' OR contract_number LIKE ? ESCAPE '\\') ORDER BY name COLLATE NOCASE LIMIT 40", (pat,) * 5) if me.can_see("telephony") else []:
        if not access.can_read_site(me, r["site_id"]):
            continue
        out["trunks"].append({"id": r["id"], "name": r["name"], "status": r["status"], "provider": r["provider"], "trunk_ident": r["trunk_ident"]})
        if len(out["trunks"]) >= PER_KIND:
            break

    for w in db.rows("SELECT id, number, title, status, location_id FROM workorders WHERE (number LIKE ? ESCAPE '\\' OR title LIKE ? ESCAPE '\\') "
                     "ORDER BY id DESC LIMIT 40", (pat, pat)):
        if not access.can_read_site(me, access.site_of_location(w["location_id"])):
            continue
        out["orders"].append({"id": w["id"], "number": w["number"], "title": w["title"], "status": w["status"]})
        if len(out["orders"]) >= PER_KIND:
            break

    for c in db.rows("""SELECT c.id, c.cable_label, c.port_a_id, c.port_b_id FROM cables c WHERE c.cable_label LIKE ? ESCAPE '\\' LIMIT 40""", (pat,)):
        ends = []
        for pid in (c["port_a_id"], c["port_b_id"]):
            p = db.row("SELECT p.name, d.id AS did, d.hostname FROM ports p JOIN devices d ON d.id = p.device_id WHERE p.id = ?", (pid,))
            ends.append(p)
        if vs is not None and not any(access.site_of_port(pid) in vs for pid in (c["port_a_id"], c["port_b_id"])):
            continue
        out["cables"].append({"id": c["id"], "label": c["cable_label"], "a": f"{ends[0]['hostname']}:{ends[0]['name']}", "b": f"{ends[1]['hostname']}:{ends[1]['name']}",
                              "device_id": ends[0]["did"]})
        if len(out["cables"]) >= PER_KIND:
            break
    return out
