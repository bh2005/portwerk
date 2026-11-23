"""VLAN/Portprofil als Attribut eines Ports: prüfen, beschreiben, anwenden (mit Historie). Nur Dokumentation.

Konfiguration = {port_mode, access_vid, voice_vid, native_vid, allowed_vids, profile_id}
* access: Access-VLAN (Pflicht) und optional Voice-VLAN
* trunk: erlaubte VLANs (leer = alle) und optional Native-VLAN
* port_mode leer = nicht dokumentiert (alle Werte leer)
Ein Profil füllt die Werte; profile_id merkt sich, welches Profil zuletzt angewendet wurde.
"""
from __future__ import annotations

import json
import time
from typing import Optional

from fastapi import HTTPException

from . import db

FIELDS = ("port_mode", "access_vid", "voice_vid", "native_vid", "allowed_vids", "profile_id")
MODES = ("", "access", "trunk")
EMPTY = {"port_mode": "", "access_vid": None, "voice_vid": None, "native_vid": None, "allowed_vids": "", "profile_id": None}
SWITCH_TYPES = ("switch", "router", "firewall")


def parse_vids(text: Optional[str]) -> str:
    """„10, 20,40-45“ → „10,20,40-45“ (sortiert, zusammengefasst). Leer bleibt leer (= alle)."""
    if not text or not str(text).strip():
        return ""
    nums: set[int] = set()
    for part in str(text).replace(";", ",").replace(" ", "").split(","):
        if not part:
            continue
        lo, _, hi = part.partition("-")
        try:
            a, b = int(lo), int(hi) if hi else int(lo)
        except ValueError:
            raise HTTPException(400, f"VLAN-Liste: „{part}“ ist keine Zahl bzw. kein Bereich")
        if not (1 <= a <= 4094 and 1 <= b <= 4094) or a > b:
            raise HTTPException(400, f"VLAN-Liste: „{part}“ liegt nicht im Bereich 1–4094")
        nums.update(range(a, b + 1))
    out, run = [], []
    for n in sorted(nums):
        if run and n == run[-1] + 1:
            run.append(n)
            continue
        if run:
            out.append(str(run[0]) if len(run) == 1 else f"{run[0]}-{run[-1]}")
        run = [n]
    if run:
        out.append(str(run[0]) if len(run) == 1 else f"{run[0]}-{run[-1]}")
    return ",".join(out)


def vid_set(text: str) -> set[int]:
    out: set[int] = set()
    for part in (text or "").split(","):
        if part:
            lo, _, hi = part.partition("-")
            out.update(range(int(lo), int(hi or lo) + 1))
    return out


def _vid(v, what: str) -> Optional[int]:
    if v in (None, ""):
        return None
    try:
        v = int(v)
    except (TypeError, ValueError):
        raise HTTPException(400, f"{what}: Zahl 1–4094 erwartet")
    if not 1 <= v <= 4094:
        raise HTTPException(400, f"{what}: Zahl 1–4094 erwartet")
    return v


def profile(pid: Optional[int]) -> Optional[dict]:
    return db.row("SELECT * FROM port_profiles WHERE id = ?", (pid,)) if pid else None


def normalize(cfg: Optional[dict]) -> dict:
    """Eingabe prüfen und vervollständigen; mit ``profile_id`` und ohne eigene Werte gelten die Werte des Profils."""
    c = {**EMPTY, **{k: v for k, v in (cfg or {}).items() if k in FIELDS}}
    if c["profile_id"]:
        p = profile(c["profile_id"])
        if not p:
            raise HTTPException(404, "Portprofil nicht gefunden")
        if not c["port_mode"]:
            c.update({k: p[k] for k in ("port_mode", "access_vid", "voice_vid", "native_vid", "allowed_vids")})
    if c["port_mode"] not in MODES:
        raise HTTPException(400, "Modus: access, trunk oder leer")
    c["access_vid"], c["voice_vid"], c["native_vid"] = (_vid(c["access_vid"], "Access-VLAN"), _vid(c["voice_vid"], "Voice-VLAN"),
                                                         _vid(c["native_vid"], "Native-VLAN"))
    c["allowed_vids"] = parse_vids(c["allowed_vids"])
    if c["port_mode"] == "access":
        if not c["access_vid"]:
            raise HTTPException(400, "Access-Port: Access-VLAN angeben")
        c["native_vid"], c["allowed_vids"] = None, ""
    elif c["port_mode"] == "trunk":
        c["access_vid"], c["voice_vid"] = None, None
    else:
        c = {**EMPTY}
    return c


def current(port_id: int) -> dict:
    r = db.row(f"SELECT {', '.join(FIELDS)} FROM ports WHERE id = ?", (port_id,))
    return {k: r[k] for k in FIELDS} if r else {**EMPTY}


def vlan_names(site_id: Optional[int]) -> dict[int, str]:
    """VLAN-Namen aus dem Katalog (standortbezogene vor globalen)."""
    rows = db.rows("SELECT vid, name, site_id FROM vlans WHERE site_id IS NULL OR site_id = ? ORDER BY site_id IS NOT NULL", (site_id,))
    return {r["vid"]: r["name"] for r in rows}


def describe(c: dict, names: Optional[dict] = None) -> str:
    """Kurzbeschreibung, z. B. „Drucker: Access 20 (Drucker)“, „Trunk 10,20 · native 99“."""
    if not c or not c.get("port_mode"):
        return ""
    names = names or {}
    n = lambda v: f"{v} ({names[v]})" if v in names else str(v)  # noqa: E731
    if c["port_mode"] == "access":
        s = f"Access {n(c['access_vid'])}" + (f" + Voice {n(c['voice_vid'])}" if c.get("voice_vid") else "")
    else:
        s = f"Trunk {c['allowed_vids'] or 'alle'}" + (f" · native {n(c['native_vid'])}" if c.get("native_vid") else "")
    p = profile(c.get("profile_id"))
    return f"{p['name']}: {s}" if p else s


def out(c: dict, site_id: Optional[int]) -> dict:
    p = profile(c.get("profile_id"))
    return {**{k: c.get(k) for k in FIELDS}, "profile": {"id": p["id"], "name": p["name"]} if p else None,
            "text": describe(c, vlan_names(site_id))}


def apply(port_id: int, cfg: dict, by: str, workorder_id: Optional[int] = None, reason: str = "manual") -> bool:
    """Konfiguration am Port dokumentieren; Änderungen landen in der Historie. Liefert True bei Änderung."""
    new = normalize(cfg)
    old = current(port_id)
    if old == new:
        return False
    db.execute(f"UPDATE ports SET {', '.join(f'{k} = ?' for k in FIELDS)} WHERE id = ?", (*[new[k] for k in FIELDS], port_id))
    p = db.row("SELECT p.name, d.hostname FROM ports p JOIN devices d ON d.id = p.device_id WHERE p.id = ?", (port_id,))
    db.execute("""INSERT INTO port_config_history(port_id, host, port_name, before, after, changed_by, workorder_id, reason, changed_at)
                  VALUES (?,?,?,?,?,?,?,?,?)""",
               (port_id, p["hostname"] if p else "", p["name"] if p else "", json.dumps(old), json.dumps(new), by, workorder_id, reason, time.time()))
    return True
