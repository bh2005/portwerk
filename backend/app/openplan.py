"""Anbindung an OpenPlan (Projektplanung): Aufgaben je Patchauftrag anlegen/verknüpfen, Status und Fortschritt abgleichen.

Portwerk spricht die REST-API von OpenPlan mit einem API-Token (Dienstkonto ``op_…``, Rolle Bearbeiter, Mitglied im Projekt):
* ``GET /api/projects``, ``GET /api/projects/{pid}`` – Projekte und Vorgänge finden,
* ``POST /api/projects/{pid}/tasks`` – Vorgang für einen Patchauftrag anlegen,
* ``POST /api/tasks/{tid}/events`` – Status/Fortschritt/Notiz und die externe Referenz ``portwerk`` (PA-Nummer mit Link) setzen,
* ``POST /api/projects/wizard`` – Projekt aus der Vorlage „Einbau Patchfelder / Verkabelung“ anlegen.
Rückrichtung (optional): OpenPlan-Webhook ``task.status`` -> ``POST /api/integrations/openplan/webhook`` (Signatur HMAC-SHA256).
Standardmäßig aus; die Einstellungen pflegt die Verwaltung (Schlüssel ``openplan`` in ``app_settings``).
"""
from __future__ import annotations

import json
import logging
import re
import ssl
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Optional

from fastapi import HTTPException

from . import audit, db, mailer

log = logging.getLogger("opp.openplan")
SETTING_KEY = "openplan"
SYSTEM = "portwerk"                    # Name der externen Referenz in OpenPlan
SYNC_IN_BACKGROUND = True                       # Tests schalten das ab (synchroner Abgleich)

DEFAULTS = {"enabled": False, "base_url": "", "token": "", "default_project_id": "", "ca_pem": "", "verify_tls": True,
            "auto_sync": True, "own_url": "", "webhook_secret": "", "account": "", "link_url": ""}
URL_KEYS = ("base_url", "own_url", "link_url")


class OpenPlanError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


# ── Einstellungen ─────────────────────────────────────────────────────────────

def settings() -> dict:
    r = db.row("SELECT value FROM app_settings WHERE key = ?", (SETTING_KEY,))
    return {**DEFAULTS, **(json.loads(r["value"]) if r else {})}


def public() -> dict:
    s = settings()
    out = {k: v for k, v in s.items() if k not in ("token", "webhook_secret")}
    out["token_set"], out["webhook_secret_set"] = bool(s["token"]), bool(s["webhook_secret"])
    out["webhook_url"] = f"{own_url(s)}/api/integrations/openplan/webhook" if own_url(s) else ""
    return out


def link_base(cfg: Optional[dict] = None) -> str:
    """Adresse von OpenPlan für Links im Browser: eigene Einstellung, sonst die API-Adresse (die z. B. im Docker-Netz anders lauten kann)."""
    cfg = cfg or settings()
    return (cfg.get("link_url") or cfg.get("base_url") or "").rstrip("/")


def own_url(cfg: Optional[dict] = None) -> str:
    """Öffentliche Adresse dieser Anwendung (für Links in OpenPlan): eigene Einstellung, sonst die der E-Mail-Einstellungen."""
    cfg = cfg or settings()
    return (cfg.get("own_url") or mailer.settings().get("public_url") or "").rstrip("/")


def validate(v: dict) -> None:
    if v["base_url"] and not re.match(r"^https?://[^\s]+$", v["base_url"]):
        raise HTTPException(422, "OpenPlan-Adresse muss mit http:// oder https:// beginnen")
    if v["enabled"] and not (v["base_url"] and v["token"]):
        raise HTTPException(422, "OpenPlan-Adresse und API-Token angeben")
    if v["token"] and not v["token"].startswith("op_"):
        raise HTTPException(422, "Das API-Token beginnt mit „op_“ (OpenPlan → Verwaltung → API-Zugänge)")
    if v["default_project_id"] and not str(v["default_project_id"]).isdigit():
        raise HTTPException(422, "Standard-Projekt: numerische Projekt-ID")
    if v["own_url"] and not re.match(r"^https?://[^\s]+$", v["own_url"]):
        raise HTTPException(422, "Eigene Adresse muss mit http:// oder https:// beginnen")
    if v.get("link_url") and not re.match(r"^https?://[^\s]+$", v["link_url"]):
        raise HTTPException(422, "OpenPlan-Adresse für Links muss mit http:// oder https:// beginnen")
    pem = (v.get("ca_pem") or "").strip()
    if pem and not (pem.startswith("-----BEGIN CERTIFICATE-----") and pem.endswith("-----END CERTIFICATE-----")):
        raise HTTPException(422, "CA-Zertifikat muss im PEM-Format vorliegen")


def save(patch: dict) -> dict:
    cur = settings()
    for k, val in patch.items():
        if val is None or k not in DEFAULTS:
            continue
        if k in ("token", "webhook_secret") and val == "":
            continue
        cur[k] = val.strip().rstrip("/") if isinstance(val, str) and k in URL_KEYS else (val.strip() if isinstance(val, str) and k != "ca_pem" else val)
    if patch.get("clear_token"):
        cur["token"] = ""
    if patch.get("clear_webhook_secret"):
        cur["webhook_secret"] = ""
    validate(cur)
    db.put_settings({SETTING_KEY: json.dumps(cur)})
    return public()


def require_enabled() -> dict:
    cfg = settings()
    if not cfg["enabled"]:
        raise HTTPException(409, "Die OpenPlan-Anbindung ist nicht eingerichtet (Verwaltung → OpenPlan)")
    return cfg


# ── HTTP ──────────────────────────────────────────────────────────────────────

def _context(cfg: dict) -> Optional[ssl.SSLContext]:
    if not cfg["base_url"].lower().startswith("https"):
        return None
    if not cfg.get("verify_tls", True):
        ctx = ssl.create_default_context()
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
        return ctx
    return ssl.create_default_context(cadata=(cfg.get("ca_pem") or "").strip() or None)


def request(method: str, path: str, body: Any = None, cfg: Optional[dict] = None) -> Any:
    """Aufruf der OpenPlan-API (JSON). Wirft ``OpenPlanError``; in Tests per monkeypatch ersetzbar."""
    cfg = cfg or settings()
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(cfg["base_url"].rstrip("/") + path, data=data, method=method,
                                 headers={"Authorization": "Bearer " + cfg["token"], "Content-Type": "application/json", "Accept": "application/json",
                                          "User-Agent": "portwerk"})
    try:
        with urllib.request.urlopen(req, timeout=10, context=_context(cfg)) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        msg = ""
        try:
            d = json.loads(e.read())
            msg = d.get("detail") if isinstance(d, dict) else ""
            if isinstance(msg, list):
                msg = "; ".join(str(x.get("msg", x)) for x in msg)
        except (ValueError, OSError):
            pass
        hint = {401: "Token ungültig oder abgelaufen", 403: "keine Berechtigung (Dienstkonto im Projekt als Bearbeiter eintragen)", 404: "nicht gefunden (Projekt/Vorgang vorhanden und für das Dienstkonto sichtbar?)"}.get(e.code, "")
        raise OpenPlanError(e.code, f"OpenPlan antwortet {e.code}" + (f": {msg}" if msg else "") + (f" – {hint}" if hint and not msg else ""))
    except (urllib.error.URLError, OSError, ssl.SSLError) as e:
        raise OpenPlanError(0, f"OpenPlan nicht erreichbar: {getattr(e, 'reason', e)}")
    except ValueError:
        raise OpenPlanError(0, "OpenPlan hat keine gültige JSON-Antwort geliefert")


def call(method: str, path: str, body: Any = None, cfg: Optional[dict] = None) -> Any:
    """Wie ``request``, aber Fehler als HTTP 502 (für die Routen)."""
    try:
        return request(method, path, body, cfg)
    except OpenPlanError as e:
        raise HTTPException(502 if e.status != 409 else 409, e.message)


# ── Verknüpfung und Abgleich ──────────────────────────────────────────────────

def order_link(cfg: dict, wid: int) -> str:
    base = own_url(cfg)
    return f"{base}/workorders/{wid}" if base else ""


def task_url(cfg: dict, pid, tid) -> str:
    return f"{link_base(cfg)}/project/{pid}?task={tid}" if link_base(cfg) else ""


def is_linked(w: dict) -> bool:
    return bool(w.get("openplan_project") and w.get("openplan_task"))


def status_payload(w: dict, progress: dict, link: str) -> dict:
    """Patchauftrag -> Rückmeldung an die OpenPlan-Aufgabe. In OpenPlan hat der Status Vorrang vor dem Fortschritt: Fortschritt > 0 setzt
    „in Arbeit“ selbst, daher wird entweder der Fortschritt oder ein Status gesendet."""
    from .routers.workorders import STATUS_LABELS
    st, total, done = w["status"], progress["total"], progress["done"]
    note = f"{w['number']}: {STATUS_LABELS.get(st, st)}" + (f" – {done} von {total} Positionen erledigt" if total else "")
    body: dict = {}
    if st == "confirmed":
        body["status"] = "done"
    elif st == "rejected":
        body["status"], note = "blocked", f"{w['number']} wurde abgelehnt"
    elif st in ("draft", "submitted", "approved"):
        body["status"] = "open"
    else:                                                               # in_progress, done (ausgeführt), rework
        pct = min(99, int(100 * done / total)) if total else 0         # erst die Bestätigung macht die Aufgabe „erledigt“
        body.update({"percent": pct} if pct > 0 else {"status": "in_progress"})
    body.update({"note": note[:300], "system": SYSTEM, "ref": w["number"], "url": link})
    return body


def _store_remote(wid: int, remote: Optional[dict], error: str = "") -> None:
    if remote:
        db.execute("UPDATE workorders SET openplan_status = ?, openplan_percent = ?, openplan_synced_at = ?, openplan_error = '' WHERE id = ?",
                   (remote.get("status", ""), remote.get("percent"), time.time(), wid))
    else:
        db.execute("UPDATE workorders SET openplan_error = ?, openplan_synced_at = ? WHERE id = ?", (error[:300], time.time(), wid))


def sync_workorder(wid: int, actor: str = "system") -> dict:
    """Status/Fortschritt eines verknüpften Patchauftrags an OpenPlan melden. Fehler stehen am Auftrag (``openplan_error``), werfen aber nie."""
    from .routers import workorders
    w = db.row("SELECT * FROM workorders WHERE id = ?", (wid,))
    cfg = settings()
    if not w or not cfg["enabled"] or not is_linked(w):
        return {"synced": False, "reason": "nicht verknüpft oder Anbindung aus"}
    try:
        res = request("POST", f"/api/tasks/{w['openplan_task']}/events", status_payload(w, workorders._progress(wid), order_link(cfg, wid)), cfg)
        _store_remote(wid, res.get("task"))
        return {"synced": True, "changed": bool(res.get("changed")), "task": res.get("task")}
    except OpenPlanError as e:
        _store_remote(wid, None, e.message)
        audit.log(actor, "openplan.sync_failed", "workorder", wid, e.message)
        return {"synced": False, "error": e.message}


def schedule_sync(wid: int, actor: str = "system") -> None:
    """Nach einer Änderung am Auftrag: Abgleich anstoßen (Hintergrund, blockiert die Anfrage nicht)."""
    w = db.row("SELECT openplan_project, openplan_task FROM workorders WHERE id = ?", (wid,))
    cfg = settings()
    if not (w and cfg["enabled"] and cfg["auto_sync"] and is_linked(w)):
        return
    if SYNC_IN_BACKGROUND:
        threading.Thread(target=lambda: sync_workorder(wid, actor), daemon=True, name=f"openplan-sync-{wid}").start()
    else:
        sync_workorder(wid, actor)


def create_task_for(cfg: dict, w: dict, project_id: int, parent_id: Optional[int], name: str = "") -> dict:
    """Vorgang für einen Patchauftrag in OpenPlan anlegen und mit dem Auftrag verknüpfen. Liefert {task_id, url}."""
    from .routers import workorders
    n = workorders._progress(w["id"])["total"]
    link = order_link(cfg, w["id"])
    body = {"name": (name.strip() or f"{w['number']} {w['title']}")[:300], "parent_id": parent_id, "duration": _duration(w),
            "notes": f"Patchauftrag {w['number']} in Portwerk ({n} Positionen)" + (f"\n{link}" if link else "")}
    if w.get("planned_from"):
        body.update({"constraint_type": "SNET", "constraint_date": w["planned_from"]})
    proj = call("POST", f"/api/projects/{project_id}/tasks", body, cfg)
    cands = [t for t in proj.get("tasks", []) if t.get("name") == body["name"] and t.get("parent_id") == parent_id]
    if not cands:
        raise HTTPException(502, "OpenPlan hat den Vorgang angelegt, aber nicht zurückgemeldet – bitte in OpenPlan prüfen")
    tid = max(t["id"] for t in cands)
    link_task(cfg, w, project_id, tid)
    return {"task_id": tid, "url": task_url(cfg, project_id, tid)}


def link_task(cfg: dict, w: dict, project_id: int, task_id: int) -> None:
    db.execute("UPDATE workorders SET openplan_project = ?, openplan_task = ?, openplan_link = ?, openplan_error = '', updated_at = ? WHERE id = ?",
               (str(project_id), str(task_id), task_url(cfg, project_id, task_id), time.time(), w["id"]))
    r = sync_workorder(w["id"])                                         # setzt Referenz, Status, Fortschritt
    if not r.get("synced"):
        raise HTTPException(502, r.get("error", "Abgleich mit OpenPlan fehlgeschlagen"))


def _duration(w: dict) -> int:
    """Arbeitstage zwischen geplantem Beginn und Ende (mindestens 1); ohne Termine 1."""
    import datetime as dt
    try:
        a, b = dt.date.fromisoformat(w["planned_from"]), dt.date.fromisoformat(w["planned_to"])
    except (TypeError, ValueError):
        return 1
    n, d = 0, a
    while d <= b:
        n += d.weekday() < 5
        d += dt.timedelta(days=1)
    return max(1, n)
