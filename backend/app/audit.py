"""Audit-Log: wer hat wann was geändert (Tabelle audit_log)."""
from __future__ import annotations

import time
from typing import Optional

from . import db


def log(actor: str, action: str, entity: str = "", entity_id: object = "", detail: str = "") -> None:
    db.execute(
        "INSERT INTO audit_log(ts, actor, action, entity, entity_id, detail) VALUES (?,?,?,?,?,?)",
        (time.time(), actor or "?", action, entity, str(entity_id), detail[:2000]),
    )


def recent(limit: int = 200, actor: Optional[str] = None, entity: Optional[str] = None) -> list[dict]:
    where, args = [], []
    if actor:
        where.append("actor = ?"); args.append(actor)
    if entity:
        where.append("entity = ?"); args.append(entity)
    sql = "SELECT * FROM audit_log" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY id DESC LIMIT ?"
    return db.rows(sql, (*args, max(1, min(limit, 1000))))


def _like(v: str) -> str:
    """Sonderzeichen für LIKE ... ESCAPE '!' entschärfen."""
    return v.replace("!", "!!").replace("%", "!%").replace("_", "!_")


def day_start(day: str, end: bool = False) -> float:
    """``JJJJ-MM-TT`` (Ortszeit des Servers) -> Zeitstempel; ``end`` = Ende dieses Tages (exklusiv). ``ValueError`` bei ungültigem Datum."""
    t = time.mktime(time.strptime(day, "%Y-%m-%d"))
    return t + 86400 if end else t


def search(q: str = "", actor: str = "", action: str = "", entity: str = "", date_from: str = "", date_to: str = "",
           limit: int = 200, offset: int = 0) -> list[dict]:
    """Audit-Einträge mit Suche und Filtern (alle Bedingungen sind UND-verknüpft).

    ``q``: Freitext, jedes Wort muss in Benutzer, Aktion, Objekt oder Detail vorkommen (Groß-/Kleinschreibung egal für ASCII).
    ``actor``: exakter Benutzername. ``action``: Aktion oder Präfix (``workorder`` findet ``workorder.create`` …).
    ``entity``: Objektart. ``date_from``/``date_to``: ``JJJJ-MM-TT``, beide Tage eingeschlossen."""
    where, args = [], []
    for word in q.split():
        where.append("(actor LIKE ? ESCAPE '!' OR action LIKE ? ESCAPE '!' OR entity LIKE ? ESCAPE '!' OR entity_id LIKE ? ESCAPE '!' OR detail LIKE ? ESCAPE '!')")
        args += ["%" + _like(word) + "%"] * 5
    if actor:
        where.append("actor = ?"); args.append(actor)
    if action:
        where.append("action LIKE ? ESCAPE '!'"); args.append(_like(action.strip()) + "%")
    if entity:
        where.append("entity = ?"); args.append(entity)
    if date_from:
        where.append("ts >= ?"); args.append(day_start(date_from))
    if date_to:
        where.append("ts < ?"); args.append(day_start(date_to, end=True))
    sql = "SELECT * FROM audit_log" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY id DESC LIMIT ? OFFSET ?"
    return db.rows(sql, (*args, max(1, min(limit, 1000)), max(0, offset)))


def facets() -> dict:
    """Werte für die Auswahllisten der Filter: Benutzer, Aktionen, Objektarten."""
    col = lambda c: [r[c] for r in db.rows(f"SELECT DISTINCT {c} FROM audit_log WHERE {c} != '' ORDER BY {c} LIMIT 500")]  # noqa: E731
    return {"actors": col("actor"), "actions": col("action"), "entities": col("entity")}
