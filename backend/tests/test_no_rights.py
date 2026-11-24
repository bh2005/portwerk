"""Neue Benutzer ohne Rechte (z. B. beim ersten AD-Login angelegt): sehen keine Daten, nur einen Hinweis zur Freischaltung."""
import time

import pytest

from app import db
from app.security import hash_password
from conftest import login

PW = "Ohne-Rechte-123!"


@pytest.fixture()
def norights(client, admin):
    """Ein Konto ohne globale Rolle und ohne Standort-Rechte (so entsteht es beim ersten AD-Login ohne Standardrolle)."""
    s = client.post("/api/sites", headers=admin, json={"code": "NR1", "name": "Werk"}).json()["id"]
    loc = client.post("/api/locations", headers=admin, json={"site_id": s, "name": "Raum", "kind": "room"}).json()["id"]
    d = client.post("/api/devices", headers=admin, json={"hostname": "sw-nr", "type": "switch", "location_id": loc}).json()["id"]
    db.execute("INSERT INTO users(username, full_name, email, roles, source, password_hash, created_at) VALUES (?,?,?,?,?,?,?)",
               ("neuling", "Neu Ling", "neu@example.test", "", "local", hash_password(PW), time.time()))
    return {"h": login(client, "neuling", PW), "site": s, "device": d}


def empty(r):
    if r.status_code in (401, 403):
        return True
    j = r.json()
    if isinstance(j, list):
        return not j
    if isinstance(j, dict):
        if "items" in j:
            return not j["items"]
        return all(not v for k, v in j.items() if isinstance(v, (list, int)) and not isinstance(v, bool) and k not in ("warn",))
    return False


GET = ["/api/sites", "/api/locations", "/api/devices", "/api/cables", "/api/overview", "/api/workorders", "/api/search?q=sw", "/api/compare",
       "/api/capacity", "/api/cable-history?device_id={device}", "/api/devices/{device}", "/api/devices/{device}/ports", "/api/wan", "/api/vlans",
       "/api/port-reservations", "/api/patchlists", "/api/checkmk/status"]


def test_user_without_rights_sees_nothing(client, norights):
    me = client.get("/auth/me", headers=norights["h"]).json()
    assert me["roles"] == [] and me["scopes"] == []                                 # die Oberfläche zeigt daran den Hinweis
    leaks = []
    for p in GET:
        r = client.get(p.format(**norights), headers=norights["h"])
        if r.status_code in (404, 422):
            continue                                                              # Pfad gibt es in dieser Version nicht bzw. braucht Parameter
        if not empty(r):
            leaks.append((p, r.status_code, r.text[:120]))
    assert not leaks, leaks


def test_user_without_rights_cannot_write(client, norights):
    h = norights["h"]
    assert client.post("/api/sites", headers=h, json={"code": "X", "name": "x"}).status_code in (401, 403)
    assert client.post("/api/devices", headers=h, json={"hostname": "evil", "type": "switch"}).status_code in (401, 403)
    assert client.put(f"/api/devices/{norights['device']}", headers=h, json={"hostname": "umbenannt", "type": "switch"}).status_code in (401, 403, 404)
    assert client.get("/api/admin/backups", headers=h).status_code in (401, 403)
    assert client.get("/api/users", headers=h).status_code in (401, 403)
    assert client.post("/api/compare/adopt", headers=h, json={"port_id": 1}).status_code in (401, 403)
    assert client.post("/api/checkmk/hosts", headers=h, json={"hostname": "x"}).status_code in (401, 403)


# ── Hinweis-Mail an die globalen Administratoren ─────────────────────────────

class FakeSMTP:
    sent: list = []
    fail = False

    def __init__(self, host, port, timeout=None, context=None):
        pass

    def __enter__(self):
        if FakeSMTP.fail:
            raise OSError("SMTP nicht erreichbar")
        return self

    def __exit__(self, *a):
        return False

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


@pytest.fixture()
def mail(client, admin, monkeypatch):
    from app import auth, mailer, notifications
    FakeSMTP.sent, FakeSMTP.fail = [], False
    monkeypatch.setattr(mailer, "smtp_class", lambda: FakeSMTP)
    monkeypatch.setattr(mailer, "smtp_ssl_class", lambda: FakeSMTP)
    monkeypatch.setattr(notifications, "SEND_IN_BACKGROUND", False)
    mailer._sent.clear()
    auth._notify_try.clear()
    assert client.put("/api/admin/mail", headers=admin, json={"enabled": True, "host": "mail.example.test", "port": 25, "from_addr": "opp@example.test",
                                                              "public_url": "https://opp.example.test", "allowed_domains": ["example.test"]}).status_code == 200
    uid = client.get("/api/users", headers=admin).json()
    adm = [u for u in uid if u["username"] == "admin"][0]
    assert client.put(f"/api/users/{adm['id']}", headers=admin, json={"email": "admin@example.test"}).status_code == 200
    return FakeSMTP


def add_neuling():
    db.execute("DELETE FROM users WHERE username = 'neuling'")
    db.execute("INSERT INTO users(username, full_name, email, roles, source, password_hash, created_at) VALUES (?,?,?,?,?,?,?)",
               ("neuling", "Neu Ling", "neu@example.test", "", "local", hash_password(PW), time.time()))


def test_admins_get_mail_once_and_user_sees_hint(client, admin, mail):
    add_neuling()
    r = client.post("/auth/login", json={"username": "neuling", "password": PW})
    assert r.status_code == 200 and r.json()["user"]["admins_notified"] is True            # der Hinweistext nennt die Information der Administratoren
    assert len(mail.sent) == 1
    m = mail.sent[0]
    assert "admin@example.test" in m["To"] and "Neu Ling" in m["Subject"] and "Freischaltung" in m["Subject"]
    body = m.get_body(preferencelist=("plain",)).get_content()
    assert "neuling" in body and "noch keine Rechte" in body and "https://opp.example.test/admin" in body
    client.post("/auth/login", json={"username": "neuling", "password": PW})                # weitere Anmeldungen: keine weitere Mail
    assert len(mail.sent) == 1
    assert client.get("/auth/me", headers=login(client, "neuling", PW)).json()["admins_notified"] is True


def test_no_mail_when_mail_disabled_or_user_has_rights(client, admin, mail):
    add_neuling()
    client.put("/api/admin/mail", headers=admin, json={"enabled": False})
    r = client.post("/auth/login", json={"username": "neuling", "password": PW})
    assert r.status_code == 200 and r.json()["user"]["admins_notified"] is False and not mail.sent   # ohne Mail-Einrichtung wird nichts behauptet
    # Konto mit Rechten löst nie eine Mail aus
    client.put("/api/admin/mail", headers=admin, json={"enabled": True})
    from app import auth
    auth._notify_try.clear()
    r = client.post("/auth/login", json={"username": "admin", "password": __import__("conftest").ADMIN_PW})
    assert r.status_code == 200 and not mail.sent


def test_failed_mail_is_not_reported_as_informed(client, admin, mail):
    add_neuling()
    mail.fail = True
    r = client.post("/auth/login", json={"username": "neuling", "password": PW})
    assert r.status_code == 200 and r.json()["user"]["admins_notified"] is False            # Versand gescheitert: Anmeldung klappt, nichts Falsches behauptet
    from app import auth
    auth._notify_try.clear()                                                                  # nächster Versuch bei der nächsten Anmeldung (frühestens nach einer Stunde)
    mail.fail = False
    r = client.post("/auth/login", json={"username": "neuling", "password": PW})
    assert r.json()["user"]["admins_notified"] is True and len(mail.sent) == 1


def test_admin_can_opt_out_of_the_mail(client, admin, mail):
    me = client.get("/auth/me", headers=admin).json()
    assert me["notify"]["new_user"] is True
    assert client.put("/auth/me/notifications", headers=admin, json={"new_user": False}).status_code == 200
    add_neuling()
    r = client.post("/auth/login", json={"username": "neuling", "password": PW})
    assert r.json()["user"]["admins_notified"] is False and not mail.sent                    # keine Empfänger → nicht als informiert vermerkt
