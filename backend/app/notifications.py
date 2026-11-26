"""Automatische E-Mail-Benachrichtigungen (ohne Benutzeraktion), je Benutzer abbestellbar („Mein Profil“).

* ``confirm_suggest``     Freigeber: ausgeführter Auftrag zur Bestätigung vorgeschlagen (LLDP stimmt) – nicht an den Ausführenden
* ``assigned``            mir wurde ein Auftrag zugewiesen (Versand in ``routers/notify.py``)
* ``my_orders``           mein Auftrag (angelegt von mir) wurde freigegeben, abgelehnt, auf Nacharbeit gesetzt oder bestätigt
* ``lldp_problem``        LLDP meldet eine Abweichung bei einem Auftrag, den ich ausgeführt habe
* ``reservation_expiry``  meine Reservierung läuft in wenigen Tagen ab (tägliche Prüfung, eine Sammelmail je Person)
* ``cleanup_report``      globale Administratoren: wöchentlicher Aufräumbericht (montags, nur wenn es offene Punkte gibt)

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

from . import absences, audit, db, i18n, mailer
from .config import settings

log = logging.getLogger("opp.notifications")
SEND_IN_BACKGROUND = True                    # Tests schalten das ab (synchroner Versand)
REMIND_DAYS = 3                              # so viele Tage vor Ablauf einer Reservierung erinnern
_bg_started = False

PREFS = {"confirm_suggest": "Aufträge zur Bestätigung vorgeschlagen (Freigeber)",
         "assigned": "Mir wurde ein Auftrag zugewiesen",
         "my_orders": "Mein Auftrag wurde freigegeben, abgelehnt, auf Nacharbeit gesetzt oder bestätigt",
         "lldp_problem": "LLDP meldet eine Abweichung bei einem Auftrag, den ich ausgeführt habe",
         "reservation_expiry": f"Meine Reservierung läuft in {REMIND_DAYS} Tagen ab",
         "new_user": "Ein neuer Benutzer ohne Rechte hat sich angemeldet (globale Administratoren)",
         "cleanup_report": "Wöchentlicher Aufräumbericht (globale Administratoren)"}


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
    return db.row("SELECT id, username, full_name, email, notify_prefs, roles, ui_prefs FROM users WHERE username = ? COLLATE NOCASE AND active = 1", (username,))


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


def can_see(u: dict, site_id: Optional[int]) -> bool:
    """Globale Rolle oder irgendeine Rolle an diesem Standort."""
    if (u.get("roles") or "").strip(","):
        return True
    return site_id is not None and bool(db.row("SELECT 1 AS x FROM user_scopes WHERE user_id = ? AND site_id = ?", (u["id"], site_id)))


def can_approve(u: dict, site_id: Optional[int]) -> bool:
    roles = set((u.get("roles") or "").split(","))
    if roles & {"freigeber", "admin"}:
        return True
    return site_id is not None and bool(db.row("SELECT 1 AS x FROM user_scopes WHERE user_id = ? AND site_id = ? AND role IN ('freigeber', 'admin')",
                                               (u["id"], site_id)))


def _route(users: list, key: str, eligible) -> tuple[list[dict], dict[int, tuple[dict, list[dict]]]]:
    """Empfänger nach Abwesenheit aufteilen: (direkt, {Vertretung-ID: (Vertretung, [vertretene Personen])}).
    Abwesend mit berechtigter Vertretung → an die Vertretung (nach deren Einstellung); sonst wie bisher an die Person selbst."""
    direct, deputies = [], {}
    for u in users:
        if not u:
            continue
        d = absences.deputy_for(u["id"])
        if d and d["email"] and (eligible is None or eligible(d)):
            if wants(d, key):
                deputies.setdefault(d["id"], (d, []))[1].append(u)
            continue
        if u.get("email") and wants(u, key):
            direct.append(u)
    return direct, deputies


def _deliver(users: list, key: str, compose, link: str, action: str, entity: str, entity_id, eligible=None, wait: bool = False) -> int:
    """Gemeinsamer Versand: Hauptschalter, Abwesenheit/Vertretung, persönliche Einstellung, Domain-Filter, Sprache, Hintergrund, Audit-Log.
    ``compose(lang)`` liefert ``(Betreff, Zeilen)`` in der Sprache der Empfänger (je Sprache eine Mail; Vertretungen in ihrer eigenen).
    ``eligible(vertretung)``: darf die Vertretung diese Nachricht bekommen (Standort, Rolle)?
    ``wait``: sofort und im Aufrufer senden; geliefert wird dann die Zahl der **tatsächlich** versendeten Empfänger (sonst die der geplanten)."""
    cfg = mailer.settings()
    if not cfg["enabled"]:
        return 0
    direct, deputies = _route(users, key, eligible)
    jobs = []                                                            # (Empfänger, Sprache, Betreff, Zeilen)
    by_lang: dict[str, list[str]] = {}
    for u in direct:
        by_lang.setdefault(i18n.user_lang(u), []).append(u["email"])
    for lang, emails in sorted(by_lang.items()):
        to = _allowed(emails, cfg)
        if to:
            subject, lines = compose(lang)
            jobs.append((to, lang, subject, lines))
    direct_ids = {u["id"] for u in direct}
    for d, absent in deputies.values():
        if d["id"] in direct_ids:
            continue                                                     # Vertretung bekommt die Nachricht ohnehin selbst
        dto = _allowed([d["email"]], cfg)
        if dto:
            lang = i18n.user_lang(d)
            who = ", ".join(i18n.t(lang, "{name} (abwesend bis {until})", name=a["full_name"] or a["username"], until=absences.current(a["id"])["end_date"])
                            for a in absent)
            subject, lines = compose(lang)
            jobs.append((dto, lang, subject, [i18n.t(lang, "Du erhältst diese Nachricht in Vertretung für {who}.", who=who), *lines]))
    if not jobs:
        return 0

    def send() -> int:
        done = 0
        for rcpt, lang, subject, ls in jobs:
            text = "\n".join(ls) + (f"\n\n{link}\n" if link else "\n")
            html = "".join(f"<p>{_h.escape(x)}</p>" for x in ls if x) + (f'<p><a href="{_h.escape(link)}">{_h.escape(i18n.t(lang, "In Portwerk öffnen"))}</a></p>' if link else "")
            try:
                mailer.send(cfg, rcpt, subject, text, html)
                done += len(rcpt)
                audit.log("system", f"mail.{action}", entity, entity_id, f"{subject} an {', '.join(rcpt)}"[:500])
            except Exception as e:                                       # Versandfehler darf den Vorgang nie stören
                log.warning("Benachrichtigung %s fehlgeschlagen: %s", action, e)
                audit.log("system", f"mail.{action}_failed", entity, entity_id, str(e)[:300])
        return done
    if wait:
        return send()
    if SEND_IN_BACKGROUND:
        threading.Thread(target=send, daemon=True, name=f"mail-{action}").start()
    else:
        send()
    return sum(len(j[0]) for j in jobs)


# ── Freigeber: zur Bestätigung vorgeschlagen ──────────────────────────────────

def approvers(wid: int) -> list[dict]:
    w = db.row("SELECT w.finished_by, l.site_id FROM workorders w LEFT JOIN locations l ON l.id = w.location_id WHERE w.id = ?", (wid,))
    if not w:
        return []
    rows = db.rows("""SELECT DISTINCT u.id, u.username, u.full_name, u.email, u.notify_prefs, u.roles, u.ui_prefs FROM users u
                      WHERE u.active = 1 AND u.email <> ''
                        AND ((',' || u.roles || ',') LIKE '%,freigeber,%'
                             OR EXISTS (SELECT 1 FROM user_scopes s WHERE s.user_id = u.id AND s.role = 'freigeber' AND s.site_id = ?))""",
                   (w["site_id"],))
    return [u for u in rows if u["username"].casefold() != (w["finished_by"] or "").casefold()
            and (wants(u, "confirm_suggest") or absences.deputy_for(u["id"]))]


def confirm_suggested(wid: int, summary: dict) -> int:
    cfg = mailer.settings()
    if not cfg.get("notify_confirm_suggest", True):
        return 0
    w = db.row("SELECT w.id, w.number, w.title, w.finished_by, l.site_id FROM workorders w LEFT JOIN locations l ON l.id = w.location_id WHERE w.id = ?", (wid,))
    if not w:
        return 0
    fin = (w["finished_by"] or "").casefold()

    def compose(lang: str):
        t = lambda s, **kw: i18n.t(lang, s, **kw)                                               # noqa: E731
        done = (t("Der Patchauftrag {number} „{title}“ ist ausgeführt (von {by}).", number=w["number"], title=w["title"], by=w["finished_by"]) if w["finished_by"]
                else t("Der Patchauftrag {number} „{title}“ ist ausgeführt.", number=w["number"], title=w["title"]))
        return (t("[Portwerk] {number} zur Bestätigung vorgeschlagen – LLDP stimmt", number=w["number"]),
                [done, t("Die LLDP-Prüfung nach dem letzten Checkmk-Import stimmt: {n} Position(en) bestätigt, keine Abweichung.", n=summary.get("ok", 0)),
                 t("Bitte prüfen und bestätigen – erst dann wird der Bestand fortgeschrieben.")])
    return _deliver(approvers(wid), "confirm_suggest", compose,
                    _link(cfg, f"/workorders/{wid}"), "confirm_suggest", "workorder", wid,
                    eligible=lambda d: can_approve(d, w["site_id"]) and d["username"].casefold() != fin)


# ── Ersteller: Statuswechsel seines Auftrags ──────────────────────────────────

STATUS_TEXT = {"approve": ("freigegeben", "Er kann jetzt ausgeführt werden."), "reject": ("abgelehnt", ""),
               "rework": ("auf Nacharbeit gesetzt", "Die Ausführung muss nachgebessert werden."),
               "confirm": ("bestätigt", "Der Bestand ist fortgeschrieben.")}


def order_status(wid: int, action: str, actor: str) -> int:
    if action not in STATUS_TEXT:
        return 0
    w = db.row("SELECT w.id, w.number, w.title, w.created_by, l.site_id FROM workorders w LEFT JOIN locations l ON l.id = w.location_id WHERE w.id = ?", (wid,))
    if not w or (w["created_by"] or "").casefold() == (actor or "").casefold():
        return 0                                                         # eigene Aktion: keine Mail an sich selbst
    word, hint = STATUS_TEXT[action]
    cfg = mailer.settings()

    def compose(lang: str):
        wd = i18n.t(lang, word)
        return (i18n.t(lang, "[Portwerk] {number} {word}", number=w["number"], word=wd),
                [i18n.t(lang, "Dein Patchauftrag {number} „{title}“ wurde von {actor} {word}.", number=w["number"], title=w["title"], actor=actor, word=wd),
                 i18n.t(lang, hint) if hint else ""])
    return _deliver([_user(w["created_by"])], "my_orders", compose,
                    _link(cfg, f"/workorders/{wid}"), "order_status", "workorder", wid, eligible=lambda d: can_see(d, w["site_id"]))


# ── Globale Administratoren: neuer Benutzer wartet auf Freischaltung ──────────

def global_admins() -> list[dict]:
    return db.rows("SELECT id, username, full_name, email, notify_prefs, roles, ui_prefs FROM users WHERE active = 1 AND (',' || roles || ',') LIKE '%,admin,%'")


def new_user_waiting(u: dict) -> int:
    """Hinweis-Mail an die globalen Administratoren: ``u`` hat sich angemeldet und hat noch keine Rechte. Liefert die Zahl der Empfänger
    (0 = nicht versendet, z. B. E-Mail nicht eingerichtet oder kein Administrator mit Adresse)."""
    name = u.get("full_name") or u["username"]
    cfg = mailer.settings()
    is_admin = lambda d: "admin" in (d.get("roles") or "").split(",")                          # noqa: E731 – Vertretung muss selbst globaler Administrator sein
    who = u["username"] + (", " + u["email"] if u.get("email") else "")

    def compose(lang: str):
        t = lambda s, **kw: i18n.t(lang, s, **kw)                                               # noqa: E731
        return (t("[Portwerk] Neuer Benutzer wartet auf Freischaltung: {name}", name=name),
                [t("{name} ({who}) hat sich bei Portwerk angemeldet und hat noch keine Rechte.", name=name, who=who),
                 t("Der Benutzer sieht nur den Hinweis, sich für Rechte an einen Administrator zu wenden."),
                 t("Bitte unter Verwaltung → Benutzer eine Rolle oder Standort-Rechte vergeben.")])
    return _deliver(global_admins(), "new_user", compose,
                    _link(cfg, "/admin"), "new_user", "user", u["id"], eligible=is_admin, wait=True)


def send_cleanup_report(compose) -> int:
    """Aufräumbericht (``cleanup.weekly_mail``) an die globalen Administratoren; Vertretung nur, wenn sie selbst globaler Administrator ist.
    ``compose(lang)`` → (Betreff, Zeilen)."""
    is_admin = lambda d: "admin" in (d.get("roles") or "").split(",")                          # noqa: E731
    return _deliver(global_admins(), "cleanup_report", compose, _link(mailer.settings(), "/cleanup"), "cleanup_report", "report", "cleanup",
                    eligible=is_admin, wait=True)


# ── Techniker: LLDP-Abweichung ────────────────────────────────────────────────

def lldp_problem(wid: int, items: list[dict]) -> int:
    w = db.row("SELECT w.id, w.number, w.title, w.finished_by, l.site_id FROM workorders w LEFT JOIN locations l ON l.id = w.location_id WHERE w.id = ?", (wid,))
    if not w:
        return 0
    probs = [i.get("text") or i.get("label", "") for i in items if i.get("status") == "problem"]
    cfg = mailer.settings()

    def compose(lang: str):
        t = lambda s, **kw: i18n.t(lang, s, **kw)                                               # noqa: E731
        return (t("[Portwerk] {number}: LLDP meldet eine Abweichung", number=w["number"]),
                [t("Bei deinem ausgeführten Patchauftrag {number} „{title}“ passt die LLDP-Meldung nicht zur Planung:", number=w["number"], title=w["title"]),
                 *[f"• {i18n.api(lang, p)}" for p in probs[:20]], t("Bitte prüfen – sonst wird der Auftrag voraussichtlich auf Nacharbeit gesetzt.")])
    return _deliver([_user(w["finished_by"])], "lldp_problem", compose,
                    _link(cfg, f"/workorders/{wid}"), "lldp_problem", "workorder", wid, eligible=lambda d: can_see(d, w["site_id"]))


# ── Reservierungen: Erinnerung vor Ablauf ─────────────────────────────────────

def reservation_reminders(today: Optional[date] = None) -> int:
    """Reservierungen, die in höchstens REMIND_DAYS Tagen ablaufen und noch nicht erinnert wurden: eine Mail je Person."""
    today = today or date.today()
    rows = db.rows("""SELECT r.id, r.purpose, r.until, r.reserved_by, p.name AS port, d.hostname, l.site_id FROM port_reservations r
                      JOIN ports p ON p.id = r.port_id JOIN devices d ON d.id = p.device_id LEFT JOIN locations l ON l.id = d.location_id
                      WHERE r.reminded_at IS NULL AND r.until IS NOT NULL AND r.until >= ? AND r.until <= ?
                      ORDER BY r.reserved_by, r.until, d.hostname, p.name""",
                   (today.isoformat(), (today + timedelta(days=REMIND_DAYS)).isoformat()))
    by_user: dict[str, list[dict]] = {}
    for r in rows:
        by_user.setdefault(r["reserved_by"], []).append(r)
    cfg = mailer.settings()
    sent = 0
    for username, res in by_user.items():
        def compose(lang: str, res=res):
            t = lambda s, **kw: i18n.t(lang, s, **kw)                                           # noqa: E731
            return (t("[Portwerk] {n} Reservierung(en) laufen bald ab", n=len(res)),
                    [t("Diese Port-Reservierungen laufen bald ab ({n}):", n=len(res)),
                     *[t("• {port} – „{purpose}“ bis {until}", port=f"{r['hostname']}:{r['port']}", purpose=r["purpose"], until=r["until"]) for r in res[:50]],
                     t("Verlängern oder freigeben unter „Reservierungen“. Abgelaufene Reservierungen blockieren nichts mehr.")])
        sent += _deliver([_user(username)], "reservation_expiry", compose,
                         _link(cfg, "/reservations"), "reservation_expiry", "port", ",".join(str(r["id"]) for r in res[:50]),
                         eligible=lambda d, sites={r["site_id"] for r in res}: all(can_see(d, s) for s in sites)) > 0
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
            try:
                from . import cleanup
                cleanup.weekly_mail()
            except Exception:
                log.exception("Aufräumbericht")
            try:
                from . import openplan
                openplan.sync_absences()                                  # nur wenn eingeschaltet
            except Exception:
                log.exception("Abwesenheiten aus OpenPlan")
            time.sleep(interval)
    threading.Thread(target=loop, daemon=True, name="notify-reminders").start()
