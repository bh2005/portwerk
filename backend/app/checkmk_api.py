"""Anbindung an die Checkmk-REST-API: prüfen, ob ein Gerät in Checkmk existiert, und es bei Bedarf dort anlegen.

Portwerk spricht ``<api_url>/check_mk/api/1.0`` mit einem Automation-User (``Authorization: Bearer <user> <secret>``).
Der User braucht Rechte zum Lesen und Anlegen von Hosts, aber keine zum Aktivieren: Portwerk legt Hosts nur als ausstehende Änderung an,
die Aktivierung geschieht in Checkmk (damit nie fremde, noch nicht fertige Änderungen mitaktiviert werden).
Neue Hosts bekommen nur den Host-Check (Ping): kein Agent, kein SNMP.
Standardmäßig aus; die Einstellungen pflegt die Verwaltung (Schlüssel ``checkmk_api`` in ``app_settings``).
"""
from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from fastapi import HTTPException

from . import db

SETTING_KEY = "checkmk_api"
DEFAULTS = {"enabled": False, "api_url": "", "user": "", "secret": "", "ca_pem": "", "verify_tls": True, "default_folder": "/"}
TIMEOUT = 15
_HOST = re.compile(r"^[A-Za-z0-9_.\-]{1,120}$")                 # Checkmk-Hostnamen: Buchstaben, Ziffern, _ . -


# ── Einstellungen ─────────────────────────────────────────────────────────────

def settings() -> dict:
    r = db.row("SELECT value FROM app_settings WHERE key = ?", (SETTING_KEY,))
    return {**DEFAULTS, **(json.loads(r["value"]) if r else {})}


def public() -> dict:
    s = settings()
    out = {k: v for k, v in s.items() if k != "secret"}
    out["secret_set"] = bool(s["secret"])
    return out


def save(body: dict) -> dict:
    cur = settings()
    new = {**cur}
    for k in ("enabled", "api_url", "user", "ca_pem", "verify_tls", "default_folder"):
        if k in body and body[k] is not None:
            new[k] = body[k]
    if body.get("secret"):                                      # leer = unverändert
        new["secret"] = body["secret"]
    new["api_url"] = str(new["api_url"]).strip().rstrip("/")
    if new["api_url"] and not re.match(r"^https?://[^\s/]+(/[^\s?#]*)?$", new["api_url"]):
        raise HTTPException(422, "Adresse im Format http(s)://host/site erwartet (ohne /check_mk/api)")
    new["default_folder"] = normalize_folder(new["default_folder"])
    db.put_settings({SETTING_KEY: json.dumps(new)})
    return public()


def normalize_folder(f: str) -> str:
    f = "/" + str(f or "").strip().strip("/")
    if not re.match(r"^/[A-Za-z0-9_\-/.]*$", f):
        raise HTTPException(422, "Ordner ungültig (Pfad wie /eu/de_germany)")
    return f


def configured(cfg: Optional[dict] = None) -> dict:
    cfg = cfg or settings()
    if not (cfg["enabled"] and cfg["api_url"] and cfg["user"] and cfg["secret"]):
        raise HTTPException(409, "Die Checkmk-Anbindung ist nicht eingerichtet (Verwaltung → Checkmk)")
    return cfg


# ── HTTP ──────────────────────────────────────────────────────────────────────

def _ctx(cfg: dict):
    if not cfg["api_url"].lower().startswith("https"):
        return None
    ctx = ssl.create_default_context()
    if cfg["ca_pem"].strip():
        ctx.load_verify_locations(cadata=cfg["ca_pem"])
    if not cfg["verify_tls"]:
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    return ctx


def request(cfg: dict, method: str, path: str, body: Optional[dict] = None) -> tuple:
    """(Status, JSON|None). Netzwerkfehler werden zu 502 mit lesbarer Meldung; HTTP-Fehler der API kommen als Status zurück."""
    url = f"{cfg['api_url']}/check_mk/api/1.0{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {cfg['user']} {cfg['secret']}", "Accept": "application/json", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=_ctx(cfg)) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"detail": raw[:200].decode("utf-8", "replace")}
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise HTTPException(502, f"Checkmk nicht erreichbar: {getattr(e, 'reason', e)}")


def _detail(js) -> str:
    if isinstance(js, dict):
        f = js.get("fields")
        return (js.get("detail") or js.get("title") or "") + (f" {json.dumps(f, ensure_ascii=False)[:300]}" if f else "")
    return ""


def _fail(status: int, js) -> HTTPException:
    if status in (401, 403):
        return HTTPException(502, f"Checkmk lehnt die Anmeldung/Berechtigung ab ({status}): {_detail(js)}")
    return HTTPException(502, f"Checkmk-Fehler {status}: {_detail(js)}")


# ── Funktionen ────────────────────────────────────────────────────────────────

def check_connection() -> dict:
    cfg = configured()
    st, js = request(cfg, "GET", "/version")
    if st != 200:
        raise _fail(st, js)
    st2, fl = request(cfg, "GET", "/domain-types/folder_config/collections/all?recursive=true&show_hosts=false")
    if st2 != 200:
        raise _fail(st2, fl)
    return {"version": (js or {}).get("versions", {}).get("checkmk", ""), "edition": (js or {}).get("edition", ""), "folders": len((fl or {}).get("value", []))}


def folders() -> list[dict]:
    cfg = configured()
    st, js = request(cfg, "GET", "/domain-types/folder_config/collections/all?recursive=true&show_hosts=false")
    if st != 200:
        raise _fail(st, js)
    out = []
    for f in (js or {}).get("value", []):
        fid = str(f.get("id") or "")
        path = "/" + fid.replace("~", "/").strip("/") if fid != "~" else "/"
        out.append({"path": path.replace("//", "/"), "title": f.get("title") or path})
    return sorted(out, key=lambda x: x["path"])


def host(name: str) -> dict:
    """Existiert der Host in Checkmk? (Antwort mit Ordner, IP und Link-Pfad, sonst ``exists: False``.)"""
    cfg = configured()
    n = str(name or "").strip()
    if not _HOST.match(n):
        raise HTTPException(422, "Hostname ungültig")
    st, js = request(cfg, "GET", f"/objects/host_config/{urllib.parse.quote(n)}")
    if st == 404:
        return {"exists": False, "host_name": n}
    if st != 200:
        raise _fail(st, js)
    ext = (js or {}).get("extensions", {})
    attrs = ext.get("attributes", {})
    return {"exists": True, "host_name": (js or {}).get("id", n), "folder": ext.get("folder", ""), "ipaddress": attrs.get("ipaddress", ""),
            "labels": attrs.get("labels", {})}


def create_host(name: str, ip: str = "", folder: str = "", labels: Optional[dict] = None, location_tag: str = "") -> dict:
    """Host nur mit Host-Check (Ping) anlegen: kein Agent, kein SNMP. Die Änderung bleibt ausstehend (Aktivierung in Checkmk)."""
    cfg = configured()
    n = str(name or "").strip()
    if not _HOST.match(n):
        raise HTTPException(422, "Hostname ungültig (erlaubt: Buchstaben, Ziffern, _ . -)")
    ip = str(ip or "").strip().split("/")[0]
    attrs: dict = {"tag_agent": "no-agent", "tag_snmp_ds": "no-snmp", "labels": {"source": "portwerk", **(labels or {})}}
    if ip:
        if not re.match(r"^[0-9a-fA-F:.]{3,45}$", ip):
            raise HTTPException(422, "IP-Adresse ungültig")
        attrs["ipaddress"] = ip
        attrs["tag_address_family"] = "ip-v6-only" if ":" in ip else "ip-v4-only"
    tag = str(location_tag or "").strip()
    if tag:                                                    # Tag-Gruppe ``location``; ob der Wert existiert, prüft Checkmk beim Anlegen
        if not re.match(r"^[A-Za-z0-9_\-]{1,40}$", tag):
            raise HTTPException(422, "Standort-Tag ungültig")
        attrs["tag_location"] = tag
    st, js = request(cfg, "POST", "/domain-types/host_config/collections/all?bake_agent=false",
                     {"host_name": n, "folder": normalize_folder(folder or cfg["default_folder"]), "attributes": attrs})
    if st == 400 and "already" in _detail(js).lower():
        raise HTTPException(409, "Der Host existiert in Checkmk bereits")
    if st == 400 and tag and "tag_location" in _detail(js):
        raise HTTPException(422, f"Das Standort-Tag „{tag}“ gibt es in Checkmk nicht")
    if st not in (200, 201):
        raise _fail(st, js)
    return {"host_name": n, "folder": normalize_folder(folder or cfg["default_folder"]), "ping_only": True, "pending_activation": True, "location_tag": tag}
