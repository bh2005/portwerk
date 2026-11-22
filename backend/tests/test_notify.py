"""E-Mail-Versand von Aufträgen/Patchlisten, Zuweisung an Benutzer, SMTP-Einstellungen."""
import smtplib

import pytest

from conftest import login


class FakeSMTP:
    sent: list = []
    fail = False
    logins: list = []
    started_tls = False

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port = host, port

    def __enter__(self):
        if FakeSMTP.fail:
            raise smtplib.SMTPConnectError(421, "nicht erreichbar")
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        FakeSMTP.started_tls = True

    def login(self, user, pw):
        FakeSMTP.logins.append((user, pw))

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


@pytest.fixture(autouse=True)
def fake_smtp(monkeypatch):
    from app import mailer
    FakeSMTP.sent, FakeSMTP.fail, FakeSMTP.logins, FakeSMTP.started_tls = [], False, [], False
    monkeypatch.setattr(mailer, "smtp_class", lambda: FakeSMTP)
    monkeypatch.setattr(mailer, "smtp_ssl_class", lambda: FakeSMTP)
    mailer._sent.clear()
    return FakeSMTP


def enable(client, admin, **kw):
    r = client.put("/api/admin/mail", headers=admin, json={"enabled": True, "host": "mail.example.test", "port": 25, "from_addr": "opp@example.test",
                                                          "public_url": "https://opp.example.test/", **kw})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture()
def lab(client, admin):
    s = client.post("/api/sites", headers=admin, json={"code": "W1", "name": "Werk"}).json()["id"]
    s2 = client.post("/api/sites", headers=admin, json={"code": "W2", "name": "Fremd"}).json()["id"]
    rack = client.post("/api/locations", headers=admin, json={"site_id": s, "kind": "rack", "name": "R1", "rack_units": 12}).json()["id"]
    ports = {}
    for h in ("sw-a", "sw-b"):
        d = client.post("/api/devices", headers=admin, json={"hostname": h, "location_id": rack}).json()
        ports[h] = [client.post(f"/api/devices/{d['id']}/ports", headers=admin, json={"name": f"P{i}"}).json()["id"] for i in range(1, 5)]
    pairs = [{"port_a_id": ports["sw-a"][i], "port_b_id": ports["sw-b"][i], "cable_label": f"K-{i + 1}"} for i in range(4)]
    wo = client.post("/api/wizards/bulk-cables", headers=admin, json={"pairs": pairs, "mode": "workorder", "workorder_title": "Vier Kabel"}).json()["workorder"]
    return {"site": s, "site2": s2, "rack": rack, "wo": wo["id"], "number": wo["number"], "ports": ports}


def user(client, admin, name, *, scopes=(), roles=(), email=""):
    r = client.post("/api/users", headers=admin, json={"username": name, "password": "Passwort-123", "roles": list(roles), "email": email,
                                                       "scopes": [{"role": r, "site_id": s} for r, s in scopes]})
    assert r.status_code == 201, r.text
    return r.json()


# ── Einstellungen ─────────────────────────────────────────────────────────────

def test_settings_default_off_validation_and_secret(client, admin):
    s = client.get("/api/admin/mail", headers=admin).json()
    assert s["enabled"] is False and s["host"] == "" and s["password_set"] is False and "password" not in s
    put = lambda **kw: client.put("/api/admin/mail", headers=admin, json=kw)  # noqa: E731
    assert put(enabled=True).status_code == 422                                              # Server/Absender fehlen
    assert put(from_addr="kaputt").status_code == 422
    assert put(security="tls13").status_code == 422
    assert put(public_url="ftp://x").status_code == 422
    assert put(allowed_domains=["keine domain"]).status_code == 422
    ok = put(host="m.example.test", from_addr="a@example.test", username="u", password="geheim", allowed_domains=["@Example.Test", "corp.example"], public_url="https://opp.example.test/").json()
    assert ok["password_set"] is True and "geheim" not in str(ok) and ok["allowed_domains"] == ["corp.example", "example.test"] and ok["public_url"] == "https://opp.example.test"
    assert put(host="m2.example.test").json()["password_set"] is True                        # leeres Passwort lässt es stehen
    assert put(clear_password=True).json()["password_set"] is False
    user(client, admin, "pl", roles=("planer",))
    h = login(client, "pl", "Passwort-123")
    assert client.get("/api/admin/mail", headers=h).status_code == 403 and client.put("/api/admin/mail", headers=h, json={}).status_code == 403


def test_mail_test_and_smtp_options(client, admin, fake_smtp):
    assert client.post("/api/admin/mail/test", headers=admin, json={"to": "a@example.test"}).status_code == 409           # nicht eingerichtet
    enable(client, admin, security="starttls", username="svc", password="pw")
    r = client.post("/api/admin/mail/test", headers=admin, json={"to": "a@example.test"})
    assert r.status_code == 200 and len(fake_smtp.sent) == 1 and fake_smtp.started_tls and fake_smtp.logins == [("svc", "pw")]
    assert fake_smtp.sent[0]["To"] == "a@example.test" and "Testnachricht" in fake_smtp.sent[0]["Subject"]
    enable(client, admin, allowed_domains=["example.test"])
    assert client.post("/api/admin/mail/test", headers=admin, json={"to": "x@fremd.test"}).status_code == 403            # Domain nicht freigegeben
    assert client.post("/api/admin/mail/test", headers=admin, json={"to": "kein-mail"}).status_code == 400
    fake_smtp.fail = True
    assert client.post("/api/admin/mail/test", headers=admin, json={"to": "a@example.test"}).status_code == 502


# ── Auftrag senden ────────────────────────────────────────────────────────────

def test_send_workorder_to_user_and_external_with_csv(client, admin, lab, fake_smtp):
    user(client, admin, "tech", scopes=[("techniker", lab["site"])], email="tech@example.test")
    uid = {u["username"]: u["id"] for u in client.get("/api/users", headers=admin).json()}["tech"]
    body = {"user_ids": [uid], "emails": ["extern@example.test"], "message": "Bitte bis Freitag erledigen.", "attach_pdf": True}
    assert client.post(f"/api/workorders/{lab['wo']}/send", headers=admin, json=body).status_code == 409                # Versand aus
    enable(client, admin)
    r = client.post(f"/api/workorders/{lab['wo']}/send", headers=admin, json=body)
    assert r.status_code == 200, r.text
    assert sorted(r.json()["sent_to"]) == ["extern@example.test", "tech@example.test"] and r.json()["items"] == 4
    m = fake_smtp.sent[0]
    assert f"[Portwerk] {lab['number']} Vier Kabel (4 Positionen)" == m["Subject"] and m["From"].endswith("<opp@example.test>")
    text = m.get_body(preferencelist=("plain",)).get_content()
    assert "Bitte bis Freitag erledigen." in text and f"https://opp.example.test/workorders/{lab['wo']}" in text and "sw-a:P1 → sw-b:P1" in text and "K-4" in text
    html = m.get_body(preferencelist=("html",)).get_content()
    assert "Im System öffnen" in html and "sw-b:P4" in html
    att = list(m.iter_attachments())
    assert [a.get_filename() for a in att] == [f"{lab['number']}-arbeitsliste.csv", f"{lab['number']}-arbeitsanweisung.pdf"]
    assert att[1].get_content_type() == "application/pdf" and att[1].get_payload(decode=True).startswith(b"%PDF")
    csv_text = att[0].get_content()
    assert "Nr;Aktion" in csv_text and "sw-a:P2;sw-b:P2;K-2" in csv_text
    audit = [a for a in client.get("/api/audit", headers=admin).json() if a["action"] == "workorder.send"]
    assert audit and "extern@example.test" in audit[0]["detail"]
    # ohne Anhang / ohne Positionsliste im Text
    r = client.post(f"/api/workorders/{lab['wo']}/send", headers=admin, json={"emails": ["x@example.test"], "attach_csv": False, "include_list": False})
    assert r.status_code == 200 and not list(fake_smtp.sent[-1].iter_attachments()) and "sw-a:P1" not in fake_smtp.sent[-1].get_body(preferencelist=("plain",)).get_content()


def test_send_validation_access_and_limits(client, admin, lab, fake_smtp, monkeypatch):
    from app import mailer
    enable(client, admin, allowed_domains=["example.test"])
    send = lambda headers=admin, **kw: client.post(f"/api/workorders/{lab['wo']}/send", headers=headers, json=kw)  # noqa: E731
    assert send().status_code == 400                                                           # kein Empfänger
    assert send(emails=["kaputt"]).status_code == 400
    assert send(emails=["x@fremd.test"]).status_code == 403                                    # Domain-Freigabeliste
    assert send(emails=[f"u{i}@example.test" for i in range(21)]).status_code == 400            # Empfänger-Limit
    u_nomail = user(client, admin, "nomail", scopes=[("techniker", lab["site"])])
    u_foreign = user(client, admin, "foreign", scopes=[("techniker", lab["site2"])], email="f@example.test")
    r = send(user_ids=[u_nomail["id"]], emails=["ok@example.test"])
    assert r.status_code == 200 and r.json()["skipped_no_email"] == ["nomail"] and r.json()["sent_to"] == ["ok@example.test"]
    assert send(user_ids=[u_foreign["id"]]).status_code == 400                                 # kein Zugriff auf den Standort -> nichts senden
    assert send(user_ids=[99999]).status_code == 400
    vw = user(client, admin, "vw", scopes=[("viewer", lab["site"])], email="v@example.test")
    h = login(client, "vw", "Passwort-123")
    assert send(headers=h, emails=["ok@example.test"]).status_code == 403                      # Betrachter dürfen nicht senden
    tk = login(client, "nomail", "Passwort-123")
    assert send(headers=tk, emails=["ok@example.test"]).status_code == 200                      # Techniker schon
    other = user(client, admin, "other", scopes=[("planer", lab["site2"])])
    oh = login(client, "other", "Passwort-123")
    assert send(headers=oh, emails=["ok@example.test"]).status_code == 404                     # fremder Standort: Auftrag unsichtbar
    fake_smtp.fail = True
    assert send(emails=["ok@example.test"]).status_code == 502
    fake_smtp.fail = False
    monkeypatch.setattr(mailer, "RATE_LIMIT", (2, 600))
    mailer._sent.clear()
    assert send(emails=["a@example.test"]).status_code == 200 and send(emails=["a@example.test"]).status_code == 200
    assert send(emails=["a@example.test"]).status_code == 429                                  # Rate-Limit
    del vw, other


def test_header_injection_is_neutralised(client, admin, lab, fake_smtp):
    enable(client, admin)
    client.put(f"/api/workorders/{lab['wo']}", headers=admin, json={"title": "Test\r\nBcc: boss@example.test"})
    r = client.post(f"/api/workorders/{lab['wo']}/send", headers=admin, json={"emails": ["a@example.test"]})
    assert r.status_code == 200, r.text
    m = fake_smtp.sent[-1]
    assert "\n" not in m["Subject"] and "\r" not in m["Subject"] and m["Bcc"] is None
    assert client.post(f"/api/workorders/{lab['wo']}/send", headers=admin, json={"emails": ["a@example.test\r\nBcc: x@example.test"]}).status_code == 400


def test_send_patchlist_of_several_orders(client, admin, lab, fake_smtp):
    enable(client, admin)
    d = client.post("/api/devices", headers=admin, json={"hostname": "sw-c", "location_id": lab["rack"]}).json()
    c1 = client.post(f"/api/devices/{d['id']}/ports", headers=admin, json={"name": "P1"}).json()["id"]
    c2 = client.post(f"/api/devices/{d['id']}/ports", headers=admin, json={"name": "P2"}).json()["id"]
    w2 = client.post("/api/wizards/bulk-cables", headers=admin, json={"pairs": [{"port_a_id": c1, "port_b_id": c2, "cable_label": "Z-1"}], "mode": "workorder", "workorder_title": "Zwei"}).json()["workorder"]
    r = client.post("/api/patchlists/send", headers=admin, json={"ids": [lab["wo"], w2["id"]], "emails": ["l@example.test"], "message": "Reihenfolge nach Ort"})
    assert r.status_code == 200, r.text
    assert r.json()["items"] == 5
    m = fake_smtp.sent[-1]
    assert "Patchliste" in m["Subject"] and lab["number"] in m["Subject"] and w2["number"] in m["Subject"]
    text = m.get_body(preferencelist=("plain",)).get_content()
    assert "Reihenfolge nach Ort" in text and f"/patchlist?ids={lab['wo']},{w2['id']}" in text and "Z-1" in text
    att = list(m.iter_attachments())[0]
    assert att.get_filename() == "patchliste.csv" and "Z-1" in att.get_content() and "K-1" in att.get_content()
    assert client.post("/api/patchlists/send", headers=admin, json={"ids": [99999], "emails": ["l@example.test"]}).status_code == 404
    assert client.post("/api/patchlists/send", headers=admin, json={"ids": [], "emails": ["l@example.test"]}).status_code == 422


# ── Zuweisen und „Meine Aufgaben“ ─────────────────────────────────────────────

def test_assign_notify_and_my_tasks(client, admin, lab, fake_smtp):
    tech = user(client, admin, "tech", scopes=[("techniker", lab["site"])], email="tech@example.test")
    nomail = user(client, admin, "nomail", scopes=[("techniker", lab["site"])])
    foreign = user(client, admin, "foreign", scopes=[("techniker", lab["site2"])], email="f@example.test")
    assign = lambda uid, **kw: client.post(f"/api/workorders/{lab['wo']}/assign", headers=admin, json={"user_id": uid, **kw})  # noqa: E731
    r = assign(tech["id"])                                                                      # Versand aus: Zuweisung klappt, Hinweis
    assert r.status_code == 200 and r.json()["assigned_to"]["username"] == "tech" and r.json()["notified"] is False and "nicht eingerichtet" in r.json()["notify_note"]
    enable(client, admin)
    r = assign(tech["id"], message="Bitte priorisieren")
    assert r.json()["notified"] is True and fake_smtp.sent[-1]["To"] == "tech@example.test" and "Dir zugewiesen" in fake_smtp.sent[-1]["Subject"]
    assert "Bitte priorisieren" in fake_smtp.sent[-1].get_body(preferencelist=("plain",)).get_content()
    r = assign(nomail["id"])
    assert r.json()["assigned_to"]["username"] == "nomail" and "keine E-Mail-Adresse" in r.json()["notify_note"]
    assert assign(foreign["id"]).status_code == 400                                             # kein Zugriff auf den Standort
    assert assign(99999).status_code == 400
    n = len(fake_smtp.sent)
    assert assign(tech["id"], notify=False).json()["notified"] is False and len(fake_smtp.sent) == n
    # Meine Aufgaben
    th = login(client, "tech", "Passwort-123")
    mine = client.get("/api/workorders?assigned=me", headers=th).json()
    assert [w["id"] for w in mine] == [lab["wo"]] and mine[0]["assigned_to"]["username"] == "tech"
    assert client.get("/api/workorders?assigned=me", headers=admin).json() == []
    assert [w["id"] for w in client.get(f"/api/workorders?assigned={tech['id']}", headers=admin).json()] == [lab["wo"]]
    assert client.get("/api/workorders?assigned=abc", headers=admin).json() == []
    # aufheben
    r = assign(None)
    assert r.json()["assigned_to"] is None and client.get("/api/workorders?assigned=me", headers=th).json() == []
    # Rechte
    vw = user(client, admin, "vw", scopes=[("viewer", lab["site"])])
    vh = login(client, "vw", "Passwort-123")
    assert client.post(f"/api/workorders/{lab['wo']}/assign", headers=vh, json={"user_id": tech["id"]}).status_code == 403
    assert client.post(f"/api/workorders/{lab['wo']}/assign", headers=th, json={"user_id": tech["id"]}).status_code == 403          # Techniker weist nicht zu
    del vw


def test_selfassign_does_not_send_mail(client, admin, lab, fake_smtp):
    enable(client, admin)
    me = [u for u in client.get("/api/users", headers=admin).json() if u["username"] == "admin"][0]
    r = client.post(f"/api/workorders/{lab['wo']}/assign", headers=admin, json={"user_id": me["id"]})
    assert r.status_code == 200 and r.json()["notified"] is False and not fake_smtp.sent


def test_directory_filters_by_access_and_hides_addresses(client, admin, lab):
    a = user(client, admin, "innen", scopes=[("techniker", lab["site"])], email="i@example.test")
    user(client, admin, "aussen", scopes=[("techniker", lab["site2"])], email="a@example.test")
    user(client, admin, "global", roles=("planer",))
    allu = client.get("/api/directory/users", headers=admin).json()
    assert {u["username"] for u in allu} >= {"admin", "innen", "aussen", "global"}
    assert all("email" not in u for u in allu) and {u["username"]: u["has_email"] for u in allu}["innen"] is True and {u["username"]: u["has_email"] for u in allu}["global"] is False
    scoped = client.get(f"/api/directory/users?workorder_id={lab['wo']}", headers=admin).json()
    names = {u["username"] for u in scoped}
    assert "innen" in names and "global" in names and "aussen" not in names                    # nur wer den Auftrag sehen darf
    assert {u["username"]: u["roles"] for u in scoped}["innen"] == ["techniker"]
    ih = login(client, "innen", "Passwort-123")
    assert client.get("/api/directory/users", headers=ih).status_code == 200
    assert client.get("/api/directory/users?workorder_id=99999", headers=ih).status_code == 404
    del a
