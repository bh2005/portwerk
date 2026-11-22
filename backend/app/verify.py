"""LLDP-Prüfung ausgeführter Patchaufträge: Stimmt die Verkabelung mit dem überein, was die Geräte per LLDP/CDP melden?

Je Position (vor der Bestätigung – die Kabel stehen dann noch nicht im Bestand):
* herstellen/umstecken: beide Seiten der neuen Verbindung über Patchfelder/Dosen bis zum aktiven Gerät verfolgen; sieht ein Ende das andere?
* trennen: das aktive Ende darf den bisherigen Nachbarn nicht mehr sehen.
LLDP-Daten zählen nur, wenn sie nach dem Abhaken der Position gemeldet wurden (sonst „wartet auf frische Daten“).

Auftrag: ``ok`` (alle prüfbaren Positionen stimmen → Vorschlag: bestätigen), ``problem`` (mindestens eine Abweichung),
``pending`` (noch keine frischen Daten), ``none`` (nichts per LLDP prüfbar).
"""
from __future__ import annotations

import json
import time
from typing import Optional

from . import audit, db
from .compare import THROUGH_TYPES
from .pathtrace import _lldp, _port, _walk, trace

CHECK_STATES = ("in_progress", "done")
LABELS = {"ok": "stimmt", "problem": "Abweichung", "pending": "wartet auf frische LLDP-Daten", "none": "nicht per LLDP prüfbar",
          "unknown": "keine LLDP-Daten", "stale": "LLDP-Daten älter als die Ausführung", "n/a": "nicht prüfbar"}


def _active_end(port_id: Optional[int]) -> tuple[Optional[dict], str]:
    """Aktives Gerät hinter diesem Port (über Durchschleifungen und vorhandene Kabel), oder (None, Grund)."""
    p = _port(port_id) if port_id else None
    if not p:
        return None, "Port fehlt"
    if p["type"] not in THROUGH_TYPES:
        return p, ""
    hops, reason = _walk(p, "through")
    if reason or not hops or hops[-1][1]["type"] in THROUGH_TYPES:
        return None, f"Strecke hinter {p['hostname']}:{p['name']} endet ohne aktives Gerät"
    return hops[-1][1], ""


def _fresh(end: dict, since: Optional[float]) -> bool:
    return bool(end["neighbors_at"]) and (since is None or end["neighbors_at"] >= since)


def _check_connect(a_id: Optional[int], b_id: Optional[int], since: Optional[float]) -> dict:
    a, why_a = _active_end(a_id)
    b, why_b = _active_end(b_id)
    if not a or not b:
        return {"status": "n/a", "text": why_a or why_b}
    label = f"{a['hostname']}:{a['name']} ↔ {b['hostname']}:{b['name']}"
    results = [(_lldp(x, y), x) for x, y in ((a, b), (b, a))]
    usable = [(r, x) for r, x in results if r["status"] not in ("unknown", "n/a")]
    if not usable:
        return {"status": "unknown", "text": f"{label}: keine LLDP-Daten an beiden Enden", "ends": label}
    if not any(_fresh(x, since) for _, x in usable):
        return {"status": "stale", "text": f"{label}: LLDP-Daten älter als die Ausführung", "ends": label}
    fresh = [r for r, x in usable if _fresh(x, since)]
    bad = [r for r in fresh if r["status"] in ("mismatch", "port_mismatch")]
    if bad:
        return {"status": "problem", "text": bad[0]["text"], "ends": label}
    if any(r["status"] == "ok" for r in fresh):
        return {"status": "ok", "text": next(r["text"] for r in fresh if r["status"] == "ok"), "ends": label}
    return {"status": "problem", "text": fresh[0]["text"], "ends": label}                  # not_seen: Ende meldet keinen Nachbarn


def _check_disconnect(port_id: Optional[int], since: Optional[float]) -> dict:
    if not port_id:
        return {"status": "n/a", "text": "Port fehlt"}
    t = trace(port_id, _SYSTEM)
    if not t.get("complete"):
        return {"status": "n/a", "text": "keine durchgängige dokumentierte Strecke zum Prüfen"}
    x, y = _port(t["nodes"][0]["ports"][0]["id"]), _port(t["nodes"][-1]["ports"][-1]["id"])      # die beiden aktiven Enden
    label = f"{x['hostname']}:{x['name']} ↔ {y['hostname']}:{y['name']}"
    results = [(_lldp(p, q), p) for p, q in ((x, y), (y, x))]
    usable = [(r, p) for r, p in results if r["status"] not in ("unknown", "n/a")]
    if not usable:
        return {"status": "unknown", "text": f"{label}: keine LLDP-Daten", "ends": label}
    fresh = [r for r, p in usable if _fresh(p, since)]
    if not fresh:
        return {"status": "stale", "text": f"{label}: LLDP-Daten älter als die Ausführung", "ends": label}
    still = [r for r in fresh if r["status"] == "ok"]
    if still:
        return {"status": "problem", "text": f"noch verbunden: {still[0]['text']}", "ends": label}
    return {"status": "ok", "text": f"{label}: Verbindung ist getrennt", "ends": label}


class _System:                                                                     # Prüfung läuft ohne Benutzer (volle Sicht)
    is_global = True
    scopes: dict = {}


_SYSTEM = _System()


def check_order(wid: int) -> dict:
    items = []
    for it in db.rows("SELECT * FROM workitems WHERE workorder_id = ? ORDER BY idx, id", (wid,)):
        since = it["executed_at"]
        if it["item_status"] != "done":
            r = {"status": "n/a", "text": "Position nicht als erledigt abgehakt"}
        elif it["action"] in ("connect", "move"):
            r = _check_connect(it["port_a_id"], it["port_b_id"], since)
        elif it["action"] == "disconnect":
            r = _check_disconnect(it["port_a_id"], since)
        else:
            r = {"status": "n/a", "text": "nicht per LLDP prüfbar"}
        items.append({"item_id": it["id"], "action": it["action"], **r, "label": LABELS.get(r["status"], r["status"])})
    st = [i["status"] for i in items]
    if "problem" in st:
        overall = "problem"
    elif "stale" in st:
        overall = "pending"
    elif "ok" in st:
        overall = "ok"
    else:
        overall = "none"
    return {"status": overall, "label": LABELS[overall], "items": items,
            "summary": {k: st.count(k) for k in ("ok", "problem", "stale", "unknown", "n/a")}}


def refresh(wid: int, actor: str = "system") -> dict:
    """Prüfen und Ergebnis am Auftrag speichern; Wechsel auf „ok“ bei einem ausgeführten Auftrag kommt ins Audit-Log."""
    w = db.row("SELECT id, number, status, lldp_status FROM workorders WHERE id = ?", (wid,))
    r = check_order(wid)
    now = time.time()
    db.execute("UPDATE workorders SET lldp_status = ?, lldp_checked_at = ?, lldp_detail = ? WHERE id = ?",
               (r["status"], now, json.dumps(r["items"], ensure_ascii=False), wid))
    if w and w["status"] == "done" and r["status"] != w["lldp_status"] and r["status"] in ("ok", "problem"):
        audit.log(actor, f"workorder.lldp_{r['status']}", "workorder", wid,
                  f"{w['number']}: LLDP-Prüfung {r['label']} ({r['summary']['ok']} stimmen, {r['summary']['problem']} Abweichung)")
    return {**r, "checked_at": now}


def refresh_open(actor: str = "system") -> int:
    """Nach einem Import mit LLDP-Daten: alle Aufträge in Ausführung bzw. ausgeführt neu prüfen."""
    ids = [r["id"] for r in db.rows(f"SELECT id FROM workorders WHERE status IN ({','.join('?' * len(CHECK_STATES))})", CHECK_STATES)]
    for wid in ids:
        refresh(wid, actor)
    return len(ids)
