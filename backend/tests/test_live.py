"""Änderungs-Revision (GET /api/live): nur Änderungen **anderer** zählen, Fehlschläge und Lesezugriffe nicht."""
from conftest import ADMIN_PW, login, make_token, make_user  # noqa: F401


def live(client, hdr):
    r = client.get("/api/live", headers=hdr)
    assert r.status_code == 200, r.text
    return r.json()


def test_others_changes_are_signalled_own_are_not(client, admin):
    make_user(client, admin, "anna", roles=("admin",), pw="Passwort-123")
    anna = login(client, "anna", "Passwort-123")
    base_admin, base_anna = live(client, admin)["others"], live(client, anna)["others"]
    # admin legt einen Standort an → Anna sieht eine fremde Änderung, admin nicht
    r = client.post("/api/sites", headers=admin, json={"code": "LIVE-1", "name": "Live 1"})
    assert r.status_code == 201
    a, b = live(client, admin), live(client, anna)
    assert a["others"] == base_admin                                   # eigene Änderung zählt für einen selbst nicht
    assert b["others"] > base_anna and b["by"] == "admin" and b["at"]
    # umgekehrt
    assert client.post("/api/sites", headers=anna, json={"code": "LIVE-2", "name": "Live 2"}).status_code == 201
    assert live(client, admin)["others"] > a["others"] and live(client, admin)["by"] == "anna"


def test_reads_failures_and_login_do_not_count(client, admin):
    make_user(client, admin, "bea", roles=("admin",), pw="Passwort-123")
    bea = login(client, "bea", "Passwort-123")
    start = live(client, bea)
    client.get("/api/sites", headers=admin)                                                   # Lesen
    assert client.post("/api/sites", headers=admin, json={"code": "", "name": ""}).status_code >= 400   # Fehlschlag
    login(client, "admin", ADMIN_PW)                                                          # Anmeldung
    assert live(client, bea)["others"] == start["others"]


def test_api_token_changes_are_signalled(client, admin):
    tok = make_token(client, admin, scope="write", name="checkmk-import")
    before = live(client, admin)["others"]
    r = client.post("/api/sites", headers=tok, json={"code": "TOK-1", "name": "Per Token"})
    assert r.status_code == 201, r.text
    after = live(client, admin)
    assert after["others"] > before and after["by"] == "checkmk-import"


def test_live_needs_login_and_users_only(client, admin):
    assert client.get("/api/live").status_code == 401
    tok = make_token(client, admin, scope="read", name="nur-lesen")
    assert client.get("/api/live", headers=tok).status_code == 403
