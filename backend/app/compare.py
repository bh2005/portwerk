"""Soll/Ist-Abgleich: dokumentierte Verkabelung (Soll) gegen LLDP/CDP-Nachbarn (Ist).

* Ist: ``observations`` – je Gerät die zuletzt gemeldeten Nachbarn (kommen aus dem Checkmk-Import, siehe ``store``).
* Soll: Kabel zum Gegenüber; über Patchfelder/Dosen (``THROUGH_TYPES``) wird bis zum ersten aktiven Gerät weiterverfolgt.
Ergebnis je lokalem Port: ok · anderer Port · anderes Gerät · nicht gesehen · nicht dokumentiert · keine Daten · Port unbekannt.
"""
from __future__ import annotations

import re
import time
from typing import Optional

from . import access, db
from .auth import Principal

THROUGH_TYPES = ("patchpanel", "outlet")                       # passive Zwischenstationen: Kette läuft über die Gegenseite weiter
STATUS_LABELS = {"ok": "stimmt", "port_mismatch": "anderer Port", "mismatch": "anderes Gerät", "not_seen": "nicht gesehen",
                 "undocumented": "nicht dokumentiert", "unknown": "keine Daten", "unmapped": "Port unbekannt"}
SEVERITY = {"mismatch": 3, "port_mismatch": 3, "undocumented": 2, "not_seen": 2, "unmapped": 1, "unknown": 0, "ok": 0}

_ABBR = (("tengigabitethernet", "te"), ("twentyfivegige", "twe"), ("fortygigabitethernet", "fo"), ("hundredgige", "hu"),
         ("gigabitethernet", "gi"), ("fastethernet", "fa"), ("port-channel", "po"), ("portchannel", "po"), ("ethernet", "eth"))
_MAC = re.compile(r"^([0-9a-f]{2}[:\-.]?){5}[0-9a-f]{2}$", re.I)


def norm_port(name: str) -> str:
    """Portnamen vergleichbar machen: ``GigabitEthernet0/3`` und ``Gi0/3`` werden gleich."""
    s = re.sub(r"\s+", "", str(name or "").lower())
    for long, short in _ABBR:
        if s.startswith(long):
            s = short + s[len(long):]
            break
    return s


def _clean(v) -> str:
    """Steuerzeichen entfernen (manche Geräte hängen ein NUL-Byte an LLDP-Namen an)."""
    return re.sub(r"[\x00-\x1f\x7f]", "", str(v or "")).strip()


def short_host(name: str) -> str:
    return str(name or "").strip().lower().split(".")[0]


# ── Nachbardaten speichern ────────────────────────────────────────────────────

def store(neighbors_by_host: dict[str, list[dict]]) -> dict:
    """Ersetzt die Nachbarn der Geräte (Hostname, ohne Groß-/Kleinschreibung); unbekannte Hosts werden gezählt und ignoriert."""
    now = time.time()
    stats = {"devices": 0, "neighbors": 0, "unknown_devices": 0}
    for host, items in neighbors_by_host.items():
        d = db.row("SELECT id FROM devices WHERE hostname = ? COLLATE NOCASE", (host,))
        if not d:
            stats["unknown_devices"] += 1
            continue
        ports = {norm_port(p["name"]): p["id"] for p in db.rows("SELECT id, name FROM ports WHERE device_id = ?", (d["id"],))}
        db.execute("DELETE FROM observations WHERE device_id = ?", (d["id"],))
        for n in items:
            db.execute("""INSERT INTO observations(device_id, port_id, local_port, protocol, neighbor_name, neighbor_port, neighbor_address, capabilities, seen_at)
                          VALUES (?,?,?,?,?,?,?,?,?)""",
                       (d["id"], ports.get(norm_port(n["local_port"])), n["local_port"], n.get("protocol", "lldp"), _clean(n["neighbor_name"])[:200],
                        _clean(n.get("neighbor_port", ""))[:120], _clean(n.get("neighbor_address", ""))[:80], _clean(n.get("capabilities", ""))[:120], now))
            stats["neighbors"] += 1
        db.execute("UPDATE devices SET neighbors_at = ? WHERE id = ?", (now, d["id"]))
        stats["devices"] += 1
    return stats


# ── Abgleich ──────────────────────────────────────────────────────────────────

class _World:
    """Bestand einmal laden (Geräte, Ports, Kabel, Standorte) – der Abgleich rechnet danach im Speicher."""

    def __init__(self):
        self.dev = {d["id"]: d for d in db.rows(
            "SELECT d.id, d.hostname, d.type, d.mgmt_ip, d.neighbors_at, d.location_id, l.site_id FROM devices d LEFT JOIN locations l ON l.id = d.location_id")}
        self.port = {p["id"]: p for p in db.rows("SELECT id, device_id, name, peer_port_id FROM ports")}
        self.cable: dict[int, int] = {}
        for c in db.rows("SELECT port_a_id, port_b_id FROM cables"):
            self.cable[c["port_a_id"]], self.cable[c["port_b_id"]] = c["port_b_id"], c["port_a_id"]
        self.peer: dict[int, int] = {}
        for p in self.port.values():
            if p["peer_port_id"]:
                self.peer[p["id"]], self.peer[p["peer_port_id"]] = p["peer_port_id"], p["id"]
        self.by_name: dict[str, list[int]] = {}
        self.by_ip: dict[str, int] = {}
        for d in self.dev.values():
            self.by_name.setdefault(short_host(d["hostname"]), []).append(d["id"])
            if d["mgmt_ip"]:
                self.by_ip.setdefault(str(d["mgmt_ip"]).split("/")[0], d["id"])
        self.by_dev_port: dict[tuple[int, str], int] = {(p["device_id"], norm_port(p["name"])): p["id"] for p in self.port.values()}

    def label(self, port_id: Optional[int]) -> str:
        p = self.port.get(port_id) if port_id else None
        return f"{self.dev[p['device_id']]['hostname']}:{p['name']}" if p else ""

    def device_by_neighbor(self, name: str, address: str) -> Optional[int]:
        ids = self.by_name.get(short_host(name), [])
        if len(ids) == 1:
            return ids[0]
        for i in ids:                                                       # mehrdeutig: voller Name entscheidet
            if self.dev[i]["hostname"].lower() == str(name).strip().lower():
                return i
        return self.by_ip.get(str(address or "").split("/")[0]) if not ids else None

    def resolve(self, o: dict) -> dict:
        """Ein gemeldeter Nachbar (Zeile aus ``observations``) mit aufgelöstem Gerät/Port aus dem Bestand."""
        dev_id = self.device_by_neighbor(o["neighbor_name"], o["neighbor_address"])
        port_id = self.by_dev_port.get((dev_id, norm_port(o["neighbor_port"]))) if dev_id else None
        return {"obs_id": o["id"], "name": o["neighbor_name"], "port": o["neighbor_port"], "address": o["neighbor_address"], "protocol": o["protocol"],
                "capabilities": o["capabilities"], "type_guess": guess_type(o["capabilities"]), "device_id": dev_id, "port_id": port_id, "label": self.label(port_id) if port_id else (self.dev[dev_id]["hostname"] if dev_id else "")}

    def adopt_target(self, port_id: int, ist: list[dict]) -> Optional[int]:
        """Gegenport, wenn der Port „übernommen“ werden kann: kein Kabel am Port, genau ein gemeldeter Nachbar, dessen Port im Bestand
        bekannt und noch frei ist. Sonst None (Konflikte und Mehrdeutigkeiten löst man bewusst von Hand)."""
        if port_id in self.cable or port_id in self.peer or len(ist) != 1:
            return None
        t = ist[0]["port_id"]
        if not t or t == port_id or t in self.cable or t in self.peer:
            return None
        return t

    def trace(self, port_id: int) -> tuple[Optional[int], list[str], str]:
        """(Endport am ersten aktiven Gerät | None, Zwischenstationen, Grund bei Abbruch)."""
        hops, cur, seen = [], port_id, set()
        while cur not in seen:
            seen.add(cur)
            other = self.cable.get(cur)
            if not other:
                return None, hops, "kein Kabel" if not hops else "Kette endet nach " + hops[-1]
            dev = self.dev[self.port[other]["device_id"]]
            if dev["type"] not in THROUGH_TYPES:
                return other, hops, ""
            hops.append(self.label(other))
            nxt = self.peer.get(other)
            if not nxt:
                return None, hops, "Kette endet am Patchfeld " + hops[-1]
            cur = nxt
        return None, hops, "Schleife in der Verkabelung"


def guess_type(capabilities: str) -> str:
    """Gerätetyp aus den gemeldeten LLDP/CDP-Fähigkeiten (nur ein Vorschlag, im Dialog änderbar)."""
    c = str(capabilities or "").lower()
    for key, typ in (("wlan", "ap"), ("access point", "ap"), ("router", "router"), ("telephone", "endpoint"), ("phone", "endpoint"),
                     ("station", "endpoint"), ("bridge", "switch"), ("switch", "switch")):
        if key in c:
            return typ
    return "other"


def _merge(ist: list[dict]) -> list[dict]:
    """Derselbe Nachbar per LLDP und CDP (oder mehrfach gemeldet) erscheint nur einmal; Protokolle werden zusammengefasst."""
    out: dict[tuple, dict] = {}
    for i in ist:
        key = (short_host(i["name"]), norm_port(i["port"]))
        if key in out:
            if i["protocol"] not in out[key]["protocol"].split("/"):
                out[key]["protocol"] += "/" + i["protocol"]
            out[key]["name"] = max(out[key]["name"], i["name"], key=len)         # den längeren (vollständigen) Namen behalten
        else:
            out[key] = dict(i)
    return list(out.values())


def compare(me: Principal, site_id: Optional[int] = None) -> dict:
    w = _World()
    vs = access.visible_sites(me)
    obs: dict[int, list[dict]] = {}
    for o in db.rows("SELECT * FROM observations ORDER BY device_id, local_port, protocol"):
        obs.setdefault(o["device_id"], []).append(o)
    rows, seen_pairs = [], set()

    for did, d in w.dev.items():
        if not d["neighbors_at"]:
            continue
        if vs is not None and d["site_id"] not in vs:
            continue
        if site_id and d["site_id"] != site_id:
            continue
        mine = [p for p in w.port.values() if p["device_id"] == did]
        by_port: dict[Optional[int], list[dict]] = {}
        for o in obs.get(did, []):
            if _MAC.match(o["neighbor_name"]) and not w.device_by_neighbor(o["neighbor_name"], o["neighbor_address"]):
                continue                                                     # reine MAC-Adressen (Telefone, Kameras …) sind kein Gerätenachbar
            by_port.setdefault(o["port_id"], []).append(o)
        unmapped = [o for o in by_port.get(None, [])]
        base = {"device_id": did, "device": d["hostname"], "site_id": d["site_id"], "location_id": d["location_id"], "seen_at": d["neighbors_at"]}

        for p in sorted(mine, key=lambda x: x["id"]):
            ist = _merge([w.resolve(o) for o in by_port.get(p["id"], [])])
            end, hops, why = w.trace(p["id"])
            soll = {"port_id": end, "label": w.label(end), "via": hops, "why": why} if (end or hops) else None
            if not ist and not end:
                continue                                                     # nichts dokumentiert, nichts gesehen
            if end and not ist:
                end_dev = w.dev[w.port[end]["device_id"]]
                status = "not_seen" if end_dev["neighbors_at"] else "unknown"
            elif ist and not end:
                status = "undocumented"
            else:
                end_dev_id = w.port[end]["device_id"]
                ok = [i for i in ist if i["port_id"] == end]
                same_dev = [i for i in ist if i["device_id"] == end_dev_id]
                status = "ok" if ok else "port_mismatch" if same_dev else "mismatch"
                if status == "ok":
                    key = frozenset({p["id"], end})                          # dieselbe Strecke von beiden Enden: nur einmal
                    if key in seen_pairs:
                        continue
                    seen_pairs.add(key)
            target = w.adopt_target(p["id"], ist) if status == "undocumented" else None
            adopt = {"port_id": target, "label": w.label(target)} if target else None      # „Verbindung übernehmen“ möglich
            rows.append({**base, "port_id": p["id"], "port": p["name"], "status": status, "status_label": STATUS_LABELS[status], "soll": soll, "ist": ist, "adopt": adopt})
        for o in unmapped:
            rows.append({**base, "port_id": None, "port": o["local_port"], "status": "unmapped", "status_label": STATUS_LABELS["unmapped"], "soll": None, "ist": _merge([w.resolve(o)]), "adopt": None})

    rows.sort(key=lambda r: (-SEVERITY[r["status"]], r["device"].lower(), r["port"]))
    summary = {k: 0 for k in STATUS_LABELS}
    for r in rows:
        summary[r["status"]] += 1
    return {"summary": summary, "rows": rows, "devices": sum(1 for d in w.dev.values() if d["neighbors_at"] and (vs is None or d["site_id"] in vs))}


def adopt(port_id: int) -> tuple[int, int]:
    """Verbindung aus dem Ist übernehmen: liefert (lokaler Port, Gegenport) für ein Kabel, das dem gesehenen Nachbarn entspricht.
    Rechnet mit dem aktuellen Stand neu, damit nichts übernommen wird, was sich inzwischen geändert hat. ValueError mit Grund, wenn nicht möglich."""
    w = _World()
    if port_id not in w.port:
        raise ValueError("Port nicht gefunden")
    obs = [o for o in db.rows("SELECT * FROM observations WHERE port_id = ?", (port_id,))
           if not (_MAC.match(o["neighbor_name"]) and not w.device_by_neighbor(o["neighbor_name"], o["neighbor_address"]))]
    ist = _merge([w.resolve(o) for o in obs])
    if port_id in w.cable or port_id in w.peer:
        raise ValueError("Am Port ist bereits eine Verbindung dokumentiert")
    target = w.adopt_target(port_id, ist)
    if not target:
        raise ValueError("Keine eindeutige, freie Gegenstelle im Bestand – bitte von Hand dokumentieren")
    return port_id, target
