"""Abwesenheiten aus OpenPlan übernehmen: Zuordnung über Benutzername/E-Mail, Ersetzen beim Abgleich, nur lesbar,
Standard-Vertretung für übernommene Einträge, Fehler und Abschalten."""
from datetime import date, timedelta

import pytest

from conftest import login
from test_notify import fake_smtp  # noqa: F401  (Fixture)
from test_openplan import enable, op  # noqa: F401  (Fixture)

D = lambda n: (date.today() + timedelta(days=n)).isoformat()  # noqa: E731


@pytest.fixture()
def people(client, admin, op):  # noqa: F811
    ids = {}
    for name, mail in (("anna", "anna@example.test"), ("bernd", "b.holz@example.test"), ("carla", "carla@example.test")):
        r = client.post("/api/users", headers=admin, json={"username": name, "password": "Passwort-123", "roles": ["techniker"], "email": mail})
        ids[name] = r.json()["id"]
    op.absences = [
        {"id": 1, "username": "Anna", "display_name": "Anna", "email": "", "start_date": D(-2), "end_date": D(3), "kind": "vacation"},        # Name, andere Schreibweise
        {"id": 2, "username": "bholz", "display_name": "Bernd", "email": "B.Holz@example.test", "start_date": D(10), "end_date": D(12), "kind": "sick"},  # über E-Mail
        {"id": 3, "username": "fremd", "display_name": "Fremd", "email": "", "start_date": D(1), "end_date": D(2), "kind": "training"},         # unbekannt
        {"id": 4, "username": "anna", "display_name": "Anna", "email": "", "start_date": D(500), "end_date": D(501), "kind": "vacation"},    # außerhalb
    ]
    return ids


def test_sync_matches_and_replaces(client, admin, op, people):  # noqa: F811
    enable(client, admin, sync_absences=True)
    r = client.post("/api/admin/openplan/absences/sync", headers=admin)
    assert r.status_code == 200, r.text
    st = r.json()
    assert st["ok"] and st["received"] == 3 and st["imported"] == 2 and st["users"] == 2 and st["unmatched"] == ["fremd"]
    a = login(client, "anna", "Passwort-123")
    mine = client.get("/auth/me/absences", headers=a).json()["absences"]
    assert len(mine) == 1 and mine[0]["readonly"] and mine[0]["source_label"] == "OpenPlan" and mine[0]["note"] == "Urlaub (OpenPlan)" and mine[0]["current"]
    assert client.get("/auth/me", headers=a).json()["absent"]["until"] == D(3)
    b = client.get(f"/api/users/{people['bernd']}/absences", headers=admin).json()
    assert [(x["start_date"], x["note"]) for x in b] == [(D(10), "abwesend (OpenPlan)")]                         # krank → nur „abwesend“
    assert client.delete(f"/auth/me/absences/{mine[0]['id']}", headers=a).status_code == 409                     # nur in OpenPlan änderbar
    own = client.post("/auth/me/absences", headers=a, json={"start_date": D(20), "end_date": D(21), "note": "selbst"}).json()
    op.absences = op.absences[1:2]                                                                                # Annas Urlaub in OpenPlan gelöscht
    assert client.post("/api/admin/openplan/absences/sync", headers=admin).json()["imported"] == 1
    assert [x["id"] for x in client.get("/auth/me/absences", headers=a).json()["absences"]] == [own["id"]]       # eigener Eintrag bleibt
    assert client.get("/api/admin/openplan", headers=admin).json()["absences_status"]["imported"] == 1
    assert client.post("/api/admin/openplan/absences/sync", headers=a).status_code == 403


def test_default_deputy_gets_mail(client, admin, op, people, fake_smtp, monkeypatch):  # noqa: F811
    from app import notifications
    monkeypatch.setattr(notifications, "SEND_IN_BACKGROUND", False)
    client.put("/api/admin/mail", headers=admin, json={"enabled": True, "host": "mail.example.test", "port": 25, "from_addr": "opp@example.test"})
    enable(client, admin, sync_absences=True)
    a = login(client, "anna", "Passwort-123")
    assert client.put("/auth/me/deputy", headers=a, json={"deputy_id": people["anna"]}).status_code == 400        # nicht sich selbst
    r = client.put("/auth/me/deputy", headers=a, json={"deputy_id": people["carla"]})
    assert r.status_code == 200 and r.json()["deputy"]["username"] == "carla"
    client.post("/api/admin/openplan/absences/sync", headers=admin)
    mine = client.get("/auth/me/absences", headers=a).json()["absences"][0]
    assert mine["deputy"]["username"] == "carla" and mine["deputy_is_default"]
    assert client.get("/auth/me", headers=a).json()["absent"]["deputy"]["username"] == "carla"
    c = login(client, "carla", "Passwort-123")
    assert [p["username"] for p in client.get("/auth/me/absences", headers=c).json()["represents"]] == ["anna"]
    wo = client.post("/api/workorders", headers=admin, json={"title": "Platz 1"}).json()
    fake_smtp.sent.clear()
    r = client.post(f"/api/workorders/{wo['id']}/assign", headers=admin, json={"user_id": people["anna"], "notify": True}).json()
    assert "carla" in r["notify_note"] and any(m["To"] == "carla@example.test" for m in fake_smtp.sent)
    # Administrator setzt die Standard-Vertretung für andere
    assert client.put(f"/api/users/{people['bernd']}/deputy", headers=admin, json={"deputy_id": people["carla"]}).json()["deputy"]["username"] == "carla"
    assert client.get(f"/api/users/{people['bernd']}/deputy", headers=admin).json()["deputy"]["username"] == "carla"
    assert client.put(f"/api/users/{people['bernd']}/deputy", headers=a, json={"deputy_id": None}).status_code == 403
    # eigene Einträge ohne Vertretung bleiben ohne (Standard gilt nur für übernommene)
    own = client.post("/auth/me/absences", headers=c, json={"start_date": D(30), "end_date": D(31)}).json()
    assert own["deputy"] is None


def test_errors_keep_old_state_and_switching_off_clears(client, admin, op, people):  # noqa: F811
    from app import openplan
    enable(client, admin)
    assert openplan.sync_absences() == {}                                                    # aus: kein Abruf
    assert not any(p == "/api/absences" or p.startswith("/api/absences?") for _, p, _ in op.calls)
    enable(client, admin, sync_absences=True)
    openplan.sync_absences()
    assert openplan.absences_status()["imported"] == 2
    op.absences_allowed = False
    r = client.post("/api/admin/openplan/absences/sync", headers=admin)
    assert r.status_code == 502 and "Freigabe „Abwesenheiten“" in r.json()["detail"]
    a = login(client, "anna", "Passwort-123")
    assert len(client.get("/auth/me/absences", headers=a).json()["absences"]) == 1           # alter Stand bleibt
    assert client.put("/api/admin/openplan", headers=admin, json={"sync_absences": False}).json()["absences_status"] == {}
    assert client.get("/auth/me/absences", headers=a).json()["absences"] == []
