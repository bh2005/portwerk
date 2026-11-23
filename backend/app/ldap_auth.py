"""Anmeldung gegen LDAP/Active Directory (ldap3) – Standardverfahren wie in den übrigen Projekten.

Zwei Betriebsarten:
* Service-Account (``bind_dn``): Benutzer suchen, dann als gefundener DN mit dem Passwort binden.
* UPN-Bind (nur ``domain``): direkt als ``benutzer@domain`` binden, danach die eigenen Attribute lesen.

Leere Passwörter werden nie weitergereicht (LDAP wertet einen Bind ohne Passwort als anonym = „erfolgreich“).
Die Einstellungen liegen in ``app_settings`` (Schlüssel ``ldap``) und werden in der Verwaltung gepflegt; es ist standardmäßig aus.
Rollen: je Portwerk-Rolle kann eine AD-Gruppe (DN) eingetragen werden; sie werden bei jeder Anmeldung abgeglichen.
"""
from __future__ import annotations

import json
import logging
import re
import ssl
from typing import Any, Optional

from fastapi import HTTPException

from . import db

log = logging.getLogger("opp.ldap")

ROLES = ("admin", "planer", "freigeber", "techniker", "viewer")
_USER_RE = re.compile(r"^[A-Za-z0-9._\-@ ]{1,64}$")
NESTED_RULE = "1.2.840.113556.1.4.1941"
SETTING_KEY = "ldap"

DEFAULTS: dict[str, Any] = {
    "enabled": False, "url": "", "base_dn": "", "domain": "", "bind_dn": "", "bind_password": "",
    "user_filter": "(&(objectClass=user)(sAMAccountName={username}))", "ca_pem": "",
    "required_group": "", "group_roles": {r: "" for r in ROLES},
    "scoped_groups": [],                 # [{group, role, site_id}]: Rolle nur für einen Standort
    "default_role": "viewer",            # Rolle für Benutzer ohne passende Gruppe; leer = Anmeldung verweigern
    "auto_create": True, "nested_groups": True,
}

_last = {"error": "", "url": ""}


# ── Einstellungen ─────────────────────────────────────────────────────────────

def _stored() -> Optional[dict]:
    r = db.row("SELECT value FROM app_settings WHERE key = ?", (SETTING_KEY,))
    return json.loads(r["value"]) if r else None


def settings() -> dict:
    s = _stored() or {}
    out = {**DEFAULTS, **{k: v for k, v in s.items() if k != "group_roles"}}
    out["group_roles"] = {**DEFAULTS["group_roles"], **(s.get("group_roles") or {})}
    return out


def public() -> dict:
    """Für den Browser: ohne Bind-Passwort (nur ``bind_password_set``)."""
    e = settings()
    out = {k: v for k, v in e.items() if k != "bind_password"}
    out["bind_password_set"] = bool(e.get("bind_password"))
    out["from_db"] = _stored() is not None
    return out


def merge(patch: dict) -> dict:
    """Bestehende Werte mit Änderungen verbinden; ``bind_password`` nur bei nicht-leerer Eingabe ersetzen."""
    cur = settings()
    for k, v in patch.items():
        if v is None or k not in DEFAULTS:
            continue
        if k == "bind_password" and v == "":
            continue
        if k == "group_roles":
            cur["group_roles"] = {r: (v.get(r) or "").strip() for r in ROLES}
        elif k == "scoped_groups":
            cur["scoped_groups"] = [{"group": str(x.get("group", "")).strip(), "role": x.get("role"), "site_id": x.get("site_id")}
                                    for x in v if str(x.get("group", "")).strip()]
        else:
            cur[k] = v.strip() if isinstance(v, str) and k != "ca_pem" else v
    if patch.get("clear_bind_password"):
        cur["bind_password"] = ""
    return cur


def urls(cfg: dict) -> list[str]:
    """Konfigurierte Server (mehrere durch Leerzeichen, Komma oder Semikolon getrennt = Ausfallsicherung)."""
    return [u for u in re.split(r"[\s,;]+", (cfg.get("url") or "").strip()) if u]


def validate(v: dict) -> None:
    for u in urls(v):
        if not u.lower().startswith(("ldap://", "ldaps://")):
            raise HTTPException(422, "Die LDAP-URL muss mit ldap:// oder ldaps:// beginnen (mehrere Server mit Leerzeichen oder Komma trennen)")
    if v.get("enabled"):
        if not urls(v):
            raise HTTPException(422, "LDAP-URL fehlt")
        if not (v.get("domain") or v.get("bind_dn")):
            raise HTTPException(422, "Domain (UPN-Bind) oder Bind-DN (Service-Account) angeben")
        if not v.get("base_dn"):
            raise HTTPException(422, "Base-DN fehlt")
    if "{username}" not in (v.get("user_filter") or ""):
        raise HTTPException(422, "Der Benutzerfilter muss {username} enthalten")
    if v.get("default_role") and v["default_role"] not in ROLES:
        raise HTTPException(422, "Standardrolle ungültig")
    if v.get("default_role") == "admin":
        raise HTTPException(422, "Die Standardrolle darf nicht „admin“ sein – Administratoren per Admin-Gruppe festlegen")
    for x in v.get("scoped_groups") or []:
        if x.get("role") not in ROLES:
            raise HTTPException(422, f"Standort-Gruppe „{x.get('group')}“: Rolle ungültig")
        if not isinstance(x.get("site_id"), int) or not db.row("SELECT id FROM sites WHERE id = ?", (x["site_id"],)):
            raise HTTPException(422, f"Standort-Gruppe „{x.get('group')}“: Standort nicht gefunden")
    pem = (v.get("ca_pem") or "").strip()
    if pem and not (pem.startswith("-----BEGIN CERTIFICATE-----") and pem.endswith("-----END CERTIFICATE-----")):
        raise HTTPException(422, "CA-Zertifikat muss im PEM-Format vorliegen (-----BEGIN CERTIFICATE----- …)")


def save(patch: dict) -> dict:
    new = merge(patch)
    validate(new)
    db.put_settings({SETTING_KEY: json.dumps(new)})
    return public()


def enabled(cfg: Optional[dict] = None) -> bool:
    c = cfg or settings()
    return bool(c["enabled"] and urls(c) and (c["domain"] or c["bind_dn"]))


# ── Verbindung ────────────────────────────────────────────────────────────────

def _open_one(cfg: dict, url: str, user: str, password: str):
    """Ein Server: ``(Verbindung, art, detail)``; art ``None`` = gebunden, ``"invalid"`` = Zugangsdaten abgelehnt,
    ``"unavailable"`` = Verbindungs-/TLS-Problem. (Testbar per monkeypatch.)"""
    from ldap3 import Connection, Server, Tls
    from ldap3.core.exceptions import LDAPException
    ssl_on = url.lower().startswith("ldaps")
    try:
        tls = None
        if ssl_on:
            pem = (cfg.get("ca_pem") or "").strip()
            tls = Tls(ca_certs_data=pem or None, validate=ssl.CERT_REQUIRED)
        server = Server(url, use_ssl=ssl_on, tls=tls, connect_timeout=5)
        conn = Connection(server, user=user, password=password, receive_timeout=10)
        if conn.bind():
            return conn, None, ""
        return None, "invalid", str((conn.result or {}).get("description") or "Bind abgelehnt")
    except LDAPException as e:
        return None, "unavailable", "%s: %s" % (type(e).__name__, e)


def _open(cfg: dict, user: str, password: str):
    """Verbindung aufbauen und binden. Mehrere Server werden der Reihe nach versucht, aber nur bei Verbindungsproblemen –
    abgelehnte Zugangsdaten werden nie auf weiteren Servern wiederholt."""
    _last["error"], _last["url"] = "", ""
    errors: list[str] = []
    for url in urls(cfg):
        conn, kind, detail = _open_one(cfg, url, user, password)
        if conn:
            _last["url"] = url
            return conn
        if kind == "invalid":
            _last["error"] = "%s (%s)" % (detail, url) if len(urls(cfg)) > 1 else detail
            return None
        errors.append("%s: %s" % (url, detail) if len(urls(cfg)) > 1 else detail)
        log.error("LDAP-Fehler (%s): %s", url, detail)
    _last["error"] = " | ".join(errors) or "keine LDAP-URL konfiguriert"
    return None


def _is_member(cfg: dict, conn, user_dn: str, member_of: list, group_dn: str) -> bool:
    from ldap3.utils.conv import escape_filter_chars as esc
    if not group_dn:
        return False
    if group_dn.lower() in [m.lower() for m in member_of]:
        return True
    if cfg.get("nested_groups"):
        flt = "(&(distinguishedName=%s)(memberOf:%s:=%s))" % (esc(user_dn), NESTED_RULE, esc(group_dn))
        conn.search(cfg["base_dn"], flt, attributes=["distinguishedName"], size_limit=1)
        return bool(conn.entries)
    return False


def _step(trace: Optional[list], name: str, ok: bool, detail: str = "") -> None:
    if trace is not None:
        trace.append({"step": name, "ok": ok, "detail": detail})


def _auth(cfg: dict, username: str, password: str, trace: Optional[list]) -> Optional[dict]:
    from ldap3.utils.conv import escape_filter_chars as esc
    username = (username or "").strip()
    if not (cfg["url"] and (cfg["domain"] or cfg["bind_dn"])):
        _step(trace, "Konfiguration", False, "LDAP-URL und (Domain oder Bind-DN) müssen gesetzt sein")
        return None
    if not password or not _USER_RE.match(username):
        _step(trace, "Eingabe", False, "Benutzername/Passwort fehlen oder enthalten unzulässige Zeichen")
        return None
    attrs = ["sAMAccountName", "displayName", "memberOf", "distinguishedName", "userPrincipalName", "mail"]
    sam = username.split("@")[0]
    flt = cfg["user_filter"].replace("{username}", esc(sam))
    multi = len(urls(cfg)) > 1
    if cfg["bind_dn"]:                                                   # Modus A: suchen, dann als Benutzer binden
        conn = _open(cfg, cfg["bind_dn"], cfg["bind_password"])
        if not conn:
            log.error("LDAP: Bind des Service-Accounts fehlgeschlagen")
            _step(trace, "Service-Account-Bind", False, _last["error"])
            return None
        _step(trace, "Service-Account-Bind", True, cfg["bind_dn"] + (" @ " + _last["url"] if multi and _last["url"] else ""))
        conn.search(cfg["base_dn"], flt, attributes=attrs, size_limit=2)
        if len(conn.entries) != 1:
            conn.unbind()
            _step(trace, "Benutzer suchen", False, "%d Treffer für %s (erwartet: 1)" % (len(conn.entries), flt))
            return None
        _step(trace, "Benutzer suchen", True, conn.entries[0].entry_dn)
        user_conn = _open(cfg, conn.entries[0].entry_dn, password)
        if not user_conn:
            conn.unbind()
            _step(trace, "Passwort prüfen", False, _last["error"])
            return None
        user_conn.unbind()
        _step(trace, "Passwort prüfen", True)
    else:                                                                # Modus B: UPN-Bind
        upn = username if "@" in username else "%s@%s" % (username, cfg["domain"])
        conn = _open(cfg, upn, password)
        if not conn:
            _step(trace, "Bind als %s" % upn, False, _last["error"])
            return None
        _step(trace, "Bind als %s" % upn, True, "Server: " + _last["url"] if multi and _last["url"] else "")
        conn.search(cfg["base_dn"], flt, attributes=attrs, size_limit=2)
        if len(conn.entries) != 1:
            conn.unbind()
            _step(trace, "Benutzer suchen", False, "%d Treffer für %s (erwartet: 1)" % (len(conn.entries), flt))
            return None
        _step(trace, "Benutzer suchen", True, conn.entries[0].entry_dn)
    try:
        entry = conn.entries[0]
        g = lambda a: (entry[a].value if a in entry.entry_attributes else None)  # noqa: E731
        member_of = g("memberOf") or []
        member_of = [member_of] if isinstance(member_of, str) else list(member_of)
        if trace is not None:                                            # Hilfe beim Eintragen der Gruppen-DNs (nur im Verbindungstest)
            _step(trace, "Gruppen des Benutzers", True,
                  "%d direkte Gruppen%s" % (len(member_of), (": " + " | ".join(sorted(member_of)[:25])) if member_of else ""))
        dn = entry.entry_dn
        if cfg["required_group"]:
            ok = _is_member(cfg, conn, dn, member_of, cfg["required_group"])
            _step(trace, "Pflichtgruppe", ok, cfg["required_group"])
            if not ok:
                log.warning("LDAP: %s ist nicht Mitglied der erforderlichen Gruppe", username)
                return None
        roles = [r for r in ROLES if cfg["group_roles"].get(r) and _is_member(cfg, conn, dn, member_of, cfg["group_roles"][r])]
        if any(cfg["group_roles"].get(r) for r in ROLES):
            _step(trace, "Rollen aus Gruppen", True, ", ".join(roles) or "keine passende Gruppe")
        scopes = []
        for x in cfg.get("scoped_groups") or []:
            if _is_member(cfg, conn, dn, member_of, x["group"]) and (x["role"], x["site_id"]) not in scopes:
                scopes.append((x["role"], x["site_id"]))
        if cfg.get("scoped_groups"):
            _step(trace, "Standort-Rechte aus Gruppen", True,
                  ", ".join("%s@%s" % (r, (db.row("SELECT code FROM sites WHERE id = ?", (sid,)) or {"code": sid})["code"]) for r, sid in scopes)
                  or "keine passende Gruppe")
        account = str(g("sAMAccountName") or sam)
        has_manual = bool(db.row("SELECT 1 AS x FROM user_scopes us JOIN users u ON u.id = us.user_id "
                                 "WHERE u.username = ? AND us.source = 'manual' LIMIT 1", (account,)))
        if not roles and not scopes and not has_manual:
            if cfg["default_role"]:
                roles = [cfg["default_role"]]
                _step(trace, "Standardrolle", True, cfg["default_role"])
            else:
                _step(trace, "Rolle", False, "keine passende Gruppe und keine Standardrolle – Anmeldung nicht erlaubt")
                return None
        return {"username": account, "display": str(g("displayName") or ""),
                "email": str(g("mail") or ""), "roles": roles, "scopes": scopes}
    finally:
        conn.unbind()


def mapping_active(cfg: dict) -> bool:
    """Sind AD-Gruppen Rollen zugeordnet? Nur dann bestimmt das Verzeichnis die Rollen bei jeder Anmeldung."""
    return bool(any((cfg.get("group_roles") or {}).values()) or cfg.get("scoped_groups"))


def authenticate(username: str, password: str, cfg: Optional[dict] = None) -> Optional[dict]:
    """``{"username", "display", "email", "roles"}`` bei Erfolg, sonst ``None`` (falsch/nicht berechtigt/Fehler)."""
    return _auth(cfg or settings(), username, password, None)


def diagnose(cfg: dict, username: str = "", password: str = "") -> dict:
    """Verbindungstest für die Verwaltung: Schritt-für-Schritt-Protokoll. Ohne Benutzer nur Service-Account-Bind."""
    trace: list = []
    if username and password:
        info = _auth(cfg, username, password, trace)
        return {"ok": info is not None, "steps": trace, "user": info}
    if not (cfg["url"] and (cfg["domain"] or cfg["bind_dn"])):
        _step(trace, "Konfiguration", False, "LDAP-URL und (Domain oder Bind-DN) müssen gesetzt sein")
    elif cfg["bind_dn"]:
        conn = _open(cfg, cfg["bind_dn"], cfg["bind_password"])
        _step(trace, "Service-Account-Bind", conn is not None, cfg["bind_dn"] if conn else _last["error"])
        if conn:
            conn.unbind()
    else:
        _step(trace, "Konfiguration", True, "UPN-Bind: zum Testen Benutzername und Passwort eingeben")
    return {"ok": bool(trace) and all(s["ok"] for s in trace), "steps": trace, "user": None}
