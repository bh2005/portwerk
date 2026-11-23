"""VLAN-Katalog, Portprofile und dokumentierte Port-Konfiguration (VLAN/Profil je Port, mit Historie)."""
from __future__ import annotations

import json
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .. import access, audit, db, portcfg
from ..access import require_writer
from ..auth import Principal, current_principal, require_master_write
from . import masterdata

router = APIRouter(prefix="/api", tags=["vlan"])


class VlanIn(BaseModel):
    site_id: Optional[int] = None                     # leer = für alle Standorte
    vid: int = Field(ge=1, le=4094)
    name: str = Field(min_length=1, max_length=80)
    note: str = Field(default="", max_length=500)


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    port_mode: str = "access"
    access_vid: Optional[int] = None
    voice_vid: Optional[int] = None
    native_vid: Optional[int] = None
    allowed_vids: str = Field(default="", max_length=500)
    note: str = Field(default="", max_length=500)


class PortConfigIn(BaseModel):
    port_mode: str = ""
    access_vid: Optional[int] = None
    voice_vid: Optional[int] = None
    native_vid: Optional[int] = None
    allowed_vids: str = Field(default="", max_length=500)
    profile_id: Optional[int] = None


# ── VLAN-Katalog ──────────────────────────────────────────────────────────────

def _vlan_write(me: Principal, site_id: Optional[int]) -> None:
    if site_id is None:
        if not me.can_write_master:
            raise HTTPException(403, "VLANs für alle Standorte pflegen nur Administratoren")
    else:
        access.require_write(me, site_id)


def _usage(vid: int, site_id: Optional[int], me: Principal) -> list[dict]:
    """Ports, die dieses VLAN führen (Access, Voice, Native oder in der Trunk-Liste) – im eigenen Bereich, optional nur an einem Standort."""
    clause, args = access.device_clause(me, "d")
    where = [clause] if clause else []
    if site_id is not None:
        where.append("d.location_id IN (SELECT id FROM locations WHERE site_id = ?)"); args = [*args, site_id]
    rows = db.rows(f"""SELECT p.id, p.name, p.port_mode, p.access_vid, p.voice_vid, p.native_vid, p.allowed_vids, d.id AS device_id, d.hostname
                       FROM ports p JOIN devices d ON d.id = p.device_id
                       WHERE p.port_mode <> '' {('AND ' + ' AND '.join(where)) if where else ''}""", tuple(args))
    out = []
    for r in rows:
        roles = [k for k, col in (("access", "access_vid"), ("voice", "voice_vid"), ("native", "native_vid")) if r[col] == vid]
        if r["port_mode"] == "trunk" and (not r["allowed_vids"] or vid in portcfg.vid_set(r["allowed_vids"])):
            roles.append("trunk")
        if roles:
            out.append({"port_id": r["id"], "port": r["name"], "device_id": r["device_id"], "hostname": r["hostname"], "as": roles})
    nk = masterdata._natural_key
    return sorted(out, key=lambda x: (nk(x["hostname"]), nk(x["port"])))


@router.get("/vlans")
def list_vlans(site_id: Optional[int] = None, me: Principal = Depends(current_principal)):
    """VLAN-Katalog: globale VLANs und die der sichtbaren Standorte (mit ``site_id`` nur dieser Standort plus globale)."""
    vis = access.visible_sites(me)
    rows = db.rows("""SELECT v.*, s.code AS site_code FROM vlans v LEFT JOIN sites s ON s.id = v.site_id
                      ORDER BY v.vid, v.site_id IS NOT NULL, s.code""")
    rows = [r for r in rows if (r["site_id"] is None or vis is None or r["site_id"] in vis) and (site_id is None or r["site_id"] in (None, site_id))]
    for r in rows:
        r["ports"] = len(_usage(r["vid"], r["site_id"], me))
    return rows


@router.post("/vlans", status_code=201)
def create_vlan(body: VlanIn, me: Principal = Depends(require_writer)):
    _vlan_write(me, body.site_id)
    try:
        vid = db.execute("INSERT INTO vlans(site_id, vid, name, note) VALUES (?,?,?,?)", (body.site_id, body.vid, body.name.strip(), body.note.strip()))
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"VLAN {body.vid} gibt es für diesen Bereich schon")
    audit.log(me.name, "vlan.create", "vlan", vid, f"{body.vid} {body.name}")
    return db.row("SELECT * FROM vlans WHERE id = ?", (vid,))


@router.put("/vlans/{vid_id}")
def update_vlan(vid_id: int, body: VlanIn, me: Principal = Depends(require_writer)):
    v = db.row("SELECT * FROM vlans WHERE id = ?", (vid_id,))
    if not v:
        raise HTTPException(404, "VLAN nicht gefunden")
    _vlan_write(me, v["site_id"]); _vlan_write(me, body.site_id)
    try:
        db.execute("UPDATE vlans SET site_id = ?, vid = ?, name = ?, note = ? WHERE id = ?", (body.site_id, body.vid, body.name.strip(), body.note.strip(), vid_id))
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"VLAN {body.vid} gibt es für diesen Bereich schon")
    audit.log(me.name, "vlan.update", "vlan", vid_id, f"{body.vid} {body.name}")
    return db.row("SELECT * FROM vlans WHERE id = ?", (vid_id,))


@router.delete("/vlans/{vid_id}")
def delete_vlan(vid_id: int, me: Principal = Depends(require_writer)):
    v = db.row("SELECT * FROM vlans WHERE id = ?", (vid_id,))
    if not v:
        raise HTTPException(404, "VLAN nicht gefunden")
    _vlan_write(me, v["site_id"])
    db.execute("DELETE FROM vlans WHERE id = ?", (vid_id,))
    audit.log(me.name, "vlan.delete", "vlan", vid_id, f"{v['vid']} {v['name']}")
    return {"ok": True}                                    # Ports behalten ihre VLAN-Nummer; nur der Name aus dem Katalog fehlt dann


@router.get("/vlans/usage")
def vlan_usage(vid: int = Query(ge=1, le=4094), site_id: Optional[int] = None, me: Principal = Depends(current_principal)):
    """Welche Ports führen dieses VLAN?"""
    if site_id is not None:
        access.require_read(me, site_id, "Standort")
    return _usage(vid, site_id, me)


# ── Portprofile ───────────────────────────────────────────────────────────────

def _profile_values(body: ProfileIn) -> dict:
    if body.port_mode not in ("access", "trunk"):
        raise HTTPException(400, "Profil: Modus access oder trunk")
    c = portcfg.normalize({**body.model_dump(exclude={"name", "note"}), "profile_id": None})
    return {k: c[k] for k in ("port_mode", "access_vid", "voice_vid", "native_vid", "allowed_vids")}


@router.get("/port-profiles")
def list_profiles(_: Principal = Depends(current_principal)):
    rows = db.rows("SELECT * FROM port_profiles ORDER BY name COLLATE NOCASE")
    for r in rows:
        r["text"] = portcfg.describe({**r, "profile_id": None})
        r["ports"] = db.row("SELECT COUNT(*) AS n FROM ports WHERE profile_id = ?", (r["id"],))["n"]
    return rows


@router.post("/port-profiles", status_code=201)
def create_profile(body: ProfileIn, me: Principal = Depends(require_master_write)):
    v = _profile_values(body)
    try:
        pid = db.execute("""INSERT INTO port_profiles(name, port_mode, access_vid, voice_vid, native_vid, allowed_vids, note) VALUES (?,?,?,?,?,?,?)""",
                         (body.name.strip(), v["port_mode"], v["access_vid"], v["voice_vid"], v["native_vid"], v["allowed_vids"], body.note.strip()))
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"Profil „{body.name}“ gibt es schon")
    audit.log(me.name, "port_profile.create", "port_profile", pid, body.name)
    return db.row("SELECT * FROM port_profiles WHERE id = ?", (pid,))


@router.put("/port-profiles/{pid}")
def update_profile(pid: int, body: ProfileIn, me: Principal = Depends(require_master_write)):
    if not portcfg.profile(pid):
        raise HTTPException(404, "Portprofil nicht gefunden")
    v = _profile_values(body)
    try:
        db.execute("""UPDATE port_profiles SET name=?, port_mode=?, access_vid=?, voice_vid=?, native_vid=?, allowed_vids=?, note=? WHERE id=?""",
                   (body.name.strip(), v["port_mode"], v["access_vid"], v["voice_vid"], v["native_vid"], v["allowed_vids"], body.note.strip(), pid))
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"Profil „{body.name}“ gibt es schon")
    audit.log(me.name, "port_profile.update", "port_profile", pid, body.name)
    return db.row("SELECT * FROM port_profiles WHERE id = ?", (pid,))           # Ports behalten ihre Werte (Profiländerung ≠ Umkonfiguration)


@router.delete("/port-profiles/{pid}")
def delete_profile(pid: int, me: Principal = Depends(require_master_write)):
    p = portcfg.profile(pid)
    if not p:
        raise HTTPException(404, "Portprofil nicht gefunden")
    db.execute("DELETE FROM port_profiles WHERE id = ?", (pid,))
    audit.log(me.name, "port_profile.delete", "port_profile", pid, p["name"])
    return {"ok": True}


# ── Konfiguration eines Ports ─────────────────────────────────────────────────

def _port_or_404(pid: int, me: Principal) -> dict:
    p = db.row("SELECT * FROM ports WHERE id = ?", (pid,))
    if not p:
        raise HTTPException(404, "Port nicht gefunden")
    access.require_read(me, access.site_of_port(pid), "Port")
    return p


@router.put("/ports/{pid}/config")
def set_port_config(pid: int, body: PortConfigIn, me: Principal = Depends(require_writer)):
    """Konfiguration direkt dokumentieren (Administratoren). Im Ablauf geht das über die Auftragsaktion „Port umkonfigurieren“."""
    _port_or_404(pid, me)
    access.require_write(me, access.site_of_port(pid))
    if portcfg.apply(pid, body.model_dump(), me.name, None, "manual"):
        audit.log(me.name, "port.config", "port", pid, portcfg.describe(portcfg.current(pid)) or "nicht dokumentiert")
    return portcfg.out(portcfg.current(pid), access.site_of_port(pid))


@router.get("/ports/{pid}/config-history")
def port_config_history(pid: int, me: Principal = Depends(current_principal)):
    _port_or_404(pid, me)
    names = portcfg.vlan_names(access.site_of_port(pid))
    out = []
    for r in db.rows("""SELECT h.*, w.number AS wo_number FROM port_config_history h LEFT JOIN workorders w ON w.id = h.workorder_id
                        WHERE h.port_id = ? ORDER BY h.changed_at DESC, h.id DESC""", (pid,)):
        out.append({"changed_at": r["changed_at"], "changed_by": r["changed_by"], "reason": r["reason"],
                    "before": portcfg.describe(json.loads(r["before"] or "{}"), names) or "nicht dokumentiert",
                    "after": portcfg.describe(json.loads(r["after"] or "{}"), names) or "nicht dokumentiert",
                    "workorder": {"id": r["workorder_id"], "number": r["wo_number"]} if r["workorder_id"] else None})
    return out
