"""E-Mail-Versand (SMTP) für Benachrichtigungen: Einstellungen in ``app_settings`` (Schlüssel ``mail``), in der Verwaltung gepflegt.

Standardmäßig aus. Schutz vor Missbrauch: optionale Freigabeliste für Empfänger-Domains, Höchstzahl Empfänger je Versand,
Rate-Limit je Benutzer, Zeilenumbrüche in Kopfzeilen werden entfernt. Das SMTP-Passwort wird nie an den Browser ausgeliefert.
"""
from __future__ import annotations

import json
import re
import smtplib
import ssl
import threading
import time
from email.message import EmailMessage
from email.utils import formataddr
from typing import Optional

from fastapi import HTTPException

from . import db

SETTING_KEY = "mail"
MAX_RECIPIENTS = 20
RATE_LIMIT = (10, 600)                       # höchstens 10 Versände je Benutzer in 10 Minuten
_EMAIL_RE = re.compile(r"^[^@\s<>,;\"']+@[^@\s<>,;\"']+\.[^@\s<>,;\"']+$")

DEFAULTS = {"enabled": False, "host": "", "port": 25, "security": "none", "username": "", "password": "", "from_addr": "",
            "from_name": "Portwerk", "reply_to": "", "public_url": "", "allowed_domains": [],
            "notify_confirm_suggest": True}             # Freigeber informieren, wenn die LLDP-Prüfung einen Auftrag zur Bestätigung vorschlägt

_sent: dict = {}
_lock = threading.Lock()


def smtp_class():                           # per monkeypatch ersetzbar (Tests)
    return smtplib.SMTP


def smtp_ssl_class():
    return smtplib.SMTP_SSL


def settings() -> dict:
    r = db.row("SELECT value FROM app_settings WHERE key = ?", (SETTING_KEY,))
    return {**DEFAULTS, **(json.loads(r["value"]) if r else {})}


def public() -> dict:
    s = settings()
    out = {k: v for k, v in s.items() if k != "password"}
    out["password_set"] = bool(s.get("password"))
    return out


def validate(v: dict) -> None:
    if v["security"] not in ("none", "starttls", "ssl"):
        raise HTTPException(422, "Verschlüsselung: none, starttls oder ssl")
    if not (1 <= int(v["port"]) <= 65535):
        raise HTTPException(422, "Port 1–65535")
    if v["enabled"] and not (v["host"].strip() and v["from_addr"].strip()):
        raise HTTPException(422, "SMTP-Server und Absenderadresse angeben")
    for k in ("from_addr", "reply_to"):
        if v[k] and not _EMAIL_RE.match(v[k]):
            raise HTTPException(422, f"{'Absender' if k == 'from_addr' else 'Antwortadresse'}: ungültige E-Mail-Adresse")
    if v["public_url"] and not re.match(r"^https?://[^\s]+$", v["public_url"]):
        raise HTTPException(422, "Öffentliche URL muss mit http:// oder https:// beginnen")
    for d in v["allowed_domains"]:
        if not re.match(r"^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", d):
            raise HTTPException(422, f"Ungültige Domain in der Freigabeliste: {d}")


def save(patch: dict) -> dict:
    cur = settings()
    for k, val in patch.items():
        if val is None or k not in DEFAULTS:
            continue
        if k == "password" and val == "":
            continue
        if k == "allowed_domains":
            cur[k] = sorted({d.strip().lower().lstrip("@") for d in val if d.strip()})
        elif isinstance(val, str):
            cur[k] = val.strip().rstrip("/") if k == "public_url" else val.strip()
        else:
            cur[k] = val
    if patch.get("clear_password"):
        cur["password"] = ""
    validate(cur)
    db.put_settings({SETTING_KEY: json.dumps(cur)})
    return public()


def clean_header(s: str) -> str:
    return re.sub(r"[\r\n]+", " ", s or "").strip()


def check_recipients(emails: list[str], cfg: dict) -> list[str]:
    out = []
    for e in emails:
        e = e.strip()
        if not e:
            continue
        if not _EMAIL_RE.match(e):
            raise HTTPException(400, f"Ungültige E-Mail-Adresse: {e}")
        dom = e.rsplit("@", 1)[1].lower()
        if cfg["allowed_domains"] and dom not in cfg["allowed_domains"]:
            raise HTTPException(403, f"Empfänger-Domain {dom} ist nicht freigegeben (Verwaltung → E-Mail)")
        if e.lower() not in [x.lower() for x in out]:
            out.append(e)
    if not out:
        raise HTTPException(400, "Kein Empfänger angegeben")
    if len(out) > MAX_RECIPIENTS:
        raise HTTPException(400, f"Höchstens {MAX_RECIPIENTS} Empfänger je Versand")
    return out


def require_enabled() -> dict:
    cfg = settings()
    if not cfg["enabled"]:
        raise HTTPException(409, "Der E-Mail-Versand ist nicht eingerichtet (Verwaltung → E-Mail)")
    return cfg


def rate_check(actor: str) -> None:
    now = time.time()
    with _lock:
        hist = [t for t in _sent.get(actor, []) if now - t < RATE_LIMIT[1]]
        if len(hist) >= RATE_LIMIT[0]:
            raise HTTPException(429, f"Zu viele Versände – höchstens {RATE_LIMIT[0]} je {RATE_LIMIT[1] // 60} Minuten")
        hist.append(now)
        _sent[actor] = hist


def send(cfg: dict, to: list[str], subject: str, text: str, html: str = "", attachments: Optional[list] = None) -> None:
    """Sendet eine Nachricht (je Empfänger eine eigene Zustellung wäre überzogen – eine Nachricht an alle). Wirft HTTPException 502 bei SMTP-Fehlern."""
    msg = EmailMessage()
    msg["From"] = formataddr((clean_header(cfg["from_name"]), cfg["from_addr"]))
    msg["To"] = ", ".join(to)
    msg["Subject"] = clean_header(subject)[:200]
    if cfg.get("reply_to"):
        msg["Reply-To"] = cfg["reply_to"]
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    for name, data, mime in attachments or []:
        main, sub = mime.split("/", 1)
        msg.add_attachment(data, maintype=main, subtype=sub, filename=clean_header(name))
    try:
        if cfg["security"] == "ssl":
            conn = smtp_ssl_class()(cfg["host"], int(cfg["port"]), timeout=20, context=ssl.create_default_context())
        else:
            conn = smtp_class()(cfg["host"], int(cfg["port"]), timeout=20)
        with conn as s:
            if cfg["security"] == "starttls":
                s.starttls(context=ssl.create_default_context())
            if cfg["username"]:
                s.login(cfg["username"], cfg["password"])
            s.send_message(msg)
    except (OSError, smtplib.SMTPException) as e:
        raise HTTPException(502, f"E-Mail konnte nicht gesendet werden: {type(e).__name__}: {e}")
