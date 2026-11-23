"""E-Mail an Freigeber, wenn die LLDP-Prüfung einen ausgeführten Auftrag zur Bestätigung vorschlägt."""
import pytest

from conftest import login
from test_compare import nb
from test_notify import fake_smtp  # noqa: F401  (Fixture)

OVR = {"override_reason": "Test (allein)"}


@pytest.fixture()
def lab(client, admin, fake_smtp, monkeypatch):  # noqa: F811
    from app import notifications
    monkeypatch.setattr(notifications, "SEND_IN_BACKGROUND", False)
    assert client.put("/api/admin/mail", headers=admin, json={"enabled": True, "host": "mail.example.test", "port": 25, "from_addr": "opp@example.test",
                                                              "public_url": "https://pw.example.test"}).status_code == 200
    s = client.post("/api/sites", headers=admin, json={"code": "S1", "name": "Werk"}).json()["id"]
    s2 = client.post("/api/sites", headers=admin, json={"code": "S2", "name": "Fremd"}).json()["id"]
    rack = client.post("/api/locations", headers=admin, json={"site_id": s, "kind": "rack", "name": "R1", "rack_units": 20}).json()["id"]

    def user(name, roles=(), scopes=(), email=True):
        r = client.post("/api/users", headers=admin, json={"username": name, "password": "Passwort-123", "roles": list(roles),
                                                           "email": f"{name}@example.test" if email else "",
                                                           "scopes": [{"site_id": sid, "role": role} for sid, role in scopes]})
        assert r.status_code == 201, r.text
    user("frei", ["freigeber"])
    user("frei-s1", scopes=[(s, "freigeber")])
    user("frei-s2", scopes=[(s2, "freigeber")])
    user("frei-ohne", ["freigeber"], email=False)
    user("allrounder", ["freigeber", "techniker", "planer"])

    def dev(name, dtype, ports):
        d = client.post("/api/devices", headers=admin, json={"hostname": name, "type": dtype, "location_id": rack}).json()
        return {"id": d["id"], **{n: client.post(f"/api/devices/{d['id']}/ports", headers=admin, json={"name": n}).json()["id"] for n in ports}}
    sw, pc = dev("sw1", "switch", ["Gi0/1"]), dev("pc1", "endpoint", ["eth0"])
    wo = client.post("/api/workorders", headers=admin, json={"title": "Platz 7", "location_id": rack}).json()
    client.post(f"/api/workorders/{wo['id']}/items", headers=admin, json={"action": "connect", "port_a_id": sw["Gi0/1"], "port_b_id": pc["eth0"]})
    ar = login(client, "allrounder", "Passwort-123")
    client.post(f"/api/workorders/{wo['id']}/transition/submit", headers=admin, json=OVR)
    client.post(f"/api/workorders/{wo['id']}/transition/approve", headers=ar)
    client.post(f"/api/workorders/{wo['id']}/transition/start", headers=ar)
    item = client.get(f"/api/workorders/{wo['id']}", headers=admin).json()["items"][0]
    client.post(f"/api/workorders/{wo['id']}/items/{item['id']}/execute", headers=ar, json={"item_status": "done"})
    assert client.post(f"/api/workorders/{wo['id']}/transition/finish", headers=ar).json()["finished_by"] == "allrounder"
    return {"wo": wo, "admin": admin}


def lldp_ok(client, admin, wid):
    from app import compare
    compare.store({"sw1": [nb("Gi0/1", "pc1", "eth0")]})
    r = client.post(f"/api/workorders/{wid}/verify", headers=admin)
    assert r.status_code == 200 and r.json()["status"] == "ok", r.text


def test_approvers_get_one_mail(client, admin, lab, fake_smtp):  # noqa: F811
    wid = lab["wo"]["id"]
    fake_smtp.sent.clear()
    lldp_ok(client, admin, wid)
    assert len(fake_smtp.sent) == 1
    m = fake_smtp.sent[0]
    assert sorted(a.strip() for a in m["To"].split(",")) == ["frei-s1@example.test", "frei@example.test"]   # nicht S2, nicht der Ausführende
    assert m["Subject"] == f"[Portwerk] {lab['wo']['number']} zur Bestätigung vorgeschlagen – LLDP stimmt"
    body = m.get_body(preferencelist=("plain",)).get_content()
    assert "von allrounder" in body and f"https://pw.example.test/workorders/{wid}" in body
    lldp_ok(client, admin, wid)                                                       # bleibt „stimmt“: keine zweite Mail
    assert len(fake_smtp.sent) == 1
    log = client.get("/api/audit", headers=admin).json()
    assert any(e["action"] == "mail.confirm_suggest" for e in (log["items"] if isinstance(log, dict) else log))


def test_switched_off_and_domain_filter(client, admin, lab, fake_smtp):  # noqa: F811
    client.put("/api/admin/mail", headers=admin, json={"notify_confirm_suggest": False})
    assert client.get("/api/admin/mail", headers=admin).json()["notify_confirm_suggest"] is False
    fake_smtp.sent.clear()
    lldp_ok(client, admin, lab["wo"]["id"])
    assert fake_smtp.sent == []


def test_disallowed_domains_are_skipped(client, admin, lab, fake_smtp):  # noqa: F811
    from app import notifications
    client.put("/api/admin/mail", headers=admin, json={"allowed_domains": ["corp.example"]})
    assert notifications.confirm_suggested(lab["wo"]["id"], {"ok": 1}) == 0                # alle Empfänger außerhalb der Positivliste
    assert fake_smtp.sent == []


def test_personal_opt_out(client, admin, lab, fake_smtp):  # noqa: F811
    h = login(client, "frei", "Passwort-123")
    assert all(client.get("/auth/me", headers=h).json()["notify"].values())                                  # Standard: alles an
    r = client.put("/auth/me/notifications", headers=h, json={"confirm_suggest": False})
    assert r.status_code == 200 and r.json()["confirm_suggest"] is False and r.json()["assigned"] is True
    assert next(u for u in client.get("/api/users", headers=admin).json() if u["username"] == "frei")["notify"]["confirm_suggest"] is False
    fake_smtp.sent.clear()
    lldp_ok(client, admin, lab["wo"]["id"])
    assert [m["To"] for m in fake_smtp.sent] == ["frei-s1@example.test"]                # „frei“ hat abbestellt


def test_assignment_mail_respects_opt_out(client, admin, lab, fake_smtp):  # noqa: F811
    h = login(client, "frei", "Passwort-123")
    client.put("/auth/me/notifications", headers=h, json={"assigned": False})
    uid = next(u for u in client.get("/api/users", headers=admin).json() if u["username"] == "frei")["id"]
    fake_smtp.sent.clear()
    r = client.post(f"/api/workorders/{lab['wo']['id']}/assign", headers=admin, json={"user_id": uid, "notify": True}).json()
    assert r["notified"] is False and "abbestellt" in r["notify_note"] and fake_smtp.sent == []
    assert client.put("/auth/me/notifications", headers=admin, json={"assigned": True}).status_code == 200          # auch Admins
