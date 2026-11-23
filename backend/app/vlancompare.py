"""VLAN-Soll/Ist: dokumentierte Port-Konfiguration (Soll) gegen die von Checkmk gemeldeten VLANs (Ist).

Datenlage (Checkmk-Plugin ``inv_cisco_vlans``, CISCO-VLAN-MEMBERSHIP-MIB): nur Cisco, nur **Access-VLANs** (``static``/``dynamic``,
bei ``multi-VLAN`` eine Liste). Trunks und Voice-VLANs meldet Checkmk nicht. Daraus folgt je Switch-Port:

==================  ==========================  =========================================
Soll                Ist                         Ergebnis
==================  ==========================  =========================================
Access X            static/dynamic X            ok
Access X            static/dynamic Y            abweichend
Access X            nichts gemeldet             nicht gemeldet (Trunk? Port aus?)
Trunk               static/dynamic Y            abweichend (Switch meldet Access-VLAN)
Trunk               nichts gemeldet             plausibel (Trunks meldet Checkmk nicht)
nicht dokumentiert  static/dynamic Y            nicht dokumentiert (übernehmbar)
beliebig            multi-VLAN                  nicht bewertbar (Dekodierung in Checkmk unsicher)
==================  ==========================  =========================================
"""
from __future__ import annotations

import time
from typing import Iterable, Optional

from . import access, db, portcfg
from .auth import Principal
from .compare import norm_port

STATUS_LABELS = {"ok": "stimmt", "mismatch": "abweichend", "not_reported": "nicht gemeldet", "plausible": "plausibel (Trunk)",
                 "undocumented": "nicht dokumentiert", "unrated": "nicht bewertbar"}
SEVERITY = {"mismatch": 3, "undocumented": 2, "not_reported": 1, "unrated": 0, "plausible": 0, "ok": 0}


def store(by_host: dict[str, list[dict]]) -> dict:
    """Ersetzt die gemeldeten VLANs der Geräte (Hostname, ohne Groß-/Kleinschreibung); unbekannte Hosts werden gezählt."""
    now = time.time()
    stats = {"devices": 0, "ports": 0, "unknown_devices": 0}
    for host, items in by_host.items():
        d = db.row("SELECT id FROM devices WHERE hostname = ? COLLATE NOCASE", (host,))
        if not d:
            stats["unknown_devices"] += 1
            continue
        ports = {norm_port(p["name"]): p["id"] for p in db.rows("SELECT id, name FROM ports WHERE device_id = ?", (d["id"],))}
        with db.transaction() as c:
            c.execute("DELETE FROM vlan_observations WHERE device_id = ?", (d["id"],))
            for v in items:
                c.execute("INSERT INTO vlan_observations(device_id, port_id, port_name, vlans, vlantype, seen_at) VALUES (?,?,?,?,?,?)",
                          (d["id"], ports.get(norm_port(v["port"])), v["port"][:120], v["vlans"][:500], v["vlantype"][:20], now))
                stats["ports"] += 1
            c.execute("UPDATE devices SET vlans_at = ? WHERE id = ?", (now, d["id"]))
        stats["devices"] += 1
    return stats


def _single(obs: dict) -> Optional[int]:
    if obs["vlantype"] in ("static", "dynamic") and obs["vlans"].strip().isdigit():
        return int(obs["vlans"].strip())
    return None


def rate(doc: dict, obs: Optional[dict]) -> tuple[str, str]:
    """(Status, Erklärung) für einen Port."""
    mode = doc.get("port_mode") or ""
    if obs and obs["vlantype"] == "multi-VLAN":
        return "unrated", f"Switch meldet mehrere VLANs ({obs['vlans']}) – nicht bewertbar"
    ist = _single(obs) if obs else None
    if mode == "access":
        if ist is None:
            return "not_reported", "Switch meldet kein Access-VLAN (Trunk, Port aus oder nicht unterstützt?)"
        if ist == doc["access_vid"]:
            return "ok", ""
        return "mismatch", f"dokumentiert Access {doc['access_vid']}, Switch meldet {ist}"
    if mode == "trunk":
        if ist is None:
            return "plausible", "Trunks meldet Checkmk nicht – kein Widerspruch"
        return "mismatch", f"dokumentiert Trunk, Switch meldet Access-VLAN {ist}"
    if ist is not None:
        return "undocumented", f"Switch meldet Access-VLAN {ist}"
    return "", ""


def report(me: Principal, site_id: Optional[int] = None) -> dict:
    """Je Port der Geräte mit VLAN-Daten das Ergebnis; Ports ohne Doku und ohne Meldung werden nicht aufgeführt."""
    where, args = ["d.vlans_at IS NOT NULL"], []
    clause, cargs = access.device_clause(me, "d")
    if clause:
        where.append(clause); args += cargs
    if site_id is not None:
        where.append("d.location_id IN (SELECT id FROM locations WHERE site_id = ?)"); args.append(site_id)
    devices = {d["id"]: d for d in db.rows(f"SELECT d.id, d.hostname, d.vlans_at, d.location_id FROM devices d WHERE {' AND '.join(where)}", tuple(args))}
    obs: dict[int, dict] = {}
    for o in db.rows("SELECT * FROM vlan_observations WHERE port_id IS NOT NULL"):
        if o["device_id"] in devices:
            obs[o["port_id"]] = o
    names_by_site: dict[Optional[int], dict] = {}
    out = []
    for did, d in devices.items():
        site = access.site_of_device(did)
        names = names_by_site.setdefault(site, portcfg.vlan_names(site))
        for p in db.rows(f"SELECT id, name, {', '.join(portcfg.FIELDS)} FROM ports WHERE device_id = ?", (did,)):
            doc = {k: p[k] for k in portcfg.FIELDS}
            o = obs.get(p["id"])
            status, why = rate(doc, o)
            if not status:
                continue
            ist = (f"{o['vlantype']} {o['vlans']}" + (f" ({names[int(o['vlans'])]})" if o["vlans"].isdigit() and int(o["vlans"]) in names else "")) if o else ""
            out.append({"device_id": did, "device": d["hostname"], "port_id": p["id"], "port": p["name"], "status": status,
                        "status_label": STATUS_LABELS[status], "soll": portcfg.describe(doc, names) or "nicht dokumentiert", "ist": ist or "–",
                        "why": why, "adoptable": status in ("undocumented", "mismatch") and _single(o) is not None if o else False,
                        "seen_at": o["seen_at"] if o else d["vlans_at"]})
    from .routers.masterdata import _natural_key as nk
    out.sort(key=lambda r: (-SEVERITY[r["status"]], nk(r["device"]), nk(r["port"])))
    summary = {k: sum(1 for r in out if r["status"] == k) for k in STATUS_LABELS}
    return {"devices": len(devices), "summary": summary, "rows": out}


def adopt(port_ids: Iterable[int], me: Principal) -> dict:
    """„Ist übernehmen“: gemeldetes Access-VLAN als dokumentierte Konfiguration eintragen (Historie: Grund „checkmk“)."""
    done, skipped = [], []
    for pid in sorted(set(port_ids)):
        o = db.row("SELECT * FROM vlan_observations WHERE port_id = ? ORDER BY seen_at DESC LIMIT 1", (pid,))
        vid = _single(o) if o else None
        if vid is None or not access.can_write_site(me, access.site_of_port(pid)):
            skipped.append(pid)
            continue
        cur = portcfg.current(pid)
        cfg = {"port_mode": "access", "access_vid": vid, "voice_vid": cur["voice_vid"] if cur["port_mode"] == "access" else None}
        portcfg.apply(pid, cfg, me.name, None, "checkmk")
        done.append(pid)
    return {"adopted": len(done), "skipped": len(skipped)}
