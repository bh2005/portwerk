"""Aufräumbericht: Stellen im Bestand, die nachgepflegt oder bereinigt werden sollten.

* ``provisional``   vorläufige Kabel (aus dem Soll/Ist-Abgleich übernommen) – Dosen/Patchfelder noch nachtragen; „alt“ ab ``days`` Tagen
* ``not_seen``      dokumentierte Verbindungen, die LLDP/CDP nicht sieht, obwohl das Gegenüber Nachbarn meldet (tote Patchung?)
* ``expired``       abgelaufene Port-Reservierungen (blockieren nichts mehr, stehen aber noch in der Liste)
* ``stale_orders``  offene Patchaufträge, die seit ``days`` Tagen nicht mehr geändert wurden
* ``planned``       Geräte im Status „geplant“, die in keinem offenen Auftrag vorkommen

Die Wochenmail (``weekly_mail``) geht an die globalen Administratoren (abbestellbar im Profil) und nur, wenn es etwas zu berichten gibt.
"""
from __future__ import annotations

import time
from datetime import date
from typing import Optional

from . import access, compare, db, reservations
from .auth import Principal

OPEN_STATES = ("draft", "submitted", "approved", "in_progress", "done", "rework")
STATUS_LABELS = {"draft": "Entwurf", "submitted": "eingereicht", "approved": "freigegeben", "in_progress": "in Arbeit",
                 "done": "ausgeführt", "rework": "Nacharbeit"}
SECTIONS = {"provisional": "Vorläufige Kabel", "not_seen": "Verbindungen, die LLDP nicht sieht", "expired": "Abgelaufene Reservierungen",
            "stale_orders": "Liegengebliebene Aufträge", "planned": "Geplante Geräte ohne Auftrag"}
DAY = 86400.0


def _age(ts: Optional[float], now: float) -> Optional[int]:
    return int((now - ts) // DAY) if ts else None


def _site_ok(me: Principal, site_id: Optional[int], only: Optional[int]) -> bool:
    if only and site_id != only:
        return False
    vs = access.visible_sites(me)
    return vs is None or site_id in vs


def provisional(me: Principal, site_id: Optional[int], days: int, now: float) -> list[dict]:
    rows = db.rows("""SELECT c.id, c.port_a_id, c.port_b_id, c.cable_label, c.created_by, c.created_at, c.note,
                             pa.name AS a_port, da.id AS a_dev, da.hostname AS a_host, la.site_id AS a_site,
                             pb.name AS b_port, db_.id AS b_dev, db_.hostname AS b_host, lb.site_id AS b_site
                      FROM cables c
                      JOIN ports pa ON pa.id = c.port_a_id JOIN devices da ON da.id = pa.device_id LEFT JOIN locations la ON la.id = da.location_id
                      JOIN ports pb ON pb.id = c.port_b_id JOIN devices db_ ON db_.id = pb.device_id LEFT JOIN locations lb ON lb.id = db_.location_id
                      WHERE c.provisional = 1 ORDER BY c.created_at, c.id""")
    out = []
    for r in rows:
        if not (_site_ok(me, r["a_site"], site_id) or _site_ok(me, r["b_site"], site_id)):
            continue                                                      # ein Ende im eigenen Bereich genügt (wie die Kabelliste)
        age = _age(r["created_at"], now)
        out.append({"cable_id": r["id"], "port_id": r["port_a_id"], "label": r["cable_label"],
                    "a": {"device_id": r["a_dev"], "port_id": r["port_a_id"], "text": f"{r['a_host']}:{r['a_port']}"},
                    "b": {"device_id": r["b_dev"], "port_id": r["port_b_id"], "text": f"{r['b_host']}:{r['b_port']}"},
                    "created_by": r["created_by"], "created_at": r["created_at"], "age_days": age, "old": age is not None and age >= days})
    return out


def not_seen(me: Principal, site_id: Optional[int]) -> list[dict]:
    res = compare.compare(me, site_id)
    return [{"device_id": r["device_id"], "device": r["device"], "port_id": r["port_id"], "port": r["port"],
             "soll": r["soll"]["label"] if r["soll"] else "", "via": r["soll"]["via"] if r["soll"] else [], "seen_at": r["seen_at"]}
            for r in res["rows"] if r["status"] == "not_seen"]


def expired(me: Principal, site_id: Optional[int]) -> list[dict]:
    rows = db.rows("""SELECT r.id, r.purpose, r.reserved_by, r.until, p.id AS port_id, p.name AS port, d.id AS device_id, d.hostname, l.site_id
                      FROM port_reservations r JOIN ports p ON p.id = r.port_id JOIN devices d ON d.id = p.device_id
                      LEFT JOIN locations l ON l.id = d.location_id
                      WHERE r.until IS NOT NULL AND r.until < ? ORDER BY r.until, d.hostname, p.name""", (reservations.today(),))
    return [{"id": r["id"], "purpose": r["purpose"], "reserved_by": r["reserved_by"], "until": r["until"], "device_id": r["device_id"],
             "port_id": r["port_id"], "text": f"{r['hostname']}:{r['port']}"} for r in rows if _site_ok(me, r["site_id"], site_id)]


def stale_orders(me: Principal, site_id: Optional[int], days: int, now: float) -> list[dict]:
    ph = ",".join("?" * len(OPEN_STATES))
    rows = db.rows(f"""SELECT w.id, w.number, w.title, w.status, w.created_by, w.updated_at, w.created_at, l.site_id
                       FROM workorders w LEFT JOIN locations l ON l.id = w.location_id
                       WHERE w.status IN ({ph}) AND MAX(w.updated_at, w.created_at) < ? ORDER BY MAX(w.updated_at, w.created_at)""",
                   (*OPEN_STATES, now - days * DAY))
    vs = access.visible_sites(me)
    out = []
    for r in rows:
        if site_id and r["site_id"] != site_id:
            continue
        if vs is not None and r["site_id"] not in vs:
            continue                                                      # Aufträge ohne Ort sehen nur globale Benutzer
        out.append({"id": r["id"], "number": r["number"], "title": r["title"], "status": r["status"], "status_label": STATUS_LABELS[r["status"]],
                    "created_by": r["created_by"], "age_days": _age(max(r["updated_at"] or 0, r["created_at"] or 0), now)})
    return out


def planned(me: Principal, site_id: Optional[int]) -> list[dict]:
    ph = ",".join("?" * len(OPEN_STATES))
    rows = db.rows(f"""SELECT d.id, d.hostname, d.type, d.location_id, l.site_id FROM devices d LEFT JOIN locations l ON l.id = d.location_id
                       WHERE d.status = 'planned' AND NOT EXISTS (
                           SELECT 1 FROM workitems i JOIN workorders w ON w.id = i.workorder_id JOIN ports p ON p.id IN (i.port_a_id, i.port_b_id)
                           WHERE p.device_id = d.id AND w.status IN ({ph}))
                       ORDER BY d.hostname COLLATE NOCASE""", OPEN_STATES)
    from .routers.masterdata import location_path
    return [{"id": r["id"], "hostname": r["hostname"], "type": r["type"], "location": location_path(r["location_id"])}
            for r in rows if _site_ok(me, r["site_id"], site_id)]


def report(me: Principal, site_id: Optional[int] = None, days: int = 30) -> dict:
    now = time.time()
    data = {"provisional": provisional(me, site_id, days, now), "not_seen": not_seen(me, site_id), "expired": expired(me, site_id),
            "stale_orders": stale_orders(me, site_id, days, now), "planned": planned(me, site_id)}
    return {"days": days, "sections": SECTIONS, "counts": {k: len(v) for k, v in data.items()}, **data}


# ── Wochenmail ────────────────────────────────────────────────────────────────

SYSTEM = Principal(kind="user", name="system", roles={"admin"})


def mail_lines(rep: dict) -> list[str]:
    c = rep["counts"]
    lines = ["Aufräumbericht – diese Stellen im Bestand sollten nachgepflegt werden:"]
    for key, title in SECTIONS.items():
        if c[key]:
            lines.append(f"• {title}: {c[key]}")
    old = sum(1 for x in rep["provisional"] if x["old"])
    if old:
        lines.append(f"Davon vorläufige Kabel älter als {rep['days']} Tage: {old}.")
    for x in rep["provisional"][:10]:
        lines.append(f"  – vorläufig: {x['a']['text']} ↔ {x['b']['text']}" + (f" (seit {x['age_days']} Tagen)" if x["age_days"] is not None else ""))
    for x in rep["not_seen"][:10]:
        lines.append(f"  – nicht gesehen: {x['device']}:{x['port']} → {x['soll']}")
    lines.append("Details und Aktionen in Portwerk unter „Aufräumen“.")
    return lines


def week_key(day: date) -> str:
    y, w, _ = day.isocalendar()
    return f"{y}-W{w:02d}"


def weekly_mail(today: Optional[date] = None, force: bool = False) -> int:
    """Montags einmal je Kalenderwoche an die globalen Administratoren (``force``: sofort, z. B. „Testmail“). Liefert die Zahl der Empfänger."""
    from . import notifications
    today = today or date.today()
    key = week_key(today)
    if not force and (today.weekday() != 0 or db.get_setting("cleanup_report_week") == key):
        return 0
    rep = report(SYSTEM)
    db.put_settings({"cleanup_report_week": key})
    if not sum(rep["counts"].values()):
        return 0
    total = sum(rep["counts"].values())
    return notifications.send_cleanup_report(f"[Portwerk] Aufräumbericht: {total} offene Punkte", mail_lines(rep))
