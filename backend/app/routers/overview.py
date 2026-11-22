"""Kennzahlen für die Übersichtsseite (für Bereichs-Benutzer nur die eigenen Standorte)."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends

from typing import Optional

from fastapi import Query

from .. import access, capacity, db
from ..auth import Principal, current_principal

router = APIRouter(prefix="/api", tags=["übersicht"])


def _where(*parts: str) -> str:
    parts = [p for p in parts if p]
    return (" WHERE " + " AND ".join(parts)) if parts else ""


@router.get("/capacity")
def capacity_report(site_id: Optional[int] = None, warn: float = Query(10.0, ge=0, le=100), me: Principal = Depends(current_principal)):
    """Kapazität: freie/belegte/verplante/reservierte Ports je Kategorie und freie HE je Rack, als Baum je Standort; Engpässe unter ``warn`` % frei."""
    return capacity.report(me, site_id, warn)


@router.get("/capacity/summary")
def capacity_summary(warn: float = Query(10.0, ge=0, le=100), me: Principal = Depends(current_principal)):
    """Kurzfassung für die Übersicht: Anzahl Engpässe und die drei knappsten."""
    r = capacity.report(me, None, warn)
    return {"warn": warn, "alerts": len(r["alerts"]), "worst": r["alerts"][:3]}


@router.get("/stats")
def stats(me: Principal = Depends(current_principal)):
    glob = me.is_global
    sc, sa = access.sites_clause(me, "s.id")                    # Standorte
    lc, la = access.sites_clause(me, "l.site_id")               # Locations
    dc, da = access.device_clause(me, "d")                      # Geräte
    cdc_a, cda_a = access.device_clause(me, "da")               # Kabel: ein Ende im eigenen Bereich genügt
    cdc_b, cda_b = access.device_clause(me, "db_")
    cable_join = ("FROM cables c JOIN ports pa ON pa.id = c.port_a_id JOIN devices da ON da.id = pa.device_id "
                  "JOIN ports pb ON pb.id = c.port_b_id JOIN devices db_ ON db_.id = pb.device_id")
    cable_f = f"({cdc_a} OR {cdc_b})" if cdc_a else ""
    cable_args = tuple(cda_a + cda_b)

    def devices_by(column: str) -> dict:
        return {r[column]: r["n"] for r in db.rows(f"SELECT d.{column} AS {column}, COUNT(*) AS n FROM devices d{_where(dc)} GROUP BY d.{column}", tuple(da))}

    def cables(extra: str = "") -> int:
        return db.row(f"SELECT COUNT(*) AS n {cable_join}{_where(cable_f, extra)}", cable_args)["n"]

    runs = []
    if glob:                                                    # Import-Läufe sind eine globale Information
        runs = db.rows("SELECT * FROM import_runs ORDER BY id DESC LIMIT 5")
        for r in runs:
            r["stats"] = json.loads(r["stats"] or "{}")
            r["dry_run"] = bool(r["dry_run"])
    return {
        "scoped": not glob,
        "sites": db.row(f"SELECT COUNT(*) AS n FROM sites s{_where(sc)}", tuple(sa))["n"],
        "locations": db.row(f"SELECT COUNT(*) AS n FROM locations l{_where(lc)}", tuple(la))["n"],
        "racks": db.row("SELECT COUNT(*) AS n FROM locations l" + _where(lc, "l.kind IN ('rack', 'wallrack', 'cabinet')"), tuple(la))["n"],
        "devices": db.row(f"SELECT COUNT(*) AS n FROM devices d{_where(dc)}", tuple(da))["n"],
        "ports": db.row(f"SELECT COUNT(*) AS n FROM ports p JOIN devices d ON d.id = p.device_id{_where(dc)}", tuple(da))["n"],
        "devices_without_location": db.row("SELECT COUNT(*) AS n FROM devices WHERE location_id IS NULL")["n"] if glob else 0,
        "devices_by_type": devices_by("type"),
        "devices_by_status": devices_by("status"),
        "devices_by_source": devices_by("source"),
        "last_imports": runs,
        "cables": cables(),
        "cables_measured": cables("c.measurement_ok IS NOT NULL"),
        "cables_passed": cables("c.measurement_ok = 1"),
        "cables_failed": cables("c.measurement_ok = 0"),
    }
