"""Englisch für vom Server erzeugte Texte: Benachrichtigungen in der Sprache des Empfängers, „Senden …“ in der des Absenders,
PDF und CSV in der Sprache dessen, der sie abruft; Deutsch bleibt Standard."""
import pytest

from conftest import login
from test_notify import fake_smtp  # noqa: F401  (Fixture)
from test_workpdf import lab, text_of  # noqa: F401  (Fixture)

OVR = {"override_reason": "Test (allein)"}


def set_lang(client, h, lang):
    assert client.put("/auth/me/preferences", headers=h, json={"start_page": "", "lang": lang}).json()["lang"] == lang


def body(m):
    return m.get_body(preferencelist=("plain",)).get_content()


@pytest.fixture()
def people(client, admin, fake_smtp, monkeypatch):  # noqa: F811
    from app import notifications
    monkeypatch.setattr(notifications, "SEND_IN_BACKGROUND", False)
    client.put("/api/admin/mail", headers=admin, json={"enabled": True, "host": "mail.example.test", "port": 25, "from_addr": "opp@example.test",
                                                       "public_url": "https://pw.example.test"})
    h = {}
    for name, lang in (("ann", "en"), ("bea", "de")):
        client.post("/api/users", headers=admin, json={"username": name, "password": "Passwort-123", "roles": ["planer", "freigeber", "techniker"],
                                                       "email": f"{name}@example.test"})
        h[name] = login(client, name, "Passwort-123")
        set_lang(client, h[name], lang)
    return h


def test_status_mail_in_recipients_language(client, admin, lab, people, fake_smtp):  # noqa: F811
    wid = lab["wo"]["id"]
    ann = people["ann"]
    client.put(f"/api/workorders/{wid}", headers=admin, json={"title": "Umbau Etage 2"})
    # ann legt einen Auftrag an, bea gibt frei → Mail an ann auf Englisch
    wo = client.post("/api/workorders", headers=ann, json={"title": "Platz 7"}).json()
    client.post(f"/api/workorders/{wo['id']}/transition/submit", headers=ann, json=OVR)
    fake_smtp.sent.clear()
    assert client.post(f"/api/workorders/{wo['id']}/transition/approve", headers=people["bea"]).status_code == 200
    m = next(x for x in fake_smtp.sent if x["To"] == "ann@example.test")
    assert m["Subject"] == f"[Portwerk] {wo['number']} approved"
    assert f"Your patch order {wo['number']} “Platz 7” was approved by bea." in body(m) and "It can now be carried out." in body(m)
    assert "Open in Portwerk" in m.get_body(preferencelist=("html",)).get_content()


def test_approvers_get_one_mail_per_language(client, admin, people, fake_smtp):  # noqa: F811
    from app import notifications
    wo = client.post("/api/workorders", headers=admin, json={"title": "LLDP"}).json()
    fake_smtp.sent.clear()
    assert notifications.confirm_suggested(wo["id"], {"ok": 2}) == 2
    subj = {m["To"]: m["Subject"] for m in fake_smtp.sent}
    assert subj["ann@example.test"] == f"[Portwerk] {wo['number']} suggested for confirmation – LLDP matches"
    assert subj["bea@example.test"] == f"[Portwerk] {wo['number']} zur Bestätigung vorgeschlagen – LLDP stimmt"


def test_assignment_mail_in_assignees_language(client, admin, lab, people, fake_smtp):  # noqa: F811
    uid = next(u["id"] for u in client.get("/api/users", headers=admin).json() if u["username"] == "ann")
    fake_smtp.sent.clear()
    r = client.post(f"/api/workorders/{lab['wo']['id']}/assign", headers=admin, json={"user_id": uid, "notify": True}).json()
    assert r["notified"]
    m = fake_smtp.sent[0]
    assert m["Subject"] == f"[Portwerk] Assigned to you: {lab['wo']['number']} Umbau Etage 2"
    assert f"admin assigned patch order {lab['wo']['number']} to you." in body(m) and "Items in the system (2):" in body(m)


def test_send_uses_senders_language_with_english_attachments(client, admin, lab, people, fake_smtp):  # noqa: F811
    set_lang(client, admin, "en")
    fake_smtp.sent.clear()
    r = client.post(f"/api/workorders/{lab['wo']['id']}/send", headers=admin, json={"emails": ["x@example.test"], "message": "", "include_list": True,
                                                                                  "attach_csv": True, "attach_pdf": True})
    assert r.status_code == 200, r.text
    m = fake_smtp.sent[0]
    assert m["Subject"] == f"[Portwerk] {lab['wo']['number']} Umbau Etage 2 (2 items)"
    txt = body(m)
    assert f"admin sent you patch order {lab['wo']['number']}." in txt and "Status: Draft" in txt and "Connect: sw-1:Gi1" in txt
    files = {p.get_filename(): p for p in m.iter_attachments()}
    csv_txt = files[f"{lab['wo']['number']}-worklist.csv"].get_content()
    assert "Cable number" in csv_txt and "Disconnect" in csv_txt
    pdf_txt = text_of(files[f"{lab['wo']['number']}-work-instruction.pdf"].get_payload(decode=True))
    assert f"Work instruction {lab['wo']['number']}" in pdf_txt and "Not approved yet" in pdf_txt


def test_pdf_and_csv_follow_requester_language(client, admin, lab):
    wid = lab["wo"]["id"]
    de = text_of(client.get(f"/api/workorders/{wid}/pdf", headers=admin).content)
    assert "Arbeitsanweisung" in de and "Unterschrift" in de and "Seite 1/" in de
    set_lang(client, admin, "en")
    r = client.get(f"/api/workorders/{wid}/pdf", headers=admin)
    assert f'{lab["wo"]["number"]}-work-instruction.pdf' in r.headers["content-disposition"]
    en = text_of(r.content)
    for s in (f"Work instruction {lab['wo']['number']}", "Signature", "Page 1/", "Deviations / remarks", "Created by", "Draft", "Remark"):
        assert s in en, (s, en)
    assert "Unterschrift" not in en
    csv_txt = client.get(f"/api/workorders/{wid}/export", headers=admin).text
    assert "Cable number" in csv_txt and "Connect" in csv_txt
    pl = text_of(client.get("/api/patchlists/pdf", headers=admin, params={"ids": str(wid)}).content)
    assert "Patch list" in pl and "Items" in pl


def test_cleanup_report_language(client, admin, people, fake_smtp):  # noqa: F811
    from app import cleanup, db
    db.execute("UPDATE users SET email = 'admin@example.test' WHERE username = 'admin'")
    set_lang(client, admin, "en")
    client.post("/api/devices", headers=admin, json={"hostname": "geplant-1", "type": "switch", "status": "planned"})
    fake_smtp.sent.clear()
    assert cleanup.weekly_mail(force=True) == 1
    m = fake_smtp.sent[0]
    assert m["Subject"].startswith("[Portwerk] Clean-up report:") and "Planned devices without an order: 1" in body(m)
