"""Audit-Log: Suche, Filter, Nachladen und Auswahllisten."""
import time

from conftest import login, make_user


def entries(client, admin, **params):
    r = client.get("/api/audit", headers=admin, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def seed(client, admin):
    make_user(client, admin, "audit-anna", roles=("planer",))
    make_user(client, admin, "audit-ben", roles=("viewer",))
    client.post("/auth/login", json={"username": "audit-anna", "password": "falsch"})                 # auth.login_failed
    login(client, "audit-ben", "Passwort-123")                                                      # auth.login


def test_free_text_search_matches_every_word(client, admin):
    seed(client, admin)
    assert entries(client, admin, q="audit-anna")                                                       # Benutzer / Detail
    both = entries(client, admin, q="audit-anna user.create")
    assert both and all("audit-anna" in (e["actor"] + e["detail"] + e["entity_id"]) and e["action"] == "user.create" for e in both)
    assert entries(client, admin, q="audit-anna gibtesnicht") == []                                     # jedes Wort muss vorkommen


def test_filters_by_actor_action_prefix_and_entity(client, admin):
    seed(client, admin)
    assert {e["actor"] for e in entries(client, admin, actor="audit-ben")} == {"audit-ben"}
    auth_rows = entries(client, admin, action="auth")                                                   # Präfix
    assert auth_rows and all(e["action"].startswith("auth.") for e in auth_rows)
    assert {e["action"] for e in entries(client, admin, action="auth.login_failed")} == {"auth.login_failed"}
    assert all(e["entity"] == "user" for e in entries(client, admin, entity="user"))


def test_like_wildcards_are_literal(client, admin):
    seed(client, admin)
    assert entries(client, admin, q="%") == [] and entries(client, admin, action="%") == []
    under = entries(client, admin, q="_")                                                              # „_“ ist kein Platzhalter, sondern ein echtes Zeichen (z. B. in auth.login_failed)
    assert under and all("_" in (e["actor"] + e["action"] + e["entity"] + e["entity_id"] + e["detail"]) for e in under)


def test_date_range_and_validation(client, admin):
    seed(client, admin)
    today = time.strftime("%Y-%m-%d")
    yesterday = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400))
    assert entries(client, admin, date_from=today, date_to=today)                                       # heute eingeschlossen
    assert entries(client, admin, date_to=yesterday) == []
    assert entries(client, admin, date_from=time.strftime("%Y-%m-%d", time.localtime(time.time() + 86400))) == []
    assert client.get("/api/audit", headers=admin, params={"date_from": "gestern"}).status_code == 400


def test_paging_with_offset_and_limit(client, admin):
    seed(client, admin)
    first = entries(client, admin, limit=3)
    nxt = entries(client, admin, limit=3, offset=3)
    assert len(first) == 3 and nxt and not ({e["id"] for e in first} & {e["id"] for e in nxt})
    assert first[0]["id"] > first[-1]["id"] > nxt[0]["id"]                                              # neueste zuerst


def test_facets_and_admin_only(client, admin):
    seed(client, admin)
    f = client.get("/api/audit/facets", headers=admin).json()
    assert {"audit-anna", "audit-ben", "admin"} <= set(f["actors"])
    assert {"auth.login", "auth.login_failed", "user.create"} <= set(f["actions"]) and "user" in f["entities"]
    viewer = login(client, "audit-ben", "Passwort-123")
    assert client.get("/api/audit", headers=viewer).status_code == 403 and client.get("/api/audit/facets", headers=viewer).status_code == 403
