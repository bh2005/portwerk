"""Automatische Benachrichtigungen (ohne Benutzeraktion): „Auftrag zur Bestätigung vorgeschlagen“ an die Freigeber.

Auslöser: Die LLDP-Prüfung (``app/verify.py``) stuft einen ausgeführten Auftrag erstmals als stimmig ein. Empfänger: aktive Benutzer mit
E-Mail-Adresse und der Rolle Freigeber – global oder am Standort des Auftrags –, außer wer den Auftrag ausgeführt hat (darf wegen des
Vier-Augen-Prinzips nicht bestätigen). Nicht freigegebene Domains werden übersprungen. Ein Fehler beim Versand stört nie die Prüfung.
"""
from __future__ import annotations

import json
import logging
import threading

from fastapi import HTTPException

from . import audit, db, mailer

log = logging.getLogger("opp.notifications")
SEND_IN_BACKGROUND = True                    # Tests schalten das ab (synchroner Versand)

# Persönliche Benachrichtigungen (je Benutzer abbestellbar, „Mein Profil“); der zentrale Schalter in den E-Mail-Einstellungen bleibt Hauptschalter
PREFS = {"confirm_suggest": "Aufträge zur Bestätigung vorgeschlagen", "assigned": "Mir wurde ein Auftrag zugewiesen"}


def prefs(raw: str) -> dict:
    """Gespeicherte Einstellungen eines Benutzers; fehlende Schlüssel = an."""
    try:
        stored = json.loads(raw) if raw else {}
    except ValueError:
        stored = {}
    return {k: bool(stored.get(k, True)) for k in PREFS}


def wants(user: dict, key: str) -> bool:
    return prefs(user.get("notify_prefs") or "")[key]


def approvers(wid: int) -> list[dict]:
    w = db.row("SELECT w.finished_by, l.site_id FROM workorders w LEFT JOIN locations l ON l.id = w.location_id WHERE w.id = ?", (wid,))
    if not w:
        return []
    rows = db.rows("""SELECT DISTINCT u.id, u.username, u.full_name, u.email, u.notify_prefs FROM users u
                      WHERE u.active = 1 AND u.email <> ''
                        AND ((',' || u.roles || ',') LIKE '%,freigeber,%'
                             OR EXISTS (SELECT 1 FROM user_scopes s WHERE s.user_id = u.id AND s.role = 'freigeber' AND s.site_id = ?))""",
                   (w["site_id"],))
    return [u for u in rows if u["username"].casefold() != (w["finished_by"] or "").casefold() and wants(u, "confirm_suggest")]


def _allowed(emails: list[str], cfg: dict) -> list[str]:
    ok = []
    for e in emails:
        try:
            ok += mailer.check_recipients([e], cfg)
        except HTTPException:
            log.info("Empfänger übersprungen: %s", e)
    return ok[:mailer.MAX_RECIPIENTS]


def confirm_suggested(wid: int, summary: dict) -> int:
    """Freigeber informieren; liefert die Zahl der Empfänger (0 = nichts versandt)."""
    cfg = mailer.settings()
    if not (cfg["enabled"] and cfg.get("notify_confirm_suggest", True)):
        return 0
    w = db.row("SELECT id, number, title, finished_by FROM workorders WHERE id = ?", (wid,))
    to = _allowed([u["email"] for u in approvers(wid)], cfg)
    if not w or not to:
        return 0
    link = f"{cfg['public_url']}/workorders/{wid}" if cfg.get("public_url") else ""
    subject = f"[Portwerk] {w['number']} zur Bestätigung vorgeschlagen – LLDP stimmt"
    text = (f"Der Patchauftrag {w['number']} „{w['title']}“ ist ausgeführt" + (f" (von {w['finished_by']})" if w["finished_by"] else "") + ".\n\n"
            f"Die LLDP-Prüfung nach dem letzten Checkmk-Import stimmt: {summary.get('ok', 0)} Position(en) bestätigt, keine Abweichung.\n"
            "Bitte prüfen und bestätigen – erst dann wird der Bestand fortgeschrieben.\n" + (f"\n{link}\n" if link else ""))
    html = (f"<p>Der Patchauftrag <b>{w['number']}</b> „{_esc(w['title'])}“ ist ausgeführt" + (f" (von {_esc(w['finished_by'])})" if w["finished_by"] else "") + ".</p>"
            f"<p>Die LLDP-Prüfung nach dem letzten Checkmk-Import stimmt: {summary.get('ok', 0)} Position(en) bestätigt, keine Abweichung. "
            "Bitte prüfen und bestätigen – erst dann wird der Bestand fortgeschrieben.</p>" + (f'<p><a href="{_esc(link)}">Auftrag öffnen</a></p>' if link else ""))

    def send() -> None:
        try:
            mailer.send(cfg, to, subject, text, html)
            audit.log("system", "mail.confirm_suggest", "workorder", wid, f"{w['number']} an {', '.join(to)}")
        except Exception as e:                                           # Versandfehler darf die Prüfung nie stören
            log.warning("Benachrichtigung %s fehlgeschlagen: %s", w["number"], e)
            audit.log("system", "mail.confirm_suggest_failed", "workorder", wid, f"{w['number']}: {e}"[:300])
    if SEND_IN_BACKGROUND:
        threading.Thread(target=send, daemon=True, name=f"mail-{wid}").start()
    else:
        send()
    return len(to)


def _esc(s: str) -> str:
    import html as _h
    return _h.escape(s or "")
