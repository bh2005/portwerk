from conftest import ADMIN_PW, login, make_token, make_user


def test_seed_admin_login_and_me(client):
    assert client.post("/auth/login", json={"username": "admin", "password": "falsch"}).status_code == 401
    h = login(client)
    me = client.get("/auth/me", headers=h).json()
    assert me["kind"] == "user" and me["username"] == "admin" and me["roles"] == ["admin"] and "password_hash" not in me
    assert client.get("/auth/me").status_code == 401


def test_logout_invalidates_session(client, admin):
    assert client.post("/auth/logout", headers=admin).status_code == 200
    assert client.get("/auth/me", headers=admin).status_code == 401


def test_roles_validation_and_viewer_is_read_only(client, admin, site):
    assert client.post("/api/users", headers=admin, json={"username": "x", "password": "Passwort-123", "roles": ["chef"]}).status_code == 400
    assert client.post("/api/users", headers=admin, json={"username": "x y", "password": "Passwort-123"}).status_code == 400
    assert client.post("/api/users", headers=admin, json={"username": "kurz", "password": "abc"}).status_code == 400
    make_user(client, admin, "v1", ["viewer"])
    make_user(client, admin, "p1", ["planer"])
    v = login(client, "v1", "Passwort-123")
    assert client.get("/api/sites", headers=v).status_code == 200                      # Lesen erlaubt
    assert client.post("/api/sites", headers=v, json={"code": "X", "name": "X"}).status_code == 403
    assert client.get("/api/users", headers=v).status_code == 403
    assert client.post("/api/sites", headers=login(client, "p1", "Passwort-123"), json={"code": "Y", "name": "Y"}).status_code == 403   # Planer ändert keine Stammdaten


def test_duplicate_user_case_insensitive(client, admin):
    make_user(client, admin, "Dup")
    assert client.post("/api/users", headers=admin, json={"username": "DUP", "password": "Passwort-123"}).status_code == 409


def test_last_admin_is_protected(client, admin):
    uid = client.get("/auth/me", headers=admin).json()["id"]
    assert client.put(f"/api/users/{uid}", headers=admin, json={"active": False}).status_code == 400
    assert client.put(f"/api/users/{uid}", headers=admin, json={"roles": ["viewer"]}).status_code == 400
    assert client.delete(f"/api/users/{uid}", headers=admin).status_code == 400
    second = make_user(client, admin, "admin2", ["admin", "planer"])
    assert client.put(f"/api/users/{uid}", headers=admin, json={"roles": ["viewer"]}).status_code == 200     # jetzt erlaubt


def test_role_change_ends_sessions(client, admin):
    u = make_user(client, admin, "worker", ["viewer"])
    h = login(client, "worker", "Passwort-123")
    assert client.get("/auth/me", headers=h).status_code == 200
    client.put(f"/api/users/{u['id']}", headers=admin, json={"roles": ["techniker"]})
    assert client.get("/auth/me", headers=h).status_code == 401


def test_change_password_keeps_own_session_ends_others(client, admin):
    other = login(client)
    r = client.post("/auth/change-password", headers=admin, json={"current_password": ADMIN_PW, "new_password": "Neues-Passwort-9"})
    assert r.status_code == 200
    assert client.get("/auth/me", headers=other).status_code == 401                      # andere Sitzung beendet
    assert client.get("/auth/me", headers={"X-Auth-Token": r.json()["token"]}).status_code == 200
    assert client.post("/auth/change-password", headers={"X-Auth-Token": r.json()["token"]},
                       json={"current_password": "falsch", "new_password": "Noch-ein-Passwort"}).status_code == 401
    assert client.post("/auth/login", json={"username": "admin", "password": "Neues-Passwort-9"}).status_code == 200


def test_api_tokens_scopes(client, admin, site):
    read = make_token(client, admin, "read", "nur-lesen")
    write = make_token(client, admin, "write", "schreiben")
    assert client.get("/api/sites", headers=read).status_code == 200
    assert client.post("/api/sites", headers=read, json={"code": "B", "name": "B"}).status_code == 403
    assert client.post("/api/sites", headers=write, json={"code": "B", "name": "B"}).status_code == 201
    assert client.get("/api/users", headers=write).status_code == 403                    # ein Token verwaltet nie Benutzer
    assert client.post("/api/tokens", headers=write, json={"name": "x"}).status_code == 403
    assert client.get("/auth/me", headers=write).json() == {"kind": "token", "name": "schreiben", "scope": "write", "areas": []}
    assert client.get("/api/sites", headers={"X-API-Key": write["Authorization"][7:]}).status_code == 200
    assert client.get("/api/sites", headers={"Authorization": "Bearer opp_falsch"}).status_code == 401


def test_token_secret_shown_once_and_revocable(client, admin):
    r = client.post("/api/tokens", headers=admin, json={"name": "einmal", "scope": "read"}).json()
    assert r["token"].startswith("opp_")
    listed = client.get("/api/tokens", headers=admin).json()[0]
    assert "token" not in listed and listed["prefix"] == r["token"][:10]
    h = {"Authorization": "Bearer " + r["token"]}
    assert client.get("/api/sites", headers=h).status_code == 200
    assert client.delete(f"/api/tokens/{r['id']}", headers=admin).status_code == 200
    assert client.get("/api/sites", headers=h).status_code == 401


def test_audit_records_admin_actions(client, admin):
    make_user(client, admin, "audited")
    log = client.get("/api/audit", headers=admin).json()
    actions = [e["action"] for e in log]
    assert "user.create" in actions and "auth.login" in actions
    assert client.get("/api/audit", headers=login(client, "audited", "Passwort-123")).status_code == 403
