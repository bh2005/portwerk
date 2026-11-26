"""Zugriff pro Standort: wer darf welchen Standort sehen und ändern.

* Globale Rollen (users.roles) gelten überall; API-Zugänge sind immer global.
* Wer keine globale Rolle hat, sieht nur die Standorte seiner Zuweisungen (user_scopes) – alles darunter (Locations, Geräte,
  Ports, Kabel, Aufträge). Geräte ohne Location gehören keinem Standort und sind nur global sichtbar.
* Stammdaten ändern darf global der Administrator (oder ein API-Zugang „write“) und je Standort der Bereichs-Administrator.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException

from . import db
from .auth import Principal, current_principal


# ── Standort einer Sache ──────────────────────────────────────────────────────

def site_of_location(location_id: Optional[int]) -> Optional[int]:
    if not location_id:
        return None
    r = db.row("SELECT site_id FROM locations WHERE id = ?", (location_id,))
    return r["site_id"] if r else None


def site_of_device(device_id: int) -> Optional[int]:
    r = db.row("SELECT l.site_id FROM devices d LEFT JOIN locations l ON l.id = d.location_id WHERE d.id = ?", (device_id,))
    return r["site_id"] if r else None


def site_of_port(port_id: int) -> Optional[int]:
    r = db.row("SELECT l.site_id FROM ports p JOIN devices d ON d.id = p.device_id LEFT JOIN locations l ON l.id = d.location_id WHERE p.id = ?",
               (port_id,))
    return r["site_id"] if r else None


# ── Prüfungen ─────────────────────────────────────────────────────────────────

def visible_sites(p: Principal) -> Optional[set]:
    """``None`` = alles sichtbar, sonst die Menge sichtbarer Standort-IDs."""
    return None if p.is_global else set(p.scopes)


def can_read_site(p: Principal, site_id: Optional[int]) -> bool:
    vs = visible_sites(p)
    return vs is None or (site_id is not None and site_id in vs)


def can_write_site(p: Principal, site_id: Optional[int]) -> bool:
    if p.can_write_master:
        return True
    return site_id is not None and "admin" in p.scopes.get(site_id, set())


def require_read(p: Principal, site_id: Optional[int], what: str = "Eintrag") -> None:
    if not can_read_site(p, site_id):
        raise HTTPException(404, f"{what} nicht gefunden")          # 404 statt 403: Existenz nicht verraten


def require_write(p: Principal, site_id: Optional[int]) -> None:
    if not can_write_site(p, site_id):
        raise HTTPException(403, "Keine Berechtigung für diesen Standort")


def require_writer(p: Principal = Depends(current_principal)) -> Principal:
    """Eintrittskarte für Stammdaten-Änderungen: global Schreibender oder Bereichs-Administrator irgendeines Standorts.
    Die Prüfung auf den konkreten Standort folgt im jeweiligen Aufruf (``require_write``)."""
    if p.can_write_master or p.admin_sites:
        return p
    raise HTTPException(403, "Nur für Administratoren, Bereichs-Administratoren oder API-Zugänge mit Umfang „write“")


def require_area(area: str):
    """Abhängigkeit für Sonderbereiche (WAN, Telefonie): nur ausdrücklich zugelassene Benutzer/API-Zugänge und globale Admins."""
    def dep(p: Principal = Depends(current_principal)) -> Principal:
        if not p.can_see(area):
            raise HTTPException(403, "Kein Zugriff auf diesen Bereich (Freigabe durch einen Administrator nötig)")
        return p
    return dep


def require_global(p: Principal = Depends(current_principal)) -> Principal:
    if not p.is_global:
        raise HTTPException(403, "Nur mit globaler Berechtigung")
    return p


# ── SQL-Hilfen ────────────────────────────────────────────────────────────────

def _in(ids: set) -> tuple[str, list]:
    ids = sorted(ids)
    return ",".join("?" * len(ids)) or "NULL", ids


def sites_clause(p: Principal, col: str = "id") -> tuple[str, list]:
    """Bedingung auf eine Standort-ID-Spalte (leer = keine Einschränkung)."""
    vs = visible_sites(p)
    if vs is None:
        return "", []
    ph, args = _in(vs)
    return f"{col} IN ({ph})", args


def device_clause(p: Principal, alias: str = "d") -> tuple[str, list]:
    """Bedingung auf Geräte (über die Location zum Standort); Geräte ohne Location nur für globale Benutzer."""
    vs = visible_sites(p)
    if vs is None:
        return "", []
    ph, args = _in(vs)
    return f"{alias}.location_id IN (SELECT id FROM locations WHERE site_id IN ({ph}))", args
