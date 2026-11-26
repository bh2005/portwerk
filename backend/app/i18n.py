"""Übersetzung der vom Server erzeugten Texte (Mails, Arbeitsanweisung als PDF, CSV-Arbeitslisten).

Muster wie im Frontend: Der deutsche Text ist der Schlüssel, ``EN`` enthält die englische Fassung; fehlt ein Eintrag, bleibt der Text
deutsch. Platzhalter im Format ``{name}`` werden mit ``t(lang, text, name=…)`` gefüllt.

Welche Sprache gilt?
* Benachrichtigungen: die des Empfängers (``ui_prefs.lang`` im Profil), bei einer Vertretung die der Vertretung.
* „Senden …“ (Auftrag/Patchliste an mehrere Empfänger, auch freie Adressen), Testmail: die des Absenders.
* PDF und CSV: die dessen, der sie abruft (bzw. versendet).
"""
from __future__ import annotations

import json
from typing import Optional

from . import db

LANGS = ("de", "en")

EN = {
    # ── allgemein ────────────────────────────────────────────────────────────
    "In Portwerk öffnen": "Open in Portwerk",
    "Im System öffnen": "Open in the system",
    "Du erhältst diese Nachricht in Vertretung für {who}.": "You are receiving this message as deputy for {who}.",
    "{name} (abwesend bis {until})": "{name} (absent until {until})",
    # Auftragsstatus, Aktionen, Prioritäten, Positionsstatus
    "Entwurf": "Draft", "Eingereicht": "Submitted", "Freigegeben": "Approved", "Abgelehnt": "Rejected", "In Ausführung": "In progress",
    "Ausgeführt": "Carried out", "Bestätigt": "Confirmed", "Nacharbeit": "Rework",
    "Verbindung herstellen": "Connect", "Verbindung trennen": "Disconnect", "Verbindung umstecken": "Re-plug connection", "Gerät einbauen": "Install device",
    "Gerät zurückbauen": "Remove device", "WAN in Betrieb nehmen": "Activate WAN", "WAN ändern": "Change WAN", "WAN kündigen": "Terminate WAN",
    "SIP-Trunk in Betrieb nehmen": "Activate SIP trunk", "SIP-Trunk ändern": "Change SIP trunk", "SIP-Trunk kündigen": "Terminate SIP trunk",
    "Port umkonfigurieren": "Reconfigure port",
    "niedrig": "low", "normal": "normal", "hoch": "high", "kritisch": "critical",
    "offen": "open", "erledigt": "done", "Abweichung": "Deviation", "(ohne Ort)": "(no location)",
    # ── Benachrichtigungen ───────────────────────────────────────────────────
    "[Portwerk] {number} zur Bestätigung vorgeschlagen – LLDP stimmt": "[Portwerk] {number} suggested for confirmation – LLDP matches",
    "Der Patchauftrag {number} „{title}“ ist ausgeführt.": "Patch order {number} “{title}” has been carried out.",
    "Der Patchauftrag {number} „{title}“ ist ausgeführt (von {by}).": "Patch order {number} “{title}” has been carried out (by {by}).",
    "Die LLDP-Prüfung nach dem letzten Checkmk-Import stimmt: {n} Position(en) bestätigt, keine Abweichung.":
        "The LLDP check after the last Checkmk import matches: {n} item(s) confirmed, no deviation.",
    "Bitte prüfen und bestätigen – erst dann wird der Bestand fortgeschrieben.": "Please check and confirm – only then is the inventory updated.",
    "freigegeben": "approved", "abgelehnt": "rejected", "auf Nacharbeit gesetzt": "sent back for rework", "bestätigt": "confirmed",
    "Er kann jetzt ausgeführt werden.": "It can now be carried out.", "Die Ausführung muss nachgebessert werden.": "The execution needs to be reworked.",
    "Der Bestand ist fortgeschrieben.": "The inventory has been updated.",
    "[Portwerk] {number} {word}": "[Portwerk] {number} {word}",
    "Dein Patchauftrag {number} „{title}“ wurde von {actor} {word}.": "Your patch order {number} “{title}” was {word} by {actor}.",
    "[Portwerk] Neuer Benutzer wartet auf Freischaltung: {name}": "[Portwerk] New user waiting for activation: {name}",
    "{name} ({who}) hat sich bei Portwerk angemeldet und hat noch keine Rechte.": "{name} ({who}) has logged in to Portwerk and does not have any permissions yet.",
    "Der Benutzer sieht nur den Hinweis, sich für Rechte an einen Administrator zu wenden.": "The user only sees the notice to contact an administrator for permissions.",
    "Bitte unter Verwaltung → Benutzer eine Rolle oder Standort-Rechte vergeben.": "Please grant a role or site permissions under Administration → Users.",
    "[Portwerk] {number}: LLDP meldet eine Abweichung": "[Portwerk] {number}: LLDP reports a deviation",
    "Bei deinem ausgeführten Patchauftrag {number} „{title}“ passt die LLDP-Meldung nicht zur Planung:":
        "For your carried-out patch order {number} “{title}” the LLDP report does not match the plan:",
    "Bitte prüfen – sonst wird der Auftrag voraussichtlich auf Nacharbeit gesetzt.": "Please check – otherwise the order will probably be sent back for rework.",
    "Diese Port-Reservierungen laufen bald ab ({n}):": "These port reservations expire soon ({n}):",
    "• {port} – „{purpose}“ bis {until}": "• {port} – “{purpose}” until {until}",
    "Verlängern oder freigeben unter „Reservierungen“. Abgelaufene Reservierungen blockieren nichts mehr.":
        "Extend or release them under “Reservations”. Expired reservations no longer block anything.",
    "[Portwerk] {n} Reservierung(en) laufen bald ab": "[Portwerk] {n} reservation(s) expire soon",
    # Aufräumbericht
    "[Portwerk] Aufräumbericht: {n} offene Punkte": "[Portwerk] Clean-up report: {n} open items",
    "Aufräumbericht – diese Stellen im Bestand sollten nachgepflegt werden:": "Clean-up report – these places in the inventory should be updated:",
    "Vorläufige Kabel": "Provisional cables", "Verbindungen, die LLDP nicht sieht": "Connections LLDP does not see", "Abgelaufene Reservierungen": "Expired reservations",
    "Liegengebliebene Aufträge": "Stalled orders", "Geplante Geräte ohne Auftrag": "Planned devices without an order",
    "Davon vorläufige Kabel älter als {days} Tage: {n}.": "Of which provisional cables older than {days} days: {n}.",
    "Davon Verbindungen, die LLDP seit mehr als {days} Tagen nicht sieht: {n}.": "Of which connections LLDP has not seen for more than {days} days: {n}.",
    "  – vorläufig: {a} ↔ {b}": "  – provisional: {a} ↔ {b}", " (seit {n} Tagen)": " (for {n} days)",
    "  – nicht gesehen: {port} → {soll}": "  – not seen: {port} → {soll}",
    "Details und Aktionen in Portwerk unter „Aufräumen“.": "Details and actions in Portwerk under “Clean-up”.",
    # ── Senden, Zuweisen, Testmail ───────────────────────────────────────────
    "Portwerk: Testnachricht": "Portwerk: test message",
    "Das ist eine Testnachricht von Portwerk, gesendet von {name}.\n\nWenn du sie liest, funktioniert der E-Mail-Versand.":
        "This is a test message from Portwerk, sent by {name}.\n\nIf you can read it, email sending works.",
    "Öffnen: {link}": "Open: {link}", "Positionen ({n}):": "Items ({n}):", "Positionen ({n})": "Items ({n})", "Positionen im System ({n}):": "Items in the system ({n}):",
    "… und {n} weitere – vollständige Liste im Anhang.": "… and {n} more – full list attached.", "… und {n} weitere – vollständige Liste im System.": "… and {n} more – full list in the system.",
    "Die Arbeitsliste liegt im Anhang (PDF zum Drucken, CSV für Excel).": "The work list is attached (PDF for printing, CSV for Excel).",
    "Nr": "No.", "Aktion": "Action", "Seite A": "Side A", "Seite B": "Side B", "Kabel": "Cable",
    "Auftrag": "Order", "Status": "Status", "Priorität": "Priority", "Ort": "Location", "Zeitraum": "Period", "Aufträge": "Orders", "Sortierung": "Sorting", "Fortschritt": "Progress",
    "Zugewiesen an": "Assigned to", "Positionen": "Items",
    "nach Ort": "by location", "nach Auftrag": "by order", "Auftragsreihenfolge": "order sequence", "unsortiert": "unsorted",
    "{a} von {b} erledigt": "{a} of {b} done",
    "hat dir den Patchauftrag {number} gesendet.": "sent you patch order {number}.",
    "hat dir eine Patchliste mit {n} Auftrag/Aufträgen gesendet.": "sent you a patch list with {n} order(s).",
    "hat dir den Patchauftrag {number} zugewiesen.": "assigned patch order {number} to you.",
    "hat den Patchauftrag {number} {name} zugewiesen – du erhältst die Nachricht in Vertretung.": "assigned patch order {number} to {name} – you are receiving this message as deputy.",
    "[Portwerk] {number} {title} ({n} Positionen)": "[Portwerk] {number} {title} ({n} items)",
    "[Portwerk] Patchliste {numbers} ({n} Positionen)": "[Portwerk] Patch list {numbers} ({n} items)",
    "[Portwerk] In Vertretung: {number} {title}": "[Portwerk] As deputy: {number} {title}",
    "[Portwerk] Dir zugewiesen: {number} {title}": "[Portwerk] Assigned to you: {number} {title}",
    "{number}-arbeitsliste.csv": "{number}-worklist.csv", "{number}-arbeitsanweisung.pdf": "{number}-work-instruction.pdf",
    "patchliste.csv": "patchlist.csv", "patchliste.pdf": "patchlist.pdf",
    # ── PDF ──────────────────────────────────────────────────────────────────
    "Arbeitsanweisung {number}": "Work instruction {number}", "Patchliste": "Patch list",
    "Portwerk · {title} · erstellt {now}": "Portwerk · {title} · created {now}", " von {by}": " by {by}",
    "Seite {page}/{{nb}}": "Page {page}/{{nb}}", "Auf dem Handy abhaken": "Tick off on the phone", "Keine Positionen.": "No items.",
    "Von (Gerät:Port / Ort)": "From (device:port / location)", "Nach (Gerät:Port / Ort)": "To (device:port / location)", "Bemerkung": "Remark",
    "HE": "U", "(bisher: {old})": "(previously: {old})", "Konfiguration: {cfg}": "Configuration: {cfg}", "Abweichung: {note}": "Deviation: {note}",
    "erledigt: {by}": "done: {by}", "Abweichungen / Bemerkungen": "Deviations / remarks", "Ausgeführt von (Name)": "Carried out by (name)", "Datum": "Date",
    "Unterschrift": "Signature",
    "Angelegt von": "Created by", "Freigegeben von": "Approved by", "Voraussetzung": "Prerequisite", "Ordnung": "Order", "Umfang": "Scope",
    "{total} (erledigt: {done})": "{total} (done: {done})", "Rückbau {number} zuerst bestätigen (jetzt: {status})": "Confirm removal {number} first (now: {status})",
    "Noch nicht freigegeben – nicht ausführen.": "Not approved yet – do not carry out.", "Bereits bestätigt – nur zur Dokumentation.": "Already confirmed – for documentation only.",
    "Erst ausführen, wenn der Rückbau-Auftrag {number} bestätigt ist.": "Only carry out once removal order {number} has been confirmed.",
    "Notiz: {note}": "Note: {note}", "nur offene Positionen": "open items only", "Nicht freigegeben – nicht ausführen: {numbers}": "Not approved – do not carry out: {numbers}",
    # ── CSV ──────────────────────────────────────────────────────────────────
    "Gerät/Port A": "Device/port A", "Gerät/Port B": "Device/port B", "Kabelnummer": "Cable number", "Kabelart": "Cable type", "Länge (m)": "Length (m)",
    "Farbe": "Colour", "Konfiguration": "Configuration", "Notiz": "Note", "Erledigt von": "Done by", "Erledigt am": "Done on", "erledigt ☐": "done ☐", "Ort B": "Location B",
}


def t(lang: Optional[str], text: str, **params) -> str:
    out = EN.get(text, text) if lang == "en" else text
    return out.format(**params) if params else out


def user_lang(u: Optional[dict]) -> str:
    """Sprache eines Benutzers (Zeile aus ``users`` mit ``ui_prefs``); Standard Deutsch."""
    if not u:
        return "de"
    raw = u.get("ui_prefs") if isinstance(u, dict) else None
    if raw is None and u.get("id"):
        r = db.row("SELECT ui_prefs FROM users WHERE id = ?", (u["id"],))
        raw = r["ui_prefs"] if r else ""
    try:
        lang = json.loads(raw or "{}").get("lang")
    except (ValueError, AttributeError):
        lang = None
    return lang if lang in LANGS else "de"


def principal_lang(me) -> str:
    """Sprache des angemeldeten Benutzers (API-Zugänge: Deutsch)."""
    if getattr(me, "user_id", None):
        return user_lang({"id": me.user_id})
    return "de"


# ── Texte aus Prüfungen (LLDP), die in Mails übernommen werden: Muster mit Platzhaltern ──────────────────────────────────
import re as _re

_API = [
    ("{a}: keine LLDP-Daten an beiden Enden", "{a}: no LLDP data at either end"),
    ("{a}: LLDP-Daten älter als die Ausführung", "{a}: LLDP data older than the execution"),
    ("{a}: keine LLDP-Daten", "{a}: no LLDP data"),
    ("{a}: Verbindung ist getrennt", "{a}: connection is disconnected"),
    ("noch verbunden: {a}", "still connected: {a}"),
    ("keine LLDP-Daten von {a}", "no LLDP data from {a}"),
    ("{a} sieht {b}, aber an {c}", "{a} sees {b}, but on {c}"),
    ("{a} sieht stattdessen {b}", "{a} sees {b} instead"),
    ("{a} sieht {b}", "{a} sees {b}"),
    ("{a} meldet keinen Nachbarn", "{a} reports no neighbour"),
    ("keine durchgängige dokumentierte Strecke zum Prüfen", "no end-to-end documented path to check"),
    ("Port fehlt", "Port missing"),
]
_API_RE = [(_re.compile("^" + _re.escape(de).replace(r"\{a\}", "(?P<a>.+?)").replace(r"\{b\}", "(?P<b>.+?)").replace(r"\{c\}", "(?P<c>.+?)") + "$"), en)
           for de, en in _API]


def api(lang: Optional[str], msg: str) -> str:
    """Von Prüfungen erzeugten Text übersetzen (unbekannte Texte bleiben unverändert)."""
    if lang != "en" or not msg:
        return msg
    for rx, en in _API_RE:
        m = rx.match(msg)
        if m:
            return en.format(**m.groupdict())
    return msg
