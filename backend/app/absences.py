"""Abwesenheit und Vertretung.

Im Zeitraum (Start- und Endtag eingeschlossen) gehen Benachrichtigungen statt an die abwesende Person an ihre Vertretung – sofern die
Vertretung aktiv ist, eine E-Mail-Adresse hat und für den Vorgang berechtigt ist (sonst bleibt es bei der abwesenden Person).
„Meine Aufgaben“ zeigt der Vertretung zusätzlich die Aufträge der vertretenen Personen. Zuweisungen selbst werden nie umgeschrieben.

Abwesenheiten aus OpenPlan (``source = 'openplan'``, Abgleich in ``openplan.sync_absences``) haben keine eigene Vertretung; für sie gilt die
Standard-Vertretung des Benutzers (``users.default_deputy_id``). Wirksame Vertretung = ``EFFECTIVE_DEPUTY``.
"""
from __future__ import annotations

import re
import time
from datetime import date
from typing import Optional

from fastapi import HTTPException

from . import db

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SOURCES = {"openplan": "OpenPlan"}
# Vertretung eines Eintrags: die eingetragene, bei übernommenen Einträgen sonst die Standard-Vertretung (a = user_absences, o = Benutzer)
EFFECTIVE_DEPUTY = "COALESCE(a.deputy_id, CASE WHEN a.source <> '' THEN o.default_deputy_id END)"


def today() -> str:
    return date.today().isoformat()


def current(user_id: int, day: Optional[str] = None) -> Optional[dict]:
    """Laufende Abwesenheit (bei mehreren die mit dem spätesten Ende)."""
    day = day or today()
    return db.row(f"""SELECT a.*, {EFFECTIVE_DEPUTY} AS eff_deputy_id, d.username AS deputy_username, d.full_name AS deputy_full_name, d.active AS deputy_active
                      FROM user_absences a JOIN users o ON o.id = a.user_id LEFT JOIN users d ON d.id = {EFFECTIVE_DEPUTY}
                      WHERE a.user_id = ? AND a.start_date <= ? AND a.end_date >= ? ORDER BY a.end_date DESC LIMIT 1""", (user_id, day, day))


def info(user_id: int, day: Optional[str] = None) -> Optional[dict]:
    """Für Anzeigen: {until, deputy: {id, username, full_name} | None} oder None (anwesend)."""
    a = current(user_id, day)
    if not a:
        return None
    dep = {"id": a["eff_deputy_id"], "username": a["deputy_username"], "full_name": a["deputy_full_name"]} if a["eff_deputy_id"] and a["deputy_active"] else None
    return {"since": a["start_date"], "until": a["end_date"], "deputy": dep, "note": a["note"], "source": a["source"]}


def deputy_for(user_id: int, day: Optional[str] = None) -> Optional[dict]:
    """Vertretung (vollständige Benutzerzeile), wenn die Person gerade abwesend ist und eine aktive Vertretung hat."""
    a = current(user_id, day)
    if not a or not a["eff_deputy_id"]:
        return None
    d = db.row("SELECT * FROM users WHERE id = ? AND active = 1", (a["eff_deputy_id"],))
    if not d or current(d["id"], day):                                    # Vertretung selbst abwesend: keine Weiterleitung
        return None
    return d


def represented_by(user_id: int, day: Optional[str] = None) -> list[dict]:
    """Personen, die dieser Benutzer gerade vertritt."""
    day = day or today()
    return db.rows(f"""SELECT DISTINCT o.id, o.username, o.full_name FROM user_absences a JOIN users o ON o.id = a.user_id
                       WHERE {EFFECTIVE_DEPUTY} = ? AND a.start_date <= ? AND a.end_date >= ?""", (user_id, day, day))


def validate(user_id: int, start: str, end: str, deputy_id: Optional[int]) -> None:
    if not (DATE_RE.match(start or "") and DATE_RE.match(end or "")):
        raise HTTPException(400, "Zeitraum: Datum als JJJJ-MM-TT")
    if end < start:
        raise HTTPException(400, "Das Ende liegt vor dem Beginn")
    if end < today():
        raise HTTPException(400, "Der Zeitraum liegt in der Vergangenheit")
    if deputy_id is not None:
        if deputy_id == user_id:
            raise HTTPException(400, "Man kann sich nicht selbst vertreten")
        if not db.row("SELECT id FROM users WHERE id = ? AND active = 1", (deputy_id,)):
            raise HTTPException(404, "Vertretung nicht gefunden")


def create(user_id: int, start: str, end: str, deputy_id: Optional[int], note: str, by: str) -> dict:
    validate(user_id, start, end, deputy_id)
    aid = db.execute("INSERT INTO user_absences(user_id, start_date, end_date, deputy_id, note, created_by, created_at) VALUES (?,?,?,?,?,?,?)",
                     (user_id, start, end, deputy_id, note.strip()[:300], by, time.time()))
    return out(db.row("SELECT * FROM user_absences WHERE id = ?", (aid,)))


def listing(user_id: int) -> list[dict]:
    """Laufende und kommende Abwesenheiten (vergangene fallen weg)."""
    return [out(r) for r in db.rows(f"""SELECT a.*, {EFFECTIVE_DEPUTY} AS eff_deputy_id FROM user_absences a JOIN users o ON o.id = a.user_id
                                         WHERE a.user_id = ? AND a.end_date >= ? ORDER BY a.start_date""", (user_id, today()))]


def out(r: dict) -> dict:
    eff = r.get("eff_deputy_id", r["deputy_id"])
    dep = db.row("SELECT id, username, full_name FROM users WHERE id = ?", (eff,)) if eff else None
    return {"id": r["id"], "start_date": r["start_date"], "end_date": r["end_date"], "note": r["note"], "deputy": dep,
            "deputy_is_default": bool(dep) and not r["deputy_id"], "source": r["source"], "source_label": SOURCES.get(r["source"], ""),
            "readonly": bool(r["source"]), "current": r["start_date"] <= today() <= r["end_date"]}


def default_deputy(user_id: int) -> Optional[dict]:
    u = db.row("SELECT default_deputy_id FROM users WHERE id = ?", (user_id,))
    return db.row("SELECT id, username, full_name FROM users WHERE id = ?", (u["default_deputy_id"],)) if u and u["default_deputy_id"] else None


def set_default_deputy(user_id: int, deputy_id: Optional[int]) -> Optional[dict]:
    if deputy_id is not None:
        if deputy_id == user_id:
            raise HTTPException(400, "Man kann sich nicht selbst vertreten")
        if not db.row("SELECT id FROM users WHERE id = ? AND active = 1", (deputy_id,)):
            raise HTTPException(404, "Vertretung nicht gefunden")
    db.execute("UPDATE users SET default_deputy_id = ? WHERE id = ?", (deputy_id, user_id))
    return default_deputy(user_id)


def delete(user_id: int, aid: int) -> dict:
    r = db.row("SELECT * FROM user_absences WHERE id = ? AND user_id = ?", (aid, user_id))
    if not r:
        raise HTTPException(404, "Abwesenheit nicht gefunden")
    if r["source"]:
        raise HTTPException(409, f"Diese Abwesenheit kommt aus {SOURCES.get(r['source'], r['source'])} – bitte dort ändern oder löschen")
    db.execute("DELETE FROM user_absences WHERE id = ?", (aid,))
    return r
