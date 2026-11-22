"""OpenPlan-Anbindung gegen eine simulierte OpenPlan-API (Verhalten nach docs/integration-api.md von OpenPlan)."""
import hashlib
import hmac
import json
import time

import pytest

from conftest import login


class FakeOpenPlan:
    """Minimale Nachbildung der benötigten OpenPlan-Endpunkte inkl. der Regel „Status hat Vorrang vor Fortschritt“."""

    def __init__(self):
        self.projects, self.tasks, self.refs, self.calls = {}, {}, {}, []
        self.users = [{"id": 10, "username": "anna", "display_name": "Anna"}, {"id": 11, "username": "bernd", "display_name": "Bernd"}, {"id": 99, "username": "svc-opp", "display_name": "OPP"}]
        self.fail = None                                  # z. B. OpenPlanError(0, "...") für alle Aufrufe
        self.seq = 100
        self.add_project(1, "Netz-Rollout", with_section=True)

    def add_project(self, pid, name, with_section=False):
        self.projects[pid] = name
        self.add_task(pid, "Planung", summary=True)
        if with_section:
            sec = self.add_task(pid, "Patchaufträge (aus Portwerk)", summary=True)
            self.add_task(pid, "Platzhalter", parent=sec)
        self.add_task(pid, "Einzelaufgabe")

    def add_task(self, pid, name, parent=None, summary=False):
        self.seq += 1
        self.tasks[self.seq] = {"id": self.seq, "project_id": pid, "name": name, "parent_id": parent, "summary": summary, "wbs": str(self.seq), "status": "open", "percent": 0.0, "note": "", "duration": 1}
        return self.seq

    def project_json(self, pid):
        ts = [{**t, "refs": {s: {"ref": r, "url": u} for (tid, s), (r, u) in self.refs.items() if tid == t["id"]}} for t in self.tasks.values() if t["project_id"] == pid]
        return {"project": {"id": pid, "name": self.projects[pid]}, "tasks": ts}

    def __call__(self, method, path, body=None, cfg=None):
        from app.openplan import OpenPlanError
        self.calls.append((method, path, body))
        if self.fail:
            raise self.fail
        if cfg and not cfg["token"].startswith("op_"):
            raise OpenPlanError(401, "OpenPlan antwortet 401")
        if (method, path) == ("GET", "/api/auth/me"):
            return {"id": 99, "username": "svc-opp", "role": "editor"}
        if (method, path) == ("GET", "/api/projects"):
            return [{"id": i, "name": n, "task_count": sum(1 for t in self.tasks.values() if t["project_id"] == i), "access": "edit"} for i, n in self.projects.items()]
        if path.startswith("/api/projects/") and method == "GET" and path.count("/") == 3:
            pid = int(path.split("/")[3])
            if pid not in self.projects:
                raise OpenPlanError(404, "OpenPlan antwortet 404")
            return self.project_json(pid)
        if method == "POST" and path.endswith("/tasks") and path.startswith("/api/projects/"):
            pid = int(path.split("/")[3])
            if pid not in self.projects:
                raise OpenPlanError(404, "OpenPlan antwortet 404")
            tid = self.add_task(pid, body["name"], body.get("parent_id"))
            self.tasks[tid]["duration"] = body.get("duration", 1)
            self.tasks[tid]["notes"] = body.get("notes", "")
            self.tasks[tid]["constraint"] = (body.get("constraint_type"), body.get("constraint_date"))
            return self.project_json(pid)
        if method == "POST" and path.startswith("/api/tasks/") and path.endswith("/events"):
            tid = int(path.split("/")[3])
            t = self.tasks.get(tid)
            if not t:
                raise OpenPlanError(404, "OpenPlan antwortet 404")
            before = (t["status"], t["percent"], t["note"], self.refs.get((tid, body.get("system"))))
            if body.get("status") is not None:
                t["status"] = body["status"]
                t["percent"] = 100.0 if body["status"] == "done" else (0.0 if body["status"] == "open" else t["percent"])
            elif body.get("percent") is not None:
                t["percent"] = body["percent"]
                t["status"] = "done" if t["percent"] >= 100 else ("in_progress" if t["percent"] > 0 and t["status"] in ("open", "done") else t["status"])
            if body.get("note") is not None:
                t["note"] = body["note"]
            if body.get("system"):
                self.refs[(tid, body["system"])] = (body["ref"], body.get("url", ""))
            after = (t["status"], t["percent"], t["note"], self.refs.get((tid, body.get("system"))))
            return {"changed": before != after, "task": {"id": tid, "status": t["status"], "percent": t["percent"], "status_note": t["note"]}}
        if method == "DELETE" and "/refs/" in path:
            tid, system = int(path.split("/")[3]), path.split("/")[5]
            return {"ok": True, "removed": self.refs.pop((tid, system), None) is not None}
        if (method, path) == ("POST", "/api/projects/wizard"):
            pid = max(self.projects) + 1
            self.add_project(pid, body["name"], with_section=body["kind"] == "patchpanel")
            self.wizard_body = body
            return self.project_json(pid)
        if method == "GET" and path.startswith("/api/users/directory"):
            q = path.split("q=")[1].split("&")[0].lower()
            return [u for u in self.users if q in u["username"]]
        raise AssertionError(f"unerwarteter Aufruf {method} {path}")


@pytest.fixture()
def op(monkeypatch):
    from app import openplan
    fake = FakeOpenPlan()
    monkeypatch.setattr(openplan, "request", fake)
    monkeypatch.setattr(openplan, "SYNC_IN_BACKGROUND", False)          # Abgleich synchron, damit Tests ihn sehen
    return fake


def enable(client, admin, **kw):
    r = client.put("/api/admin/openplan", headers=admin, json={"enabled": True, "base_url": "http://openplan.test:8083/", "token": "op_geheim", "own_url": "https://opp.example.test",
                                                              "webhook_secret": "whsec_test", **kw})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture()
def lab(client, admin):
    s = client.post("/api/sites", headers=admin, json={"code": "W1", "name": "Werk"}).json()["id"]
    s2 = client.post("/api/sites", headers=admin, json={"code": "W2", "name": "Fremd"}).json()["id"]
    rack = client.post("/api/locations", headers=admin, json={"site_id": s, "kind": "rack", "name": "R1", "rack_units": 12}).json()["id"]
    ports = []
    for h in ("sw-a", "sw-b"):
        d = client.post("/api/devices", headers=admin, json={"hostname": h, "location_id": rack}).json()
        ports.append([client.post(f"/api/devices/{d['id']}/ports", headers=admin, json={"name": f"P{i}"}).json()["id"] for i in range(1, 13)])
    used = [0]                                                     # jeder Auftrag eigene Ports (sonst Rückfrage „verplant“)

    def order(title, n=4, **kw):
        pairs = [{"port_a_id": ports[0][i], "port_b_id": ports[1][i], "cable_label": f"K{i}"} for i in range(used[0], used[0] + n)]
        used[0] += n
        wo = client.post("/api/wizards/bulk-cables", headers=admin, json={"pairs": pairs, "mode": "workorder", "workorder_title": title}).json()["workorder"]
        return wo
    return {"site": s, "site2": s2, "rack": rack, "ports": ports, "order": order}


def user(client, admin, name, scopes=(), roles=()):
    client.post("/api/users", headers=admin, json={"username": name, "password": "Passwort-123", "roles": list(roles), "scopes": [{"role": r, "site_id": s} for r, s in scopes]})
    return login(client, name, "Passwort-123")


# ── Einstellungen ─────────────────────────────────────────────────────────────

def test_settings_default_off_validation_secrets_and_admin_only(client, admin, op):
    s = client.get("/api/admin/openplan", headers=admin).json()
    assert s["enabled"] is False and s["base_url"] == "" and s["token_set"] is False and "token" not in s and "webhook_secret" not in s
    put = lambda **kw: client.put("/api/admin/openplan", headers=admin, json=kw)  # noqa: E731
    assert put(enabled=True).status_code == 422                                              # Adresse/Token fehlen
    assert put(base_url="openplan.test").status_code == 422
    assert put(base_url="http://x.test", token="falsch").status_code == 422                  # Token beginnt mit op_
    assert put(default_project_id="abc").status_code == 422
    assert put(ca_pem="kein pem").status_code == 422
    ok = enable(client, admin, default_project_id="1")
    assert ok["token_set"] and ok["webhook_secret_set"] and ok["base_url"] == "http://openplan.test:8083" and "geheim" not in str(ok) and "whsec" not in str(ok)
    assert ok["webhook_url"] == "https://opp.example.test/api/integrations/openplan/webhook"
    assert put(default_project_id="2").json()["token_set"] is True                          # leeres Token lässt es stehen
    assert put(clear_token=True).status_code == 422                                          # aktiv ohne Token geht nicht
    assert put(clear_token=True, enabled=False).json()["token_set"] is False
    h = user(client, admin, "pl", roles=("planer",))
    assert client.get("/api/admin/openplan", headers=h).status_code == 403 and client.post("/api/admin/openplan/test", headers=h).status_code == 403


def test_connection_test_reports_account_and_projects(client, admin, op):
    assert client.post("/api/admin/openplan/test", headers=admin).status_code == 409          # noch nichts gespeichert
    enable(client, admin)
    r = client.post("/api/admin/openplan/test", headers=admin).json()
    assert r["ok"] and r["account"] == "svc-opp" and r["role"] == "editor" and r["projects"][0]["name"] == "Netz-Rollout"
    from app import openplan
    assert openplan.settings()["account"] == "svc-opp"                                         # für die Schleifenerkennung
    from app.openplan import OpenPlanError
    op.fail = OpenPlanError(0, "OpenPlan nicht erreichbar: Connection refused")
    bad = client.post("/api/admin/openplan/test", headers=admin)
    assert bad.status_code == 502 and "nicht erreichbar" in bad.json()["detail"]


def test_status_projects_and_tasks_need_enabled_and_planner_role(client, admin, op, lab):
    assert client.get("/api/openplan/status", headers=admin).json()["enabled"] is False
    assert client.get("/api/openplan/projects", headers=admin).status_code == 409
    enable(client, admin, default_project_id="1")
    assert client.get("/api/openplan/status", headers=admin).json() == {"enabled": True, "default_project_id": "1", "base_url": "http://openplan.test:8083"}
    assert [p["name"] for p in client.get("/api/openplan/projects", headers=admin).json()] == ["Netz-Rollout"]
    t = client.get("/api/openplan/projects/1/tasks", headers=admin).json()
    assert t["project"]["name"] == "Netz-Rollout" and any(x["suggested"] and x["name"].startswith("Patchaufträge") for x in t["tasks"])       # Abschnitt wird vorgeschlagen
    assert [x["name"] for x in client.get("/api/openplan/projects/1/tasks?q=einzel", headers=admin).json()["tasks"]] == ["Einzelaufgabe"]
    assert client.get("/api/openplan/projects/99/tasks", headers=admin).status_code == 502
    vw, tk = user(client, admin, "vw", [("viewer", lab["site"])]), user(client, admin, "tk", [("techniker", lab["site"])])
    assert client.get("/api/openplan/projects", headers=vw).status_code == 403 and client.get("/api/openplan/projects", headers=tk).status_code == 403
    pl = user(client, admin, "pl", [("planer", lab["site"])])
    assert client.get("/api/openplan/projects", headers=pl).status_code == 200


# ── Verknüpfen und Abgleichen ─────────────────────────────────────────────────

def test_create_task_links_order_sets_reference_and_syncs_lifecycle(client, admin, op, lab):
    enable(client, admin)
    wo = lab["order"]("Trunk RZ ↔ E1", n=4)
    client.put(f"/api/workorders/{wo['id']}", headers=admin, json={"title": "Trunk RZ ↔ E1", "planned_from": "2026-11-23", "planned_to": "2026-11-27", "location_id": lab["rack"]})
    sec = [t for t in op.tasks.values() if t["name"].startswith("Patchaufträge")][0]["id"]
    r = client.post(f"/api/workorders/{wo['id']}/openplan/create", headers=admin, json={"project_id": 1, "parent_id": sec})
    assert r.status_code == 200, r.text
    o = r.json()["openplan"]
    tid = int(o["task"])
    t = op.tasks[tid]
    assert o["linked"] and o["project"] == "1" and o["link"] == f"http://openplan.test:8083/project/1?task={tid}"
    assert t["name"] == f"{wo['number']} Trunk RZ ↔ E1" and t["parent_id"] == sec and t["duration"] == 5 and t["constraint"] == ("SNET", "2026-11-23")      # 5 Arbeitstage
    assert f"https://opp.example.test/workorders/{wo['id']}" in t["notes"]
    assert op.refs[(tid, "portwerk")] == (wo["number"], f"https://opp.example.test/workorders/{wo['id']}")                                   # Referenz mit Link zurück
    assert t["status"] == "open" and o["status"] == "open"                                                                                           # Entwurf = offen
    assert client.post(f"/api/workorders/{wo['id']}/openplan/create", headers=admin, json={"project_id": 1}).status_code == 409                     # schon verknüpft
    # Lebenszyklus: Status/Fortschritt wandern automatisch nach OpenPlan
    step = lambda a: client.post(f"/api/workorders/{wo['id']}/transition/{a}", headers=admin, json={"override_reason": "Test (allein)"})  # noqa: E731
    for a in ("submit", "approve"):
        assert step(a).status_code == 200 and t["status"] == "open"
    assert step("start").status_code == 200 and t["status"] == "in_progress" and t["percent"] == 0
    items = client.get(f"/api/workorders/{wo['id']}", headers=admin).json()["items"]
    client.post(f"/api/workorders/{wo['id']}/items/bulk", headers=admin, json={"ids": [i["id"] for i in items[:1]], "action": "execute"})
    assert t["percent"] == 25 and t["status"] == "in_progress" and "1 von 4" in t["note"]
    client.post(f"/api/workorders/{wo['id']}/items/{items[1]['id']}/execute", headers=admin, json={"item_status": "done"})
    assert t["percent"] == 50
    client.post(f"/api/workorders/{wo['id']}/items/{items[1]['id']}/reopen", headers=admin)
    assert t["percent"] == 25
    client.post(f"/api/workorders/{wo['id']}/items/bulk", headers=admin, json={"ids": [i["id"] for i in items], "action": "execute"})
    assert step("finish").status_code == 200 and t["percent"] == 99 and t["status"] == "in_progress"                  # ausgeführt, aber noch nicht bestätigt
    assert step("confirm").status_code == 200 and t["status"] == "done" and t["percent"] == 100
    final = client.get(f"/api/workorders/{wo['id']}", headers=admin).json()["openplan"]
    assert final["status"] == "done" and final["percent"] == 100 and final["synced_at"] and final["error"] == ""


def test_rejection_and_rework_map_to_openplan(client, admin, op, lab):
    enable(client, admin)
    wo = lab["order"]("Abgelehnt")
    client.post(f"/api/workorders/{wo['id']}/openplan/create", headers=admin, json={"project_id": 1})
    t = op.tasks[int(client.get(f"/api/workorders/{wo['id']}", headers=admin).json()["openplan"]["task"])]
    client.post(f"/api/workorders/{wo['id']}/transition/submit", headers=admin, json={"override_reason": "Test (allein)"})
    client.post(f"/api/workorders/{wo['id']}/transition/reject", headers=admin, json={"override_reason": "Test (allein)"})
    assert t["status"] == "blocked" and "abgelehnt" in t["note"]


def test_link_existing_unlink_and_validation(client, admin, op, lab):
    enable(client, admin)
    a, b = lab["order"]("A"), lab["order"]("B", n=2)
    leaf = [t for t in op.tasks.values() if t["name"] == "Einzelaufgabe"][0]["id"]
    summary = [t for t in op.tasks.values() if t["name"] == "Planung"][0]["id"]
    link = lambda wid, task, pid=1: client.post(f"/api/workorders/{wid}/openplan/link", headers=admin, json={"project_id": pid, "task_id": task})  # noqa: E731
    assert link(a["id"], summary).status_code == 400                                          # Sammelvorgang
    assert link(a["id"], 99999).status_code == 404
    assert link(a["id"], leaf, pid=77).status_code == 502
    ok = link(a["id"], leaf)
    assert ok.status_code == 200 and ok.json()["openplan"]["linked"] and op.refs[(leaf, "portwerk")][0] == a["number"]
    assert link(b["id"], leaf).status_code == 409                                             # eine Aufgabe, ein Auftrag
    un = client.delete(f"/api/workorders/{a['id']}/openplan", headers=admin)
    assert un.status_code == 200 and not un.json()["openplan"]["linked"] and (leaf, "portwerk") not in op.refs
    assert link(b["id"], leaf).status_code == 200                                             # jetzt frei
    assert client.post(f"/api/workorders/{a['id']}/openplan/sync", headers=admin).status_code == 409                # nicht verknüpft


def test_sync_failure_never_breaks_the_workflow(client, admin, op, lab):
    from app.openplan import OpenPlanError
    enable(client, admin)
    wo = lab["order"]("Ausfall")
    client.post(f"/api/workorders/{wo['id']}/openplan/create", headers=admin, json={"project_id": 1})
    op.fail = OpenPlanError(0, "OpenPlan nicht erreichbar: Connection refused")
    r = client.post(f"/api/workorders/{wo['id']}/transition/submit", headers=admin, json={"override_reason": "Test (allein)"})
    assert r.status_code == 200 and r.json()["status"] == "submitted"                          # Arbeitsablauf läuft weiter
    assert "nicht erreichbar" in client.get(f"/api/workorders/{wo['id']}", headers=admin).json()["openplan"]["error"]
    assert any(a["action"] == "openplan.sync_failed" for a in client.get("/api/audit", headers=admin).json())
    op.fail = None
    res = client.post(f"/api/workorders/{wo['id']}/openplan/sync", headers=admin).json()
    assert res["sync"]["synced"] is True and res["openplan"]["error"] == ""                      # „Jetzt abgleichen“ holt es nach
    # Anbindung aus: nichts wird gesendet
    client.put("/api/admin/openplan", headers=admin, json={"enabled": False})
    n = len(op.calls)
    client.post(f"/api/workorders/{wo['id']}/transition/approve", headers=admin, json={"override_reason": "Test (allein)"})
    assert len(op.calls) == n
    client.put("/api/admin/openplan", headers=admin, json={"enabled": True, "auto_sync": False})
    client.post(f"/api/workorders/{wo['id']}/transition/start", headers=admin, json={"override_reason": "Test (allein)"})
    assert len(op.calls) == n                                                                  # auto_sync aus: nur manueller Abgleich


def test_bulk_create_tasks_for_several_orders(client, admin, op, lab):
    enable(client, admin)
    a, b, c = lab["order"]("A"), lab["order"]("B", n=2), lab["order"]("C", n=3)
    sec = [t for t in op.tasks.values() if t["name"].startswith("Patchaufträge")][0]["id"]
    client.post(f"/api/workorders/{a['id']}/openplan/create", headers=admin, json={"project_id": 1})
    r = client.post("/api/openplan/orders", headers=admin, json={"project_id": 1, "parent_id": sec, "workorder_ids": [a["id"], b["id"], c["id"], 99999]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert [x["number"] for x in d["created"]] == [b["number"], c["number"]] and d["skipped_linked"] == [a["number"]] and d["errors"][0]["id"] == 99999
    assert sum(1 for t in op.tasks.values() if t["parent_id"] == sec) == 3                      # Platzhalter + 2 neue
    assert client.get(f"/api/workorders/{b['id']}", headers=admin).json()["openplan"]["linked"]
    vw = user(client, admin, "vw", [("viewer", lab["site"])])
    assert client.post("/api/openplan/orders", headers=vw, json={"project_id": 1, "workorder_ids": [a["id"]]}).status_code == 403


def test_create_project_from_template_with_orders_and_members(client, admin, op, lab):
    enable(client, admin)
    a, b = lab["order"]("Trunk"), lab["order"]("Dosen", n=2)
    body = {"name": "Patchfelder RZ/E1", "start_date": "2026-12-01", "description": "Neubau", "members": ["anna", "bernd"], "workorder_ids": [a["id"], b["id"]]}
    r = client.post("/api/openplan/projects", headers=admin, json=body)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["name"] == "Patchfelder RZ/E1" and d["url"] == f"http://openplan.test:8083/project/{d['project_id']}" and len(d["created"]) == 2 and not d["errors"]
    assert op.wizard_body["kind"] == "patchpanel" and op.wizard_body["members"] == [{"user_id": 10, "role": "editor"}, {"user_id": 11, "role": "editor"}]
    sec = [t for t in op.tasks.values() if t["project_id"] == d["project_id"] and t["name"].startswith("Patchaufträge")][0]["id"]
    assert {t["name"] for t in op.tasks.values() if t["parent_id"] == sec} >= {f"{a['number']} Trunk", f"{b['number']} Dosen"}                  # unter dem Abschnitt der Vorlage
    assert client.get(f"/api/workorders/{a['id']}", headers=admin).json()["openplan"]["project"] == str(d["project_id"])
    n = len(op.projects)
    bad = client.post("/api/openplan/projects", headers=admin, json={**body, "name": "X", "members": ["gibtsnicht"], "workorder_ids": []})
    assert bad.status_code == 400 and "gibtsnicht" in bad.json()["detail"] and len(op.projects) == n          # nichts angelegt
    assert client.post("/api/openplan/projects", headers=admin, json={**body, "kind": "unbekannt"}).status_code == 400
    assert client.post("/api/openplan/projects", headers=admin, json={**body, "start_date": "morgen"}).status_code == 422
    assert client.post("/api/openplan/projects", headers=admin, json={**body, "workorder_ids": [99999]}).status_code == 404                    # Rechte/Existenz vorab geprüft


# ── Webhook von OpenPlan ──────────────────────────────────────────────────────

def signed(payload, secret="whsec_test", ts=None, sig=None):
    raw = json.dumps(payload).encode()
    ts = str(int(time.time()) if ts is None else ts)
    return raw, {"X-OpenPlan-Timestamp": ts, "X-OpenPlan-Signature": sig or ("sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()), "Content-Type": "application/json"}


def test_webhook_signature_ping_status_and_loop_protection(client, admin, op, lab):
    wo = lab["order"]("Webhook")
    assert client.post("/api/integrations/openplan/webhook", content=b"{}").status_code == 404                # nicht eingerichtet
    enable(client, admin)
    client.post("/api/admin/openplan/test", headers=admin)                                                     # merkt sich das Dienstkonto
    client.post(f"/api/workorders/{wo['id']}/openplan/create", headers=admin, json={"project_id": 1})
    tid = int(client.get(f"/api/workorders/{wo['id']}", headers=admin).json()["openplan"]["task"])
    hook = lambda payload, **kw: client.post("/api/integrations/openplan/webhook", **dict(zip(("content", "headers"), signed(payload, **kw))))  # noqa: E731
    ev = {"event": "task.status", "actor": "anna", "project": {"id": 1}, "task": {"id": tid, "status": "blocked", "percent": 30}}
    assert client.post("/api/integrations/openplan/webhook", content=b"{}", headers={"X-OpenPlan-Timestamp": str(int(time.time())), "X-OpenPlan-Signature": "sha256=00"}).status_code == 401
    assert hook(ev, sig="sha256=" + "0" * 64).status_code == 401                                               # falsche Signatur
    assert hook(ev, ts=int(time.time()) - 3600).status_code == 401                                             # zu alt
    assert hook(ev, secret="anderes").status_code == 401
    assert hook({"event": "ping"}).json()["pong"] is True
    ok = hook(ev)
    assert ok.status_code == 200 and ok.json()["updated"] == 1
    o = client.get(f"/api/workorders/{wo['id']}", headers=admin).json()["openplan"]
    assert o["status"] == "blocked" and o["percent"] == 30
    assert hook({**ev, "actor": "svc-opp", "task": {**ev["task"], "status": "done"}}).json()["ignored"] == "eigene Änderung"                  # eigene Änderung, keine Schleife
    assert client.get(f"/api/workorders/{wo['id']}", headers=admin).json()["openplan"]["status"] == "blocked"
    assert hook({**ev, "task": {"id": 99999, "status": "done", "percent": 100}}).json()["updated"] == 0                                        # unbekannte Aufgabe
    assert hook({"event": "task.assigned"}).json()["ignored"]


def test_openplan_fields_in_order_output_and_permissions_for_scoped_planer(client, admin, op, lab):
    enable(client, admin)
    wo = lab["order"]("Bereich")
    assert client.get(f"/api/workorders/{wo['id']}", headers=admin).json()["openplan"] == {"linked": False, "project": "", "task": "", "link": "", "status": "", "percent": None, "synced_at": None, "error": ""}
    pl = user(client, admin, "pl", [("planer", lab["site"])])
    assert client.post(f"/api/workorders/{wo['id']}/openplan/create", headers=pl, json={"project_id": 1}).status_code == 200
    other = user(client, admin, "other", [("planer", lab["site2"])])
    assert client.post(f"/api/workorders/{wo['id']}/openplan/sync", headers=other).status_code == 404         # fremder Standort
    tk = user(client, admin, "tk", [("techniker", lab["site"])])
    assert client.post(f"/api/workorders/{wo['id']}/openplan/sync", headers=tk).status_code == 403
    assert client.delete(f"/api/workorders/{wo['id']}/openplan", headers=tk).status_code == 403
