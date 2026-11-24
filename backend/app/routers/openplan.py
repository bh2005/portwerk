"""OpenPlan-Anbindung: Einstellungen (Verwaltung), Projekte/Vorgänge suchen, Patchaufträge verknüpfen/abgleichen, Projekt aus Vorlage, Webhook-Empfang."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import audit, db, openplan
from ..auth import Principal, current_principal, require_admin
from ..schemas import OpenPlanBulkIn, OpenPlanCreateIn, OpenPlanLinkIn, OpenPlanProjectIn, OpenPlanSettingsIn
from . import workorders

router = APIRouter(tags=["openplan"])

PLAN_ROLES = ["planer", "freigeber", "admin"]


def _planner(me: Principal) -> None:
    if not (me.kind == "user" and me.any_role(*PLAN_ROLES)):
        raise HTTPException(403, "Fehlende Rolle (erforderlich: planer oder freigeber)")


# ── Verwaltung ────────────────────────────────────────────────────────────────

@router.get("/api/admin/openplan")
def get_settings(_: Principal = Depends(require_admin)):
    return openplan.public()


@router.put("/api/admin/openplan")
def put_settings(body: OpenPlanSettingsIn, me: Principal = Depends(require_admin)):
    was = openplan.settings().get("sync_absences")
    out = openplan.save(body.model_dump(exclude_unset=True))
    if was and not out["sync_absences"]:
        n = openplan.clear_absences()                                              # ausgeschaltet: übernommene Einträge wieder entfernen
        audit.log(me.name, "openplan.absences_cleared", "settings", "openplan", f"{n} übernommene Abwesenheit(en) entfernt")
        out = openplan.public()
    audit.log(me.name, "settings.openplan.save", "settings", "openplan", f"aktiv={out['enabled']}, {out['base_url']}, Standard-Projekt {out['default_project_id'] or '-'}, Webhook={'ja' if out['webhook_secret_set'] else 'nein'}")
    return out


@router.post("/api/admin/openplan/test")
def test_connection(me: Principal = Depends(require_admin)):
    """Prüft Adresse, Token und Sichtbarkeit: meldet das Dienstkonto und die Projekte, die es sehen darf."""
    cfg = openplan.settings()
    if not (cfg["base_url"] and cfg["token"]):
        raise HTTPException(409, "Zuerst OpenPlan-Adresse und API-Token speichern")
    who = openplan.call("GET", "/api/auth/me", None, cfg)
    projects = openplan.call("GET", "/api/projects", None, cfg)
    db.put_settings({openplan.SETTING_KEY: json.dumps({**cfg, "account": who.get("username", "")})})          # für die Schleifenerkennung beim Webhook
    audit.log(me.name, "openplan.test", "settings", "openplan", f"Konto {who.get('username')}, {len(projects)} Projekte")
    return {"ok": True, "account": who.get("username", ""), "role": who.get("role", ""), "projects": [{"id": p["id"], "name": p["name"], "access": p.get("access", "")} for p in projects[:100]],
            "webhook_url": openplan.public()["webhook_url"]}


@router.post("/api/admin/openplan/absences/sync")
def sync_absences(me: Principal = Depends(require_admin)):
    """Abwesenheiten jetzt aus OpenPlan übernehmen (sonst stündlich, wenn eingeschaltet)."""
    openplan.require_enabled()
    st = openplan.sync_absences(me.name, force=True)
    if not st.get("ok"):
        raise HTTPException(502, st.get("error") or "Abgleich fehlgeschlagen")
    return st


# ── Auswahl ───────────────────────────────────────────────────────────────────

@router.get("/api/openplan/status")
def status(_: Principal = Depends(current_principal)):
    """Für die Oberfläche: ist die Anbindung eingerichtet und aktiv?"""
    c = openplan.settings()
    return {"enabled": bool(c["enabled"]), "default_project_id": c["default_project_id"], "base_url": openplan.link_base(c) if c["enabled"] else ""}


@router.get("/api/openplan/projects")
def projects(me: Principal = Depends(current_principal)):
    _planner(me)
    cfg = openplan.require_enabled()
    return [{"id": p["id"], "name": p["name"], "task_count": p.get("task_count"), "access": p.get("access", "")} for p in openplan.call("GET", "/api/projects", None, cfg)]


@router.get("/api/openplan/projects/{pid}/tasks")
def project_tasks(pid: int, q: str = "", me: Principal = Depends(current_principal)):
    """Vorgänge eines OpenPlan-Projekts (zum Verknüpfen bzw. als Ziel für neue Vorgänge); Abschnitte „Portwerk“ sind vorgeschlagen."""
    _planner(me)
    cfg = openplan.require_enabled()
    proj = openplan.call("GET", f"/api/projects/{pid}", None, cfg)
    out = []
    for t in proj.get("tasks", []):
        if q.strip() and q.strip().lower() not in t["name"].lower() and q.strip().lower() not in str(t.get("wbs", "")).lower():
            continue
        out.append({"id": t["id"], "name": t["name"], "wbs": t.get("wbs", ""), "parent_id": t.get("parent_id"), "summary": bool(t.get("summary")),
                    "status": t.get("status"), "percent": t.get("percent"), "suggested": bool(t.get("summary")) and "portwerk" in t["name"].lower(),
                    "refs": {k: v.get("ref") if isinstance(v, dict) else v for k, v in (t.get("refs") or {}).items()}})
    return {"project": {"id": proj["project"]["id"], "name": proj["project"]["name"]}, "tasks": out[:400], "truncated": len(out) > 400}


# ── Auftrag ↔ Aufgabe ─────────────────────────────────────────────────────────

def _order(wid: int, me: Principal) -> dict:
    w = workorders._wo_or_404(wid, me)
    workorders._require_role(me, PLAN_ROLES, w)
    return w


def _out(wid: int) -> dict:
    return workorders._wo_out(db.row("SELECT * FROM workorders WHERE id = ?", (wid,)), with_items=True)


@router.post("/api/workorders/{wid}/openplan/link")
def link_existing(wid: int, body: OpenPlanLinkIn, me: Principal = Depends(current_principal)):
    """Verknüpft den Patchauftrag mit einer vorhandenen OpenPlan-Aufgabe (Teilvorgang) und gleicht Status/Fortschritt ab."""
    w = _order(wid, me)
    cfg = openplan.require_enabled()
    proj = openplan.call("GET", f"/api/projects/{body.project_id}", None, cfg)
    t = next((x for x in proj.get("tasks", []) if x["id"] == body.task_id), None)
    if not t:
        raise HTTPException(404, "Vorgang im OpenPlan-Projekt nicht gefunden")
    if t.get("summary"):
        raise HTTPException(400, "Das ist ein Sammelvorgang – bitte einen Teilvorgang wählen")
    clash = db.row("SELECT number FROM workorders WHERE openplan_project = ? AND openplan_task = ? AND id <> ?", (str(body.project_id), str(body.task_id), wid))
    if clash:
        raise HTTPException(409, f"Diese Aufgabe ist schon mit {clash['number']} verknüpft")
    openplan.link_task(cfg, w, body.project_id, body.task_id)
    audit.log(me.name, "openplan.link", "workorder", wid, f"{w['number']} -> Projekt {body.project_id}, Vorgang {body.task_id}")
    return _out(wid)


@router.post("/api/workorders/{wid}/openplan/create")
def create_in_openplan(wid: int, body: OpenPlanCreateIn, me: Principal = Depends(current_principal)):
    """Legt für den Patchauftrag einen Vorgang in OpenPlan an (optional unter einem Abschnitt) und verknüpft beide."""
    w = _order(wid, me)
    cfg = openplan.require_enabled()
    if openplan.is_linked(w):
        raise HTTPException(409, "Der Auftrag ist bereits mit OpenPlan verknüpft")
    res = openplan.create_task_for(cfg, w, body.project_id, body.parent_id, body.name)
    audit.log(me.name, "openplan.create_task", "workorder", wid, f"{w['number']} -> Projekt {body.project_id}, Vorgang {res['task_id']}")
    return _out(wid)


@router.post("/api/workorders/{wid}/openplan/sync")
def sync_now(wid: int, me: Principal = Depends(current_principal)):
    w = _order(wid, me)
    openplan.require_enabled()
    if not openplan.is_linked(w):
        raise HTTPException(409, "Der Auftrag ist nicht mit OpenPlan verknüpft")
    res = openplan.sync_workorder(wid, me.name)
    out = _out(wid)
    out["sync"] = res
    return out


@router.delete("/api/workorders/{wid}/openplan")
def unlink(wid: int, me: Principal = Depends(current_principal)):
    """Hebt die Verknüpfung auf (die OpenPlan-Aufgabe bleibt bestehen; die Referenz wird dort nach Möglichkeit entfernt)."""
    w = _order(wid, me)
    cfg = openplan.settings()
    if openplan.is_linked(w) and cfg["enabled"]:
        try:
            openplan.request("DELETE", f"/api/tasks/{w['openplan_task']}/refs/{openplan.SYSTEM}", None, cfg)
        except openplan.OpenPlanError:
            pass                                                                    # Referenz bleibt dort stehen – unkritisch
    db.execute("""UPDATE workorders SET openplan_project = '', openplan_task = '', openplan_link = '', openplan_status = '', openplan_percent = NULL,
                  openplan_synced_at = NULL, openplan_error = '', updated_at = ? WHERE id = ?""", (time.time(), wid))
    audit.log(me.name, "openplan.unlink", "workorder", wid, w["number"])
    return _out(wid)


# ── Mehrere Aufträge / Projekt aus Vorlage ────────────────────────────────────

def _bulk_create(cfg: dict, me: Principal, project_id: int, parent_id: Optional[int], ids: list[int]) -> dict:
    created, skipped, errors = [], [], []
    for wid in sorted(set(ids)):
        try:
            w = _order(wid, me)
        except HTTPException as e:
            errors.append({"id": wid, "message": str(e.detail)}); continue
        if openplan.is_linked(w):
            skipped.append(w["number"]); continue
        try:
            r = openplan.create_task_for(cfg, w, project_id, parent_id)
            created.append({"number": w["number"], "task_id": r["task_id"], "url": r["url"]})
            audit.log(me.name, "openplan.create_task", "workorder", wid, f"{w['number']} -> Projekt {project_id}, Vorgang {r['task_id']}")
        except HTTPException as e:
            errors.append({"id": wid, "number": w["number"], "message": str(e.detail)})
    return {"created": created, "skipped_linked": skipped, "errors": errors}


@router.post("/api/openplan/orders")
def create_for_orders(body: OpenPlanBulkIn, me: Principal = Depends(current_principal)):
    """Legt für mehrere Patchaufträge je einen Vorgang in OpenPlan an (z. B. unter „Patchaufträge (aus Portwerk)“)."""
    _planner(me)
    cfg = openplan.require_enabled()
    return _bulk_create(cfg, me, body.project_id, body.parent_id, body.workorder_ids)


@router.post("/api/openplan/projects", status_code=201)
def create_project(body: OpenPlanProjectIn, me: Principal = Depends(current_principal)):
    """Legt in OpenPlan ein Projekt aus der Vorlage „Einbau Patchfelder / Verkabelung“ an und hängt auf Wunsch die gewählten Patchaufträge
    als Vorgänge unter den Abschnitt „Patchaufträge (aus Portwerk)“. Das Projekt gehört dem Dienstkonto; weitere Beteiligte
    gibst du als OpenPlan-Benutzernamen an (Bearbeiter)."""
    _planner(me)
    cfg = openplan.require_enabled()
    if body.kind not in ("patchpanel", "network", "migration", "release", "empty"):
        raise HTTPException(400, "Unbekannte Projektart")
    for wid in body.workorder_ids:
        _order(wid, me)                                                              # Rechte vorab prüfen, bevor etwas angelegt wird
    members, unknown = [], []
    for name in dict.fromkeys(n.strip() for n in body.members if n.strip()):
        hits = openplan.call("GET", f"/api/users/directory?q={name}&limit=10", None, cfg)
        hit = next((u for u in hits if u["username"].lower() == name.lower()), None)
        (members if hit else unknown).append({"user_id": hit["id"], "role": "editor"} if hit else name)
    if unknown:
        raise HTTPException(400, "OpenPlan-Benutzer nicht gefunden: " + ", ".join(unknown))
    me_id = (openplan.call("GET", "/api/auth/me", None, cfg) or {}).get("id")                   # das Dienstkonto ist schon Verantwortlicher
    proj = openplan.call("POST", "/api/projects/wizard", {"kind": body.kind, "name": body.name.strip(), "description": body.description, "start_date": body.start_date,
                                                          "members": [m for m in members if m["user_id"] != me_id]}, cfg)
    pid = proj["project"]["id"]
    out = {"project_id": pid, "name": proj["project"]["name"], "url": f"{openplan.link_base(cfg)}/project/{pid}", "tasks": len(proj.get("tasks", [])),
           "created": [], "skipped_linked": [], "errors": []}
    if body.workorder_ids:
        tasks = proj.get("tasks", [])                                                 # Abschnitt „Patchaufträge (aus Portwerk)“: bevorzugt Sammelvorgang
        parent = next((t["id"] for t in tasks if t.get("summary") and "portwerk" in t["name"].lower()),
                      next((t["id"] for t in tasks if "portwerk" in t["name"].lower() and not t.get("parent_id")), None))
        out.update(_bulk_create(cfg, me, pid, parent, body.workorder_ids))
    audit.log(me.name, "openplan.create_project", "settings", "openplan", f"{body.name} ({body.kind}) -> Projekt {pid}, {len(out['created'])} Aufträge")
    return out


# ── Webhook von OpenPlan ──────────────────────────────────────────────────────

@router.post("/api/integrations/openplan/webhook", include_in_schema=False)
async def webhook(request: Request):
    """Empfängt OpenPlan-Ereignisse (``task.status``/``task.blocked``) und merkt sich den Status der verknüpften Aufgabe am Patchauftrag.
    Die Signatur (HMAC-SHA256 über den rohen Body mit dem Webhook-Geheimnis) und die Aktualität (±5 min) werden geprüft."""
    raw = await request.body()
    cfg = openplan.settings()
    secret = cfg["webhook_secret"]
    if not (cfg["enabled"] and secret):
        raise HTTPException(404, "nicht eingerichtet")
    mac = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    try:
        fresh = abs(time.time() - int(request.headers.get("X-OpenPlan-Timestamp", "0"))) < 300
    except ValueError:
        fresh = False
    if not (fresh and hmac.compare_digest(mac, request.headers.get("X-OpenPlan-Signature", ""))):
        raise HTTPException(401, "Signatur ungültig")
    try:
        p = json.loads(raw)
    except ValueError:
        raise HTTPException(400, "kein JSON")
    event = p.get("event")
    if event == "ping":
        return {"ok": True, "pong": True}
    if event not in ("task.status", "task.blocked"):
        return {"ok": True, "ignored": "Ereignis unbekannt"}
    if cfg["account"] and p.get("actor") == cfg["account"]:
        return {"ok": True, "ignored": "eigene Änderung"}                            # Schleifen vermeiden
    t, pr = p.get("task") or {}, p.get("project") or {}
    rows = db.rows("SELECT id, number FROM workorders WHERE openplan_project = ? AND openplan_task = ?", (str(pr.get("id")), str(t.get("id"))))
    for w in rows:
        db.execute("UPDATE workorders SET openplan_status = ?, openplan_percent = ?, openplan_synced_at = ?, openplan_error = '' WHERE id = ?",
                   (t.get("status", ""), t.get("percent"), time.time(), w["id"]))
        audit.log("openplan", "openplan.webhook", "workorder", w["id"], f"{w['number']}: Aufgabe {t.get('status')} {t.get('percent')}% (von {p.get('actor')})")
    return {"ok": True, "updated": len(rows)}
