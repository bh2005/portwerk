"""Abwesenheit und Vertretung: Pflege, Anzeige, Umleitung der Benachrichtigungen (mit Berechtigungsprüfung), Zuweisung, „Meine Aufgaben“."""
from datetime import date, timedelta

import pytest

from conftest import login
from test_compare import nb
from test_notify import fake_smtp  # noqa: F401  (Fixture)

OVR = {"override_reason": "Test (allein)"}
TODAY = date.today()
D = lambda n: (TODAY + timedelta(days=n)).isoformat()  # noqa: E731


@pytest.fixture()
def lab(client, admin, fake_smtp, monkeypatch):  # noqa: F811
    from app import notifications
    monkeypatch.setattr(notifications, "SEND_IN_BACKGROUND", False)
    client.put("/api/admin/mail", headers=admin, json={"enabled": True, "host": "mail.example.test", "port": 25, "from_addr": "opp@example.test"})
    s = client.post("/api/sites", headers=admin, json={"code": "S1", "name": "Werk"}).json()["id"]
    s2 = client.post("/api/sites", headers=admin, json={"code": "S2", "name": "Fremd"}).json()["id"]
    rack = client.post("/api/locations", headers=admin, json={"site_id": s, "kind": "rack", "name": "R1", "rack_units": 20}).json()["id"]
    ids = {}
    for name, roles, scopes in (("frei", ["freigeber"], []), ("frei2", ["freigeber"], []), ("plan", ["planer"], []), ("tech", ["techniker"], []),
                                ("tech2", ["techniker"], []), ("fremd", [], [{"site_id": s2, "role": "planer"}])):
        r = client.post("/api/users", headers=admin, json={"username": name, "password": "Passwort-123", "roles": roles,
                                                           "email": f"{name}@example.test", "scopes": scopes})
        assert r.status_code == 201, r.text
        ids[name] = r.json()["id"]
    h = {n: login(client, n, "Passwort-123") for n in ids}

    def dev(name, dtype, ports):
        d = client.post("/api/devices", headers=admin, json={"hostname": name, "type": dtype, "location_id": rack}).json()
        return {"id": d["id"], **{n: client.post(f"/api/devices/{d['id']}/ports", headers=admin, json={"name": n}).json()["id"] for n in ports}}
    return {"ids": ids, "h": h, "rack": rack, "sw": dev("sw1", "switch", ["Gi0/1"]), "pc": dev("pc1", "endpoint", ["eth0"])}


def away(client, h, deputy=None, start=0, end=5):
    r = client.post("/auth/me/absences", headers=h, json={"start_date": D(start), "end_date": D(end), "deputy_id": deputy, "note": "Urlaub"})
    assert r.status_code == 201, r.text
    return r.json()


def mails(smtp):
    return [(m["To"], m["Subject"], m.get_body(preferencelist=("plain",)).get_content()) for m in smtp.sent]


def test_manage_and_show(client, admin, lab):
    h, ids = lab["h"], lab["ids"]
    a = away(client, h["tech"], deputy=ids["tech2"])
    assert a["current"] and a["deputy"]["username"] == "tech2"
    assert client.get("/auth/me", headers=h["tech"]).json()["absent"]["deputy"]["username"] == "tech2"
    assert client.get("/auth/me/absences", headers=h["tech2"]).json()["represents"][0]["username"] == "tech"
    bad = lambda **b: client.post("/auth/me/absences", headers=h["tech"], json={"start_date": D(0), "end_date": D(1), **b}).status_code  # noqa: E731
    assert bad(end_date=D(-1)) == 400 and bad(start_date=D(-5), end_date=D(-2)) == 400 and bad(deputy_id=ids["tech"]) == 400 and bad(deputy_id=99999) == 404
    future = away(client, h["tech"], start=10, end=12)
    assert not future["current"] and len(client.get("/auth/me/absences", headers=h["tech"]).json()["absences"]) == 2
    assert client.delete(f"/auth/me/absences/{future['id']}", headers=h["tech2"]).status_code == 404       # nur eigene
    assert client.delete(f"/auth/me/absences/{future['id']}", headers=h["tech"]).status_code == 200
    users = {u["username"]: u for u in client.get("/api/users", headers=admin).json()}
    assert users["tech"]["absent"]["until"] == D(5) and users["frei"]["absent"] is None
    r = client.post(f"/api/users/{ids['frei']}/absences", headers=admin, json={"start_date": D(0), "end_date": D(3)})
    assert r.status_code == 201 and client.post(f"/api/users/{ids['frei']}/absences", headers=h["plan"], json={"start_date": D(0), "end_date": D(3)}).status_code == 403


def test_creator_mail_goes_to_eligible_deputy(client, admin, lab, fake_smtp):  # noqa: F811
    h, ids = lab["h"], lab["ids"]
    away(client, h["plan"], deputy=ids["tech"])
    wo = client.post("/api/workorders", headers=h["plan"], json={"title": "Platz 1", "location_id": lab["rack"]}).json()
    client.post(f"/api/workorders/{wo['id']}/transition/submit", headers=h["plan"])
    fake_smtp.sent.clear()
    client.post(f"/api/workorders/{wo['id']}/transition/approve", headers=h["frei"])
    (to, _, body), = mails(fake_smtp)
    assert to == "tech@example.test" and "in Vertretung für plan" in body and f"abwesend bis {D(5)}" in body


def test_deputy_without_rights_keeps_mail_with_absent_person(client, admin, lab, fake_smtp):  # noqa: F811
    h, ids = lab["h"], lab["ids"]
    away(client, h["plan"], deputy=ids["fremd"])                          # „fremd“ sieht Standort S1 nicht
    wo = client.post("/api/workorders", headers=h["plan"], json={"title": "Platz 2", "location_id": lab["rack"]}).json()
    client.post(f"/api/workorders/{wo['id']}/transition/submit", headers=h["plan"])
    fake_smtp.sent.clear()
    client.post(f"/api/workorders/{wo['id']}/transition/reject", headers=h["frei"])
    assert [m[0] for m in mails(fake_smtp)] == ["plan@example.test"]


def test_approver_deputy_gets_one_mail(client, admin, lab, fake_smtp):  # noqa: F811
    from app import compare
    h, ids = lab["h"], lab["ids"]
    away(client, h["frei"], deputy=ids["frei2"])                         # Vertretung ist selbst Freigeber: nur eine Mail
    wo = client.post("/api/workorders", headers=h["plan"], json={"title": "Platz 3", "location_id": lab["rack"]}).json()
    client.post(f"/api/workorders/{wo['id']}/items", headers=h["plan"], json={"action": "connect", "port_a_id": lab["sw"]["Gi0/1"], "port_b_id": lab["pc"]["eth0"]})
    client.post(f"/api/workorders/{wo['id']}/transition/submit", headers=h["plan"])
    client.post(f"/api/workorders/{wo['id']}/transition/approve", headers=h["frei2"])
    client.post(f"/api/workorders/{wo['id']}/transition/start", headers=h["tech"])
    item = client.get(f"/api/workorders/{wo['id']}", headers=admin).json()["items"][0]
    client.post(f"/api/workorders/{wo['id']}/items/{item['id']}/execute", headers=h["tech"], json={"item_status": "done"})
    client.post(f"/api/workorders/{wo['id']}/transition/finish", headers=h["tech"])
    fake_smtp.sent.clear()
    compare.store({"sw1": [nb("Gi0/1", "pc1", "eth0")]})
    client.post(f"/api/workorders/{wo['id']}/verify", headers=admin)
    confirm = [m for m in mails(fake_smtp) if "zur Bestätigung" in m[1]]
    assert len(confirm) == 1 and confirm[0][0] == "frei2@example.test"


def test_assignment_and_my_tasks(client, admin, lab, fake_smtp):  # noqa: F811
    h, ids = lab["h"], lab["ids"]
    away(client, h["tech"], deputy=ids["tech2"])
    wo = client.post("/api/workorders", headers=h["plan"], json={"title": "Platz 4", "location_id": lab["rack"]}).json()
    users = {u["username"]: u for u in client.get("/api/directory/users", headers=h["plan"], params={"workorder_id": wo["id"]}).json()}
    assert users["tech"]["absent"]["deputy"]["username"] == "tech2"
    fake_smtp.sent.clear()
    r = client.post(f"/api/workorders/{wo['id']}/assign", headers=h["plan"], json={"user_id": ids["tech"], "notify": True}).json()
    assert r["assigned_to"]["username"] == "tech" and r["assigned_to"]["absent"]["until"] == D(5)   # Zuweisung bleibt bei tech
    assert r["notified"] and "Vertretung tech2" in r["notify_note"]
    assert [m[0] for m in mails(fake_smtp)] == ["tech2@example.test"] and "In Vertretung" in mails(fake_smtp)[0][1]
    mine = client.get("/api/workorders", headers=h["tech2"], params={"assigned": "me"}).json()
    assert [w["number"] for w in mine] == [wo["number"]]


def test_deputy_absent_too_means_no_forwarding(client, admin, lab, fake_smtp):  # noqa: F811
    h, ids = lab["h"], lab["ids"]
    away(client, h["plan"], deputy=ids["tech"])
    away(client, h["tech"])
    wo = client.post("/api/workorders", headers=h["plan"], json={"title": "Platz 5", "location_id": lab["rack"]}).json()
    client.post(f"/api/workorders/{wo['id']}/transition/submit", headers=h["plan"])
    fake_smtp.sent.clear()
    client.post(f"/api/workorders/{wo['id']}/transition/approve", headers=h["frei"])
    assert [m[0] for m in mails(fake_smtp)] == ["plan@example.test"]
