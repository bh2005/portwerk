"""Persönlicher Bereich: weitere Benachrichtigungen (mein Auftrag, LLDP-Abweichung, Reservierung läuft ab), Standard-Standort/Startseite,
alle anderen Anmeldungen beenden."""
from datetime import date, timedelta

import pytest

from conftest import ADMIN_PW, login
from test_compare import nb
from test_notify import fake_smtp  # noqa: F401  (Fixture)

OVR = {"override_reason": "Test (allein)"}


@pytest.fixture()
def lab(client, admin, fake_smtp, monkeypatch):  # noqa: F811
    from app import notifications
    monkeypatch.setattr(notifications, "SEND_IN_BACKGROUND", False)
    client.put("/api/admin/mail", headers=admin, json={"enabled": True, "host": "mail.example.test", "port": 25, "from_addr": "opp@example.test",
                                                       "public_url": "https://pw.example.test"})
    s = client.post("/api/sites", headers=admin, json={"code": "S1", "name": "Werk"}).json()["id"]
    s2 = client.post("/api/sites", headers=admin, json={"code": "S2", "name": "Fremd"}).json()["id"]
    rack = client.post("/api/locations", headers=admin, json={"site_id": s, "kind": "rack", "name": "R1", "rack_units": 20}).json()["id"]
    for name, roles in (("plan", ["planer"]), ("tech", ["techniker"]), ("frei", ["freigeber"])):
        assert client.post("/api/users", headers=admin, json={"username": name, "password": "Passwort-123", "roles": roles,
                                                              "email": f"{name}@example.test"}).status_code == 201
    client.post("/api/users", headers=admin, json={"username": "w1", "password": "Passwort-123", "roles": [], "email": "w1@example.test",
                                                   "scopes": [{"site_id": s, "role": "planer"}]})
    h = {n: login(client, n, "Passwort-123") for n in ("plan", "tech", "frei", "w1")}

    def dev(name, dtype, ports):
        d = client.post("/api/devices", headers=admin, json={"hostname": name, "type": dtype, "location_id": rack}).json()
        return {"id": d["id"], **{n: client.post(f"/api/devices/{d['id']}/ports", headers=admin, json={"name": n}).json()["id"] for n in ports}}
    sw, pc = dev("sw1", "switch", ["Gi0/1", "Gi0/2"]), dev("pc1", "endpoint", ["eth0"])
    return {"site": s, "site2": s2, "rack": rack, "h": h, "sw": sw, "pc": pc}


def order(client, lab, creator="plan"):
    wo = client.post("/api/workorders", headers=lab["h"][creator], json={"title": "Platz 9", "location_id": lab["rack"]}).json()
    client.post(f"/api/workorders/{wo['id']}/items", headers=lab["h"][creator],
                json={"action": "connect", "port_a_id": lab["sw"]["Gi0/1"], "port_b_id": lab["pc"]["eth0"]})
    client.post(f"/api/workorders/{wo['id']}/transition/submit", headers=lab["h"][creator])
    return wo


def recipients(smtp):
    return [m["To"] for m in smtp.sent]


def test_creator_gets_status_mails(client, admin, lab, fake_smtp):  # noqa: F811
    wo = order(client, lab)
    fake_smtp.sent.clear()
    assert client.post(f"/api/workorders/{wo['id']}/transition/approve", headers=lab["h"]["frei"]).status_code == 200
    assert recipients(fake_smtp) == ["plan@example.test"] and fake_smtp.sent[0]["Subject"] == f"[Portwerk] {wo['number']} freigegeben"
    assert "von frei freigegeben" in fake_smtp.sent[0].get_body(preferencelist=("plain",)).get_content()
    client.put("/auth/me/notifications", headers=lab["h"]["plan"], json={"my_orders": False})
    wo2 = order(client, lab)
    fake_smtp.sent.clear()
    client.post(f"/api/workorders/{wo2['id']}/transition/reject", headers=lab["h"]["frei"])
    assert fake_smtp.sent == []                                                      # abbestellt
    own = client.post("/api/workorders", headers=admin, json={"title": "eigen"}).json()
    client.post(f"/api/workorders/{own['id']}/transition/submit", headers=admin, json=OVR)
    fake_smtp.sent.clear()
    client.post(f"/api/workorders/{own['id']}/transition/reject", headers=admin)
    assert fake_smtp.sent == []                                                      # selbst ausgelöst


def test_executor_gets_lldp_problem_mail(client, admin, lab, fake_smtp):  # noqa: F811
    from app import compare
    wo = order(client, lab)
    client.post(f"/api/workorders/{wo['id']}/transition/approve", headers=lab["h"]["frei"])
    t = lab["h"]["tech"]
    client.post(f"/api/workorders/{wo['id']}/transition/start", headers=t)
    item = client.get(f"/api/workorders/{wo['id']}", headers=admin).json()["items"][0]
    client.post(f"/api/workorders/{wo['id']}/items/{item['id']}/execute", headers=t, json={"item_status": "done"})
    client.post(f"/api/workorders/{wo['id']}/transition/finish", headers=t)
    fake_smtp.sent.clear()
    compare.store({"sw1": [nb("Gi0/1", "drucker-9", "p1")]})
    assert client.post(f"/api/workorders/{wo['id']}/verify", headers=admin).json()["status"] == "problem"
    m = [x for x in fake_smtp.sent if x["To"] == "tech@example.test"]
    assert len(m) == 1 and "LLDP meldet eine Abweichung" in m[0]["Subject"] and "drucker-9" in m[0].get_body(preferencelist=("plain",)).get_content()


def test_reservation_reminder_once_and_after_extension(client, admin, lab, fake_smtp):  # noqa: F811
    from app import notifications
    soon, later = (date.today() + timedelta(days=2)).isoformat(), (date.today() + timedelta(days=20)).isoformat()
    r = client.post("/api/reservations", headers=lab["h"]["plan"], json={"port_ids": [lab["sw"]["Gi0/1"]], "purpose": "Kamera", "until": soon}).json()[0]
    client.post("/api/reservations", headers=lab["h"]["plan"], json={"port_ids": [lab["sw"]["Gi0/2"]], "purpose": "Drucker", "until": later})
    fake_smtp.sent.clear()
    assert notifications.reservation_reminders() == 1
    assert recipients(fake_smtp) == ["plan@example.test"] and "sw1:Gi0/1" in fake_smtp.sent[0].get_body(preferencelist=("plain",)).get_content()
    assert "Gi0/2" not in fake_smtp.sent[0].get_body(preferencelist=("plain",)).get_content()          # läuft erst in 20 Tagen ab
    assert notifications.reservation_reminders() == 0                                                # nur einmal
    client.put(f"/api/reservations/{r['id']}", headers=lab["h"]["plan"],
               json={"purpose": "Kamera", "until": (date.today() + timedelta(days=3)).isoformat()})       # verlängert
    assert notifications.reservation_reminders() == 1                                                # neue Frist, neue Erinnerung


def test_ui_preferences(client, admin, lab):
    h = lab["h"]["w1"]
    assert client.get("/auth/me", headers=h).json()["prefs"] == {"default_site_id": None, "start_page": ""}
    r = client.put("/auth/me/preferences", headers=h, json={"default_site_id": lab["site"], "start_page": "m"})
    assert r.status_code == 200 and r.json() == {"default_site_id": lab["site"], "start_page": "m"}
    assert client.get("/auth/me", headers=h).json()["prefs"]["start_page"] == "m"
    assert client.put("/auth/me/preferences", headers=h, json={"start_page": "irgendwo"}).status_code == 400
    assert client.put("/auth/me/preferences", headers=h, json={"default_site_id": lab["site2"]}).status_code == 404   # fremder Standort


def test_logout_other_sessions(client, admin, lab):
    a1, a2 = login(client, "plan", "Passwort-123"), login(client, "plan", "Passwort-123")
    assert client.get("/auth/me/sessions", headers=a1).json()["active"] >= 2
    r = client.post("/auth/me/logout-others", headers=a1)
    assert r.status_code == 200 and r.json()["ended"] >= 1
    new = {"X-Auth-Token": r.json()["token"]}
    assert client.get("/auth/me", headers=a2).status_code == 401 and client.get("/auth/me", headers=a1).status_code == 401
    assert client.get("/auth/me", headers=new).status_code == 200 and client.get("/auth/me/sessions", headers=new).json()["active"] == 1
    assert client.get("/auth/me", headers=login(client, "admin", ADMIN_PW)).status_code == 200          # andere Benutzer unberührt
