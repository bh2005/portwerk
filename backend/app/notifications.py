"""Automatische E-Mail-Benachrichtigungen (ohne Benutzeraktion), je Benutzer abbestellbar („Mein Profil“).

* ``confirm_suggest``     Freigeber: ausgeführter Auftrag zur Bestätigung vorgeschlagen (LLDP stimmt) – nicht an den Ausführenden
* ``assigned``            mir wurde ein Auftrag zugewiesen (Versand in ``routers/notify.py``)
* ``my_orders``           mein Auftrag (angelegt von mir) wurde freigegeben, abgelehnt, auf Nacharbeit gesetzt oder bestätigt
* ``lldp_problem``        LLDP meldet eine Abweichung bei einem Auftrag, den ich ausgeführt habe
* ``reservation_expiry``  meine Reservierung läuft in wenigen Tagen ab (tägliche Prüfung, eine Sammelmail je Person)

Hauptschalter bleibt der E-Mail-Versand in der Verwaltung (für „zur Bestätigung vorgeschlagen“ zusätzlich ``notify_confirm_suggest``).
Versand im Hintergrund; ein Fehler beim Versand stört nie den auslösenden Vorgang. Wer eine Änderung selbst auslöst, bekommt keine Mail dazu.
"""
from __future__ import annotations

import html as _h
import json
import logging
import threading
import time
from datetime import date, timedelta
from typing import Iterable, Optional

from fastapi import HTTPException

from . import audit, db, mailer
from .config import settings

log = logging.getLogger("opp.notifications")
SEND_IN_BACKGROUND = True                    # Tests schalten das ab (synchroner Versand)
REMIND_DAYS = 3                              # so viele Tage vor Ablauf einer Reservierung erinnern
_bg_started = False

PREFS = {"confirm_suggest": "Aufträge zur Bestätigung vorgeschlagen (Freigeber)",
         "assigned": "Mir wurde ein Auftrag zugewiesen",
         "my_orders": "Mein Auftrag wurde freigegeben, abgelehnt, auf Nacharbeit gesetzt oder bestätigt",
         "lldp_problem": "LLDP meldet eine Abweichung bei einem Auftrag, den ich ausgeführt habe",
         "reservation_expiry": f"Meine Reservierung läuft in {REMIND_DAYS} Tagen ab"}


def prefs(raw: str) -> dict:
    """Gespeicherte Einstellungen eines Benutzers; fehlende Schlüssel = an."""
    try:
        stored = json.loads(raw) if raw else {}
    except ValueError:
        stored = {}
    return {k: bool(stored.get(k, True)) for k in PREFS}


def wants(user: dict, key: str) -> bool:
    return prefs(user.get("notify_prefs") or "")[key]


def _user(username: Optional[str]) -> Optional[dict]:
    if not username:
        return None
    return db.row("SELECT id, username, full_name, email, notify_prefs FROM users WHERE username = ? COLLATE NOCASE AND active = 1", (username,))


def _allowed(emails: Iterable[str], cfg: dict) -> list[str]:
    ok = []
    for e in emails:
        try:
            ok += [x for x in mailer.check_recipients([e], cfg) if x.lower() not in (o.lower() for o in ok)]
        except HTTPException:
            log.info("Empfänger übersprungen: %s", e)
    return ok[:mailer.MAX_RECIPIENTS]


def _link(cfg: dict, path: str) -> str:
    return f"{cfg['public_url']}{path}" if cfg.get("public_url") else ""


def _deliver(users: list[dict], key: str, subject: str, lines: list[str], link: str, action: str, entity: str, entity_id) -> int:
    """Gemeinsamer Versand: Hauptschalter, persönliche Einstellung, Domain-Filter, Hintergrund, Audit-Log."""
    cfg = mailer.settings()
    if not cfg["enabled"]:
        return 0
    to = _allowed([u["email"] for u in users if u and u.get("email") and wants(u, key)], cfg)
    if not to:
        return 0
    text = "\n".join(lines) + (f"\n\n{link}\n" if link else "\n")
    html = "".join(f"<p>{_h.escape(x)}</p>" for x in lines if x) + (f'<p><a href="{_h.escape(link)}">In Portwerk öffnen</a></p>' if link else "")

    def send() -> None:
        try:
            mailer.send(cfg, to, subject, text, html)
            audit.log("system", f"mail.{action}", entity, entity_id, f"{subject} an {', '.join(to)}"[:500])
        except Exception as e:                                           # Versandfehler darf den Vorgang nie stören
            log.warning("Benachrichtigung %s fehlgeschlagen: %s", action, e)
            audit.log("system", f"mail.{action}_failed", entity, entity_id, str(e)[:300])
    if SEND_IN_BACKGROUND:
        threading.Thread(target=send, daemon=True, name=f"mail-{action}").start()
    else:
        send()
    return len(to)


# ── Freigeber: zur Bestätigung vorgeschlagen ──────────────────────────────────

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


def confirm_suggested(wid: int, summary: dict) -> int:
    cfg = mailer.settings()
    if not cfg.get("notify_confirm_suggest", True):
        return 0
    w = db.row("SELECT id, number, title, finished_by FROM workorders WHERE id = ?", (wid,))
    if not w:
        return 0
    return _deliver(approvers(wid), "confirm_suggest", f"[Portwerk] {w['number']} zur Bestätigung vorgeschlagen – LLDP stimmt",
                    [f"Der Patchauftrag {w['number']} „{w['title']}“ ist ausgeführt" + (f" (von {w['finished_by']})" if w["finished_by"] else "") + ".",
                     f"Die LLDP-Prüfung nach dem letzten Checkmk-Import stimmt: {summary.get('ok', 0)} Position(en) bestätigt, keine Abweichung.",
                     "Bitte prüfen und bestätigen – erst dann wird der Bestand fortgeschrieben."],
                    _link(cfg, f"/workorders/{wid}"), "confirm_suggest", "workorder", wid)


# ── Ersteller: Statuswechsel seines Auftrags ──────────────────────────────────

STATUS_TEXT = {"approve": ("freigegeben", "Er kann jetzt ausgeführt werden."), "reject": ("abgelehnt", ""),
               "rework": ("auf Nacharbeit gesetzt", "Die Ausführung muss nachgebessert werden."),
               "confirm": ("bestätigt", "Der Bestand ist fortgeschrieben.")}


def order_status(wid: int, action: str, actor: str) -> int:
    if action not in STATUS_TEXT:
        return 0
    w = db.row("SELECT id, number, title, created_by FROM workorders WHERE id = ?", (wid,))
    if not w or (w["created_by"] or "").casefold() == (actor or "").casefold():
        return 0                                                         # eigene Aktion: keine Mail an sich selbst
    word, hint = STATUS_TEXT[action]
    cfg = mailer.settings()
    return _deliver([_user(w["created_by"])], "my_orders", f"[Portwerk] {w['number']} {word}",
                    [f"Dein Patchauftrag {w['number']} „{w['title']}“ wurde von {actor} {word}.", hint],
                    _link(cfg, f"/workorders/{wid}"), "order_status", "workorder", wid)


# ── Techniker: LLDP-Abweichung ────────────────────────────────────────────────

def lldp_problem(wid: int, items: list[dict]) -> int:
    w = db.row("SELECT id, number, title, finished_by FROM workorders WHERE id = ?", (wid,))
    if not w:
        return 0
    probs = [i.get("text") or i.get("label", "") for i in items if i.get("status") == "problem"]
    cfg = mailer.settings()
    return _deliver([_user(w["finished_by"])], "lldp_problem", f"[Portwerk] {w['number']}: LLDP meldet eine Abweichung",
                    [f"Bei deinem ausgeführten Patchauftrag {w['number']} „{w['title']}“ passt die LLDP-Meldung nicht zur Planung:",
                     *[f"• {p}" for p in probs[:20]], "Bitte prüfen – sonst wird der Auftrag voraussichtlich auf Nacharbeit gesetzt."],
                    _link(cfg, f"/workorders/{wid}"), "lldp_problem", "workorder", wid)


# ── Reservierungen: Erinnerung vor Ablauf ─────────────────────────────────────

def reservation_reminders(today: Optional[date] = None) -> int:
    """Reservierungen, die in höchstens REMIND_DAYS Tagen ablaufen und noch nicht erinnert wurden: eine Mail je Person."""
    today = today or date.today()
    rows = db.rows("""SELECT r.id, r.purpose, r.until, r.reserved_by, p.name AS port, d.hostname FROM port_reservations r
                      JOIN ports p ON p.id = r.port_id JOIN devices d ON d.id = p.device_id
                      WHERE r.reminded_at IS NULL AND r.until IS NOT NULL AND r.until >= ? AND r.until <= ?
                      ORDER BY r.reserved_by, r.until, d.hostname, p.name""",
                   (today.isoformat(), (today + timedelta(days=REMIND_DAYS)).isoformat()))
    by_user: dict[str, list[dict]] = {}
    for r in rows:
        by_user.setdefault(r["reserved_by"], []).append(r)
    cfg = mailer.settings()
    sent = 0
    for username, res in by_user.items():
        lines = [f"Diese Port-Reservierungen laufen bald ab ({len(res)}):",
                 *[f"• {r['hostname']}:{r['port']} – „{r['purpose']}“ bis {r['until']}" for r in res[:50]],
                 "Verlängern oder freigeben unter „Reservierungen“. Abgelaufene Reservierungen blockieren nichts mehr."]
        sent += _deliver([_user(username)], "reservation_expiry", f"[Portwerk] {len(res)} Reservierung(en) laufen bald ab", lines,
                         _link(cfg, "/reservations"), "reservation_expiry", "port", ",".join(str(r["id"]) for r in res[:50])) > 0
    if rows:
        db.execute(f"UPDATE port_reservations SET reminded_at = ? WHERE id IN ({','.join('?' * len(rows))})", (time.time(), *[r["id"] for r in rows]))
    return sent


def start_background(interval: float = 3600.0) -> None:
    """Tägliche Erinnerungen (stündlich geprüft; jede Reservierung wird nur einmal erinnert)."""
    global _bg_started
    if _bg_started or not settings.notify_background:
        return
    _bg_started = True

    def loop() -> None:
        time.sleep(120)
        while True:
            try:
                reservation_reminders()
            except Exception:
                log.exception("Erinnerungen")
            time.sleep(interval)
    threading.Thread(target=loop, daemon=True, name="notify-reminders").start()
