import pytest

from conftest import login


def mk(client, admin, user, scopes=(), roles=(), pw="Passwort-123"):
    r = client.post("/api/users", headers=admin, json={"username": user, "password": pw, "roles": list(roles),
                                                       "scopes": [{"role": r, "site_id": s} for r, s in scopes]})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture()
def world(client, admin):
    """Standort A und B, je ein Rack, zwei Geräte (A: sw-a, pp-a, B: sw-b), ein unplatziertes Gerät und ein Kabel A↔A, ein Kabel A↔B."""
    out = {}
    for code in ("A", "B"):
        s = client.post("/api/sites", headers=admin, json={"code": code, "name": f"Standort {code}"}).json()
        loc = client.post("/api/locations", headers=admin, json={"site_id": s["id"], "kind": "rack", "name": f"Rack-{code}", "rack_units": 42}).json()
        out[code] = {"site": s["id"], "loc": loc["id"]}
    def dev(name, code=None, **kw):
        body = {"hostname": name, **kw}
        if code:
            body["location_id"] = out[code]["loc"]
        d = client.post("/api/devices", headers=admin, json=body).json()
        ports = [client.post(f"/api/devices/{d['id']}/ports", headers=admin, json={"name": f"P{i}"}).json() for i in (1, 2)]
        return {"id": d["id"], "ports": [p["id"] for p in ports]}
    out["sw_a"], out["pp_a"], out["sw_b"], out["free"] = dev("sw-a", "A"), dev("pp-a", "A", type="patchpanel"), dev("sw-b", "B"), dev("lose")
    cab = lambda a, b: client.put(f"/api/ports/{a}/cable", headers=admin, json={"port_b_id": b, "cable_type": "Cat6", "cable_label": f"{a}-{b}"}).status_code  # noqa: E731
    assert cab(out["sw_a"]["ports"][0], out["pp_a"]["ports"][0]) == 200
    assert cab(out["sw_a"]["ports"][1], out["sw_b"]["ports"][0]) == 200                      # Strecke zwischen den Standorten
    return out


def hdr(client, admin, name, scopes, roles=()):
    mk(client, admin, name, scopes, roles)
    return login(client, name, "Passwort-123")


# ── Sichtbarkeit ──────────────────────────────────────────────────────────────

def test_scoped_user_sees_only_own_site(client, admin, world):
    h = hdr(client, admin, "va", [("viewer", world["A"]["site"])])
    assert [s["code"] for s in client.get("/api/sites", headers=h).json()] == ["A"]
    assert {l["name"] for l in client.get("/api/locations", headers=h).json()} == {"Rack-A"}
    names = {d["hostname"] for d in client.get("/api/devices", headers=h).json()["items"]}
    assert names == {"sw-a", "pp-a"}                                                     # kein sw-b, kein unplatziertes Gerät
    assert client.get(f"/api/devices/{world['sw_b']['id']}", headers=h).status_code == 404
    assert client.get(f"/api/devices/{world['free']['id']}", headers=h).status_code == 404
    assert client.get(f"/api/devices/{world['sw_b']['id']}/ports", headers=h).status_code == 404
    assert client.get(f"/api/devices?site_id={world['B']['site']}", headers=h).json()["total"] == 0
    assert client.get(f"/api/locations?site_id={world['B']['site']}", headers=h).json() == []
    # Kabel: beide aus A sichtbar, die Strecke A↔B ebenfalls (ein Ende im eigenen Bereich)
    assert len(client.get("/api/cables", headers=h).json()) == 2


def test_stats_are_scoped(client, admin, world):
    h = hdr(client, admin, "va", [("viewer", world["A"]["site"])])
    st = client.get("/api/stats", headers=h).json()
    assert st["scoped"] and st["sites"] == 1 and st["devices"] == 2 and st["racks"] == 1 and st["ports"] == 4
    assert st["devices_without_location"] == 0 and st["last_imports"] == []
    g = client.get("/api/stats", headers=admin).json()
    assert g["sites"] == 2 and g["devices"] == 4 and g["scoped"] is False


def test_global_viewer_sees_everything(client, admin, world):
    mk(client, admin, "gv", roles=("viewer",))
    h = login(client, "gv", "Passwort-123")
    assert len(client.get("/api/sites", headers=h).json()) == 2 and client.get("/api/devices", headers=h).json()["total"] == 4


def test_multiple_sites_and_no_scope_user(client, admin, world):
    h = hdr(client, admin, "vab", [("viewer", world["A"]["site"]), ("planer", world["B"]["site"])])
    assert [s["code"] for s in client.get("/api/sites", headers=h).json()] == ["A", "B"]
    me = client.get("/auth/me", headers=h).json()
    assert me["roles"] == [] and {(s["role"], s["site_code"]) for s in me["scopes"]} == {("viewer", "A"), ("planer", "B")}


# ── Schreiben ─────────────────────────────────────────────────────────────────

def test_site_admin_writes_only_in_own_site(client, admin, world):
    h = hdr(client, admin, "aa", [("admin", world["A"]["site"])])
    ok = client.post("/api/devices", headers=h, json={"hostname": "neu-a", "location_id": world["A"]["loc"]})
    assert ok.status_code == 201
    assert client.post("/api/devices", headers=h, json={"hostname": "neu-b", "location_id": world["B"]["loc"]}).status_code == 403
    assert client.post("/api/devices", headers=h, json={"hostname": "neu-x"}).status_code == 403              # ohne Location = kein Standort
    assert client.put(f"/api/devices/{world['sw_b']['id']}", headers=h, json={"hostname": "sw-b", "note": "x"}).status_code == 403
    assert client.put(f"/api/devices/{world['sw_a']['id']}", headers=h, json={"hostname": "sw-a", "location_id": world["B"]["loc"]}).status_code == 403   # Verschieben nach B
    assert client.delete(f"/api/devices/{world['sw_b']['id']}", headers=h).status_code == 403
    assert client.post("/api/locations", headers=h, json={"site_id": world["A"]["site"], "kind": "room", "name": "Raum"}).status_code == 201
    assert client.post("/api/locations", headers=h, json={"site_id": world["B"]["site"], "kind": "room", "name": "Raum"}).status_code == 403
    assert client.put(f"/api/sites/{world['A']['site']}", headers=h, json={"code": "A", "name": "Neu"}).status_code == 200
    assert client.put(f"/api/sites/{world['B']['site']}", headers=h, json={"code": "B", "name": "Neu"}).status_code == 403
    # global: keine neuen Standorte, kein Katalog, kein Import, keine Verwaltung
    assert client.post("/api/sites", headers=h, json={"code": "C", "name": "C"}).status_code == 403
    assert client.post("/api/device-models", headers=h, json={"model": "X"}).status_code == 403
    assert client.post("/api/import/json", headers=h, json={"devices": []}).status_code == 403
    assert client.get("/api/admin/ldap", headers=h).status_code == 403
    assert client.get("/api/tokens", headers=h).status_code == 403
    assert client.get("/api/audit", headers=h).status_code == 403


def test_cables_need_both_ends_in_scope(client, admin, world):
    h = hdr(client, admin, "aa", [("admin", world["A"]["site"])])
    a, b = world["sw_a"]["ports"], world["pp_a"]["ports"]
    assert client.put(f"/api/ports/{a[0]}/cable", headers=h, json={"port_b_id": b[1], "cable_type": "Cat6"}).status_code == 200
    assert client.put(f"/api/ports/{a[0]}/cable", headers=h, json={"port_b_id": world["sw_b"]["ports"][1], "cable_type": "Cat6"}).status_code == 403
    assert client.put(f"/api/ports/{a[0]}/cable", headers=h, json={"port_b_id": None, "cable_type": "Cat6"}).status_code == 200   # lösen genügt im eigenen Bereich
    assert client.put(f"/api/ports/{world['sw_b']['ports'][1]}/cable", headers=h, json={"port_b_id": None, "cable_type": "Cat6"}).status_code == 403


def test_scoped_viewer_and_planer_cannot_edit_masterdata(client, admin, world):
    for role in ("viewer", "planer", "techniker"):
        h = hdr(client, admin, f"u-{role}", [(role, world["A"]["site"])])
        r = client.post("/api/devices", headers=h, json={"hostname": f"x-{role}", "location_id": world["A"]["loc"]})
        assert r.status_code == 403, role


# ── Patchaufträge ─────────────────────────────────────────────────────────────

def test_workorders_scoped_by_site_and_roles(client, admin, world):
    A, B = world["A"], world["B"]
    pa = hdr(client, admin, "pa", [("planer", A["site"])])
    ta = hdr(client, admin, "ta", [("techniker", A["site"])])
    fa = hdr(client, admin, "fa", [("freigeber", A["site"])])
    pb = hdr(client, admin, "pb", [("planer", B["site"])])
    # Anlegen nur für Locations des eigenen Standorts
    assert client.post("/api/workorders", headers=pa, json={"title": "ohne Ort"}).status_code == 403
    assert client.post("/api/workorders", headers=pa, json={"title": "in B", "location_id": B["loc"]}).status_code == 403
    wo = client.post("/api/workorders", headers=pa, json={"title": "in A", "location_id": A["loc"]})
    assert wo.status_code == 201, wo.text
    wid = wo.json()["id"]
    # Positionen: nur Ports aus A
    free_a = client.post(f"/api/devices/{world['sw_a']['id']}/ports", headers=admin, json={"name": "P3"}).json()["id"]      # freie Ports: sonst Rückfrage „alten Patch zurückbauen?“
    free_b = client.post(f"/api/devices/{world['pp_a']['id']}/ports", headers=admin, json={"name": "P3"}).json()["id"]
    ok = client.post(f"/api/workorders/{wid}/items", headers=pa, json={"action": "connect", "port_a_id": free_a, "port_b_id": free_b, "cable_type": "Cat6"})
    assert ok.status_code == 201, ok.text
    bad = client.post(f"/api/workorders/{wid}/items", headers=pa, json={"action": "connect", "port_a_id": free_a, "port_b_id": world["sw_b"]["ports"][1], "cable_type": "Cat6"})
    assert bad.status_code == 403
    # Sichtbarkeit
    assert [w["id"] for w in client.get("/api/workorders", headers=ta).json()] == [wid]
    assert client.get("/api/workorders", headers=pb).json() == []
    assert client.get(f"/api/workorders/{wid}", headers=pb).status_code == 404
    assert client.post(f"/api/workorders/{wid}/transition/submit", headers=pb).status_code == 404
    # Rollenwechsel am Standort A
    assert client.post(f"/api/workorders/{wid}/transition/submit", headers=pa).status_code == 200
    assert client.post(f"/api/workorders/{wid}/transition/approve", headers=pa).status_code == 403      # Planer ist kein Freigeber
    assert client.post(f"/api/workorders/{wid}/transition/approve", headers=fa).status_code == 200
    assert client.post(f"/api/workorders/{wid}/transition/start", headers=fa).status_code == 403
    assert client.post(f"/api/workorders/{wid}/transition/start", headers=ta).status_code == 200


def test_planer_role_does_not_leak_between_sites(client, admin, world):
    A, B = world["A"], world["B"]
    h = hdr(client, admin, "mix", [("planer", A["site"]), ("viewer", B["site"])])
    assert client.post("/api/workorders", headers=h, json={"title": "B", "location_id": B["loc"]}).status_code == 403   # in B nur Betrachter
    assert client.post("/api/workorders", headers=h, json={"title": "A", "location_id": A["loc"]}).status_code == 201


# ── Benutzerverwaltung: delegiert ─────────────────────────────────────────────

def test_site_admin_manages_users_of_own_area_only(client, admin, world):
    A, B = world["A"]["site"], world["B"]["site"]
    aa = hdr(client, admin, "aa", [("admin", A)])
    mk(client, admin, "xa", [("viewer", A)])
    mk(client, admin, "xb", [("viewer", B)])
    mk(client, admin, "xab", [("viewer", A), ("planer", B)])
    mk(client, admin, "glob", roles=("viewer",))
    names = {u["username"] for u in client.get("/api/users", headers=aa).json()}
    assert names == {"aa", "xa", "xab"}                                                   # nur Benutzer mit Zuweisung in A
    xab = [u for u in client.get("/api/users", headers=aa).json() if u["username"] == "xab"][0]
    assert [s["site_code"] for s in xab["scopes"]] == ["A"] and xab["limited"] is True    # fremde Standorte werden nicht gezeigt
    uid = {u["username"]: u["id"] for u in client.get("/api/users", headers=admin).json()}
    assert client.put(f"/api/users/{uid['xb']}", headers=aa, json={"full_name": "x"}).status_code == 404

    # anlegen: nur Rechte für eigene Standorte, keine globalen Rollen
    new = lambda **kw: client.post("/api/users", headers=aa, json={"username": kw.pop("u"), "password": "Passwort-123", **kw})  # noqa: E731
    assert new(u="n1", roles=[], scopes=[{"role": "techniker", "site_id": A}]).status_code == 201
    assert new(u="n2", roles=[], scopes=[{"role": "viewer", "site_id": B}]).status_code == 403
    assert new(u="n3", roles=["viewer"], scopes=[]).status_code == 403
    assert new(u="n4", roles=[], scopes=[]).status_code == 400
    # Rechte setzen: ersetzt nur im eigenen Bereich, fremde bleiben
    r = client.put(f"/api/users/{uid['xab']}", headers=aa, json={"scopes": [{"role": "freigeber", "site_id": A}]})
    assert r.status_code == 200, r.text
    full = [u for u in client.get("/api/users", headers=admin).json() if u["username"] == "xab"][0]
    assert {(s["role"], s["site_code"]) for s in full["scopes"]} == {("freigeber", "A"), ("planer", "B")}
    assert client.put(f"/api/users/{uid['xa']}", headers=aa, json={"scopes": [{"role": "viewer", "site_id": B}]}).status_code == 403
    # Sperren/Passwort/Löschen nur bei Benutzern, die ganz im eigenen Bereich liegen
    assert client.put(f"/api/users/{uid['xab']}", headers=aa, json={"active": False}).status_code == 403
    assert client.post(f"/api/users/{uid['xab']}/reset-password", headers=aa, json={"new_password": "Neues-Passwort-1"}).status_code == 403
    assert client.delete(f"/api/users/{uid['xab']}", headers=aa).status_code == 403
    assert client.put(f"/api/users/{uid['xa']}", headers=aa, json={"active": False}).status_code == 200
    assert client.post(f"/api/users/{uid['xa']}/reset-password", headers=aa, json={"new_password": "Neues-Passwort-1"}).status_code == 200
    assert client.delete(f"/api/users/{uid['xa']}", headers=aa).status_code == 200
    # keine Rechteausweitung: globale Rolle für sich selbst, API-Zugänge, Verwaltung
    assert client.put(f"/api/users/{uid['aa']}", headers=aa, json={"roles": ["admin"]}).status_code == 403
    assert client.get("/api/tokens", headers=aa).status_code == 403


def test_global_admin_assigns_scopes_and_guard(client, admin, world):
    A, B = world["A"]["site"], world["B"]["site"]
    u = mk(client, admin, "m1", [("viewer", A)])
    r = client.put(f"/api/users/{u['id']}", headers=admin, json={"scopes": [{"role": "planer", "site_id": B}], "roles": ["viewer"]})
    assert r.status_code == 200 and r.json()["roles"] == ["viewer"] and [s["site_code"] for s in r.json()["scopes"]] == ["B"]
    assert client.put(f"/api/users/{u['id']}", headers=admin, json={"scopes": [{"role": "boss", "site_id": A}]}).status_code == 400
    assert client.put(f"/api/users/{u['id']}", headers=admin, json={"scopes": [{"role": "viewer", "site_id": 999}]}).status_code == 400
    # ein lokaler Benutzer ohne jede Berechtigung ist nicht erlaubt
    assert client.put(f"/api/users/{u['id']}", headers=admin, json={"roles": [], "scopes": []}).status_code == 400
    assert client.post("/api/users", headers=admin, json={"username": "leer", "password": "Passwort-123", "roles": [], "scopes": []}).status_code == 400
    # Standort löschen entfernt die Zuweisung
    client.delete(f"/api/sites/{B}", headers=admin)
    assert client.get("/auth/me", headers=login(client, "m1", "Passwort-123")).json()["scopes"] == []


def test_scope_changes_apply_immediately(client, admin, world):
    A, B = world["A"]["site"], world["B"]["site"]
    u = mk(client, admin, "live", [("viewer", A)])
    h = login(client, "live", "Passwort-123")
    assert [s["code"] for s in client.get("/api/sites", headers=h).json()] == ["A"]
    client.put(f"/api/users/{u['id']}", headers=admin, json={"scopes": [{"role": "viewer", "site_id": B}]})
    h2 = login(client, "live", "Passwort-123")
    assert [s["code"] for s in client.get("/api/sites", headers=h2).json()] == ["B"]


# ── AD-Gruppen -> Standort-Rechte ─────────────────────────────────────────────

def test_ldap_scoped_groups(client, admin, world, monkeypatch):
    from app import ldap_auth
    import test_ldap
    A = world["A"]["site"]
    test_ldap.USERS["scop"] = {"dn": "CN=Scop,OU=U,DC=example,DC=test", "display": "Scoped", "mail": "",
                               "groups": ["CN=Site-A-Admins,OU=G,DC=example,DC=test"]}
    test_ldap.USERS["nobody"] = {"dn": "CN=Nobody,OU=U,DC=example,DC=test", "display": "Niemand", "mail": "", "groups": []}
    monkeypatch.setattr(ldap_auth, "_open_one",
                        lambda cfg, url, user, pw: (test_ldap._Conn(), None, "") if pw == "gut" else (None, "invalid", "bad"))
    r = client.put("/api/admin/ldap", headers=admin, json={
        "enabled": True, "url": "ldaps://dc1.example.test", "base_dn": "DC=example,DC=test", "domain": "example.test", "default_role": "viewer",
        "scoped_groups": [{"group": "CN=Site-A-Admins,OU=G,DC=example,DC=test", "role": "admin", "site_id": A}]})
    assert r.status_code == 200, r.text
    assert client.put("/api/admin/ldap", headers=admin, json={"scoped_groups": [{"group": "x", "role": "admin", "site_id": 999}]}).status_code == 422
    assert client.put("/api/admin/ldap", headers=admin, json={"scoped_groups": [{"group": "x", "role": "boss", "site_id": A}]}).status_code == 422
    try:
        lg = client.post("/auth/login", json={"username": "scop", "password": "gut"})
        assert lg.status_code == 200, lg.text
        u = lg.json()["user"]
        assert u["roles"] == [] and [(s["role"], s["site_code"], s["source"]) for s in u["scopes"]] == [("admin", "A", "ldap")]   # Standardrolle gilt nicht zusätzlich
        h = {"X-Auth-Token": lg.json()["token"]}
        assert [s["code"] for s in client.get("/api/sites", headers=h).json()] == ["A"]
        assert client.post("/api/devices", headers=h, json={"hostname": "ad-neu", "location_id": world["A"]["loc"]}).status_code == 201
        # Gruppe entfällt -> Standort-Recht weg (Standardrolle viewer greift jetzt global)
        test_ldap.USERS["scop"]["groups"] = []
        lg2 = client.post("/auth/login", json={"username": "scop", "password": "gut"}).json()
        assert lg2["user"]["scopes"] == [] and lg2["user"]["roles"] == ["viewer"]
        assert client.get("/auth/me", headers=h).status_code == 401                                   # alte Sitzung mit alten Rechten beendet
        # Benutzer ohne Gruppe bekommt ohne Standardrolle ein Konto ohne Rechte (Anmeldung ja, Hinweis zur Freischaltung)
        client.put("/api/admin/ldap", headers=admin, json={"default_role": ""})
        nb = client.post("/auth/login", json={"username": "nobody", "password": "gut"})
        assert nb.status_code == 200 and nb.json()["user"]["roles"] == [] and nb.json()["user"]["scopes"] == []
    finally:
        test_ldap.USERS.pop("scop", None)
        test_ldap.USERS.pop("nobody", None)


def test_manual_scope_survives_ldap_login(client, admin, world, monkeypatch):
    from app import ldap_auth
    import test_ldap
    A = world["A"]["site"]
    monkeypatch.setattr(ldap_auth, "_open_one",
                        lambda cfg, url, user, pw: (test_ldap._Conn(), None, "") if pw == "gut" else (None, "invalid", "bad"))
    client.put("/api/admin/ldap", headers=admin, json={"enabled": True, "url": "ldaps://dc1.example.test", "base_dn": "DC=example,DC=test",
                                                       "domain": "example.test", "default_role": "viewer"})
    assert client.post("/auth/login", json={"username": "nogr", "password": "gut"}).json()["user"]["roles"] == ["viewer"]
    uid = [u for u in client.get("/api/users", headers=admin).json() if u["username"] == "nogr"][0]["id"]
    # Admin trägt manuell Standort-Recht ein und nimmt die globale Rolle weg
    client.put(f"/api/users/{uid}", headers=admin, json={"roles": [], "scopes": [{"role": "planer", "site_id": A}]})
    lg = client.post("/auth/login", json={"username": "nogr", "password": "gut"}).json()["user"]
    assert lg["roles"] == [] and [(s["role"], s["source"]) for s in lg["scopes"]] == [("planer", "manual")]   # Standardrolle greift nicht mehr
