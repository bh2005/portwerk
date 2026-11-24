"""Checkmk: ausstehende Änderungen anzeigen und aktivieren (nur ohne fremde Änderungen)."""
import pytest

from app import checkmk_api


@pytest.fixture()
def cmk(client, admin, monkeypatch):
    state = {"changes": [], "calls": [], "running": False}

    def fake(cfg, method, path, body=None, headers=None, timeout=15):
        state["calls"].append((method, path, body, headers))
        if path.endswith("/pending_changes"):
            return 200, {"value": state["changes"]}
        if path.endswith("/activate-changes/invoke"):
            return (409, {"detail": "busy"}) if state["running"] else (200, {"id": "act1"})
        if path.startswith("/objects/activation_run/act1/actions/wait-for-completion"):
            return 204, None
        return 500, {"detail": "unerwartet"}
    monkeypatch.setattr(checkmk_api, "request", fake)
    assert client.put("/api/admin/checkmk-api", headers=admin, json={"enabled": True, "api_url": "http://cmk.example.test/mysite", "user": "portwerk", "secret": "s"}).status_code == 200
    return state


def test_pending_and_activate(client, admin, cmk):
    assert checkmk_api.site_name() == "mysite"
    p = client.get("/api/checkmk/pending", headers=admin).json()
    assert p["count"] == 0 and p["site"] == "mysite"
    assert client.post("/api/checkmk/activate", headers=admin).json()["activated"] is False                       # nichts zu tun
    assert not any(c[1].endswith("activate-changes/invoke") for c in cmk["calls"])

    cmk["changes"] = [{"user_id": "portwerk", "text": "Host angelegt", "time": "2026-11-24T10:00:00"}, {"user_id": "portwerk", "text": "Host angelegt 2"}]
    p = client.get("/api/checkmk/pending", headers=admin).json()
    assert (p["count"], p["own"], p["foreign"]) == (2, 2, 0)
    r = client.post("/api/checkmk/activate", headers=admin)
    assert r.status_code == 200 and r.json()["activated"] is True and r.json()["count"] == 2
    inv = [c for c in cmk["calls"] if c[1].endswith("activate-changes/invoke")][0]
    assert inv[2] == {"redirect": False, "sites": ["mysite"], "force_foreign_changes": False} and inv[3] == {"If-Match": "*"}   # nie force
    assert any("wait-for-completion" in c[1] for c in cmk["calls"])


def test_activate_refuses_foreign_changes(client, admin, cmk):
    cmk["changes"] = [{"user_id": "portwerk", "text": "a"}, {"user_id": "anna", "text": "b"}]
    p = client.get("/api/checkmk/pending", headers=admin).json()
    assert (p["own"], p["foreign"]) == (1, 1)
    r = client.post("/api/checkmk/activate", headers=admin)
    assert r.status_code == 409 and "anna" in r.json()["detail"]
    assert not any(c[1].endswith("activate-changes/invoke") for c in cmk["calls"])                              # nichts aktiviert


def test_activate_busy(client, admin, cmk):
    cmk["changes"] = [{"user_id": "portwerk", "text": "a"}]
    cmk["running"] = True
    assert client.post("/api/checkmk/activate", headers=admin).status_code == 409
