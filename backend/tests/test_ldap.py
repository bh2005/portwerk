import pytest

from conftest import make_user, login

USERS = {
    "max":  {"dn": "CN=Max,OU=U,DC=example,DC=test", "display": "Max Muster", "mail": "max@example.test",
             "groups": ["CN=OPP-Planer,OU=G,DC=example,DC=test"]},
    "adm":  {"dn": "CN=Adm,OU=U,DC=example,DC=test", "display": "Ada Admin", "mail": "",
             "groups": ["CN=OPP-Admin,OU=G,DC=example,DC=test", "CN=OPP-Planer,OU=G,DC=example,DC=test"]},
    "nogr": {"dn": "CN=NoGr,OU=U,DC=example,DC=test", "display": "Ohne Gruppe", "mail": "", "groups": []},
    "admin": {"dn": "CN=Ad,OU=U,DC=example,DC=test", "display": "Gleichnamig", "mail": "", "groups": []},
}


class _Val:
    def __init__(self, v):
        self.value = v


class _Entry:
    def __init__(self, dn, u):
        self.entry_dn = dn
        self._a = {"sAMAccountName": u["sam"], "displayName": u["display"], "mail": u["mail"] or None, "memberOf": u["groups"]}
        self.entry_attributes = [k for k, v in self._a.items() if v is not None]

    def __getitem__(self, k):
        return _Val(self._a[k])


class _Conn:
    def __init__(self):
        self.entries = []

    def search(self, base, flt, attributes=None, size_limit=0):
        import re
        if "memberOf:" in flt:                                  # verschachtelte Gruppen: Treffer, wenn Gruppe in den (simulierten) Gruppen
            dn = re.search(r"distinguishedName=(.+?)\)\(memberOf", flt).group(1)
            grp = re.search(r":=(.+?)\)\)$", flt).group(1)
            hit = [u for u in USERS.values() if u["dn"] == dn and grp in u["groups"] + u.get("nested", [])]
            self.entries = [_Entry(dn, {**hit[0], "sam": "x"})] if hit else []
            return
        sam = re.search(r"sAMAccountName=([^)]+)", flt).group(1)
        u = USERS.get(sam)
        self.entries = [_Entry(u["dn"], {**u, "sam": sam})] if u else []

    def unbind(self):
        pass


@pytest.fixture()
def ad(client, admin, monkeypatch):
    """Simuliertes Verzeichnis: Passwort für alle Benutzer ist „gut“."""
    from app import ldap_auth

    def fake_open(cfg, url, user, password):
        if url.startswith("ldaps://down"):
            return None, "unavailable", "Server nicht erreichbar"
        return (_Conn(), None, "") if password == "gut" else (None, "invalid", "invalidCredentials")
    monkeypatch.setattr(ldap_auth, "_open_one", fake_open)
    r = client.put("/api/admin/ldap", headers=admin, json={
        "enabled": True, "url": "ldaps://dc1.example.test", "base_dn": "DC=example,DC=test", "domain": "example.test",
        "group_roles": {"admin": "CN=OPP-Admin,OU=G,DC=example,DC=test", "planer": "CN=OPP-Planer,OU=G,DC=example,DC=test"},
        "default_role": "viewer"})
    assert r.status_code == 200, r.text
    return ldap_auth


def ldap_login(client, user, pw="gut"):
    return client.post("/auth/login", json={"username": user, "password": pw})


def test_ldap_is_off_by_default_and_local_login_unaffected(client, admin):
    s = client.get("/api/admin/ldap", headers=admin).json()
    assert s["enabled"] is False and s["url"] == "" and s["bind_password_set"] is False and "bind_password" not in s
    assert ldap_login(client, "max").status_code == 401
    assert login(client)


def test_settings_validation_and_secret_never_returned(client, admin):
    put = lambda **kw: client.put("/api/admin/ldap", headers=admin, json=kw)  # noqa: E731
    assert put(enabled=True).status_code == 422                                    # URL fehlt
    assert put(enabled=True, url="dc1.example.test").status_code == 422            # Schema fehlt
    assert put(enabled=True, url="ldaps://dc", base_dn="DC=x").status_code == 422  # weder Domain noch Bind-DN
    assert put(user_filter="(cn=x)").status_code == 422                            # {username} fehlt
    assert put(default_role="admin").status_code == 422                            # keine Admin-Standardrolle
    assert put(ca_pem="nope").status_code == 422
    ok = put(url="ldaps://dc", base_dn="DC=x", bind_dn="CN=svc", bind_password="geheim").json()
    assert ok["bind_password_set"] is True and "geheim" not in str(ok)
    keep = put(url="ldaps://dc2").json()                                           # leeres/fehlendes Passwort lässt es unverändert
    assert keep["bind_password_set"] is True
    assert put(clear_bind_password=True).json()["bind_password_set"] is False


def test_first_login_creates_user_with_roles_from_groups(client, admin, ad):
    r = ldap_login(client, "max")
    assert r.status_code == 200, r.text
    u = r.json()["user"]
    assert u["source"] == "ldap" and u["roles"] == ["planer"] and u["full_name"] == "Max Muster" and u["email"] == "max@example.test"
    me = client.get("/auth/me", headers={"X-Auth-Token": r.json()["token"]}).json()
    assert me["username"] == "max"
    a = ldap_login(client, "adm@example.test").json()["user"]                      # UPN-Eingabe funktioniert ebenfalls
    assert a["roles"] == ["admin", "planer"]


def test_default_role_and_deny_without_group(client, admin, ad):
    assert ldap_login(client, "nogr").json()["user"]["roles"] == ["viewer"]
    client.put("/api/admin/ldap", headers=admin, json={"default_role": ""})
    assert ldap_login(client, "nogr").status_code == 401       # ohne passende Gruppe und ohne Standardrolle: kein Zugang (auch nicht für bestehende Konten)
    assert ldap_login(client, "max").status_code == 200        # mit Gruppe weiterhin


def test_roles_sync_on_every_login_and_old_sessions_end(client, admin, ad):
    t1 = ldap_login(client, "max").json()["token"]
    USERS["max"]["groups"] = ["CN=OPP-Admin,OU=G,DC=example,DC=test"]
    try:
        r = ldap_login(client, "max")
        assert r.json()["user"]["roles"] == ["admin"]
        assert client.get("/auth/me", headers={"X-Auth-Token": t1}).status_code == 401   # Sitzung mit alten Rollen beendet
    finally:
        USERS["max"]["groups"] = ["CN=OPP-Planer,OU=G,DC=example,DC=test"]


def test_wrong_password_and_down_server(client, admin, ad):
    assert ldap_login(client, "max", "falsch").status_code == 401
    assert client.get("/api/users", headers=admin).json()[0]["username"] == "admin"
    client.put("/api/admin/ldap", headers=admin, json={"url": "ldaps://down1 ldaps://dc2.example.test"})
    assert ldap_login(client, "max").status_code == 200                            # Ausfallsicherung: zweiter Server
    client.put("/api/admin/ldap", headers=admin, json={"url": "ldaps://down1"})
    assert ldap_login(client, "max").status_code == 401


def test_local_accounts_stay_local_and_are_not_hijacked(client, admin, ad):
    assert ldap_login(client, "admin", "gut").status_code == 401                   # Verzeichnis kennt „admin“, lokal gilt nur das lokale Passwort
    assert login(client)                                                           # lokaler Admin geht weiter


def test_disabled_ldap_user_and_no_auto_create(client, admin, ad):
    ldap_login(client, "max")
    uid = [u for u in client.get("/api/users", headers=admin).json() if u["username"] == "max"][0]["id"]
    client.put(f"/api/users/{uid}", headers=admin, json={"active": False})
    assert ldap_login(client, "max").status_code == 401
    client.put("/api/admin/ldap", headers=admin, json={"auto_create": False})
    assert ldap_login(client, "adm").status_code == 401                            # nicht angelegt, Auto-Anlage aus


def test_required_group(client, admin, ad):
    client.put("/api/admin/ldap", headers=admin, json={"required_group": "CN=OPP-Planer,OU=G,DC=example,DC=test"})
    assert ldap_login(client, "max").status_code == 200
    assert ldap_login(client, "nogr").status_code == 401


def test_ldap_users_cannot_change_password_and_test_endpoint(client, admin, ad):
    tok = ldap_login(client, "max").json()["token"]
    r = client.post("/auth/change-password", headers={"X-Auth-Token": tok}, json={"current_password": "gut", "new_password": "NeuesPasswort-1"})
    assert r.status_code == 400
    t = client.post("/api/admin/ldap/test", headers=admin, json={"username": "adm", "password": "gut"}).json()
    assert t["ok"] and t["user"]["roles"] == ["admin", "planer"] and any(s["step"] == "Gruppen des Benutzers" for s in t["steps"])
    bad = client.post("/api/admin/ldap/test", headers=admin, json={"username": "adm", "password": "x"}).json()
    assert bad["ok"] is False
    # ungespeicherte Formularwerte werden getestet
    t2 = client.post("/api/admin/ldap/test", headers=admin, json={"settings": {"url": "ldaps://down1"}, "username": "adm", "password": "gut"}).json()
    assert t2["ok"] is False
    make_user(client, admin, "v1", roles=("viewer",))
    h = login(client, "v1", "Passwort-123")
    assert client.get("/api/admin/ldap", headers=h).status_code == 403


def test_manual_roles_persist_when_no_groups_are_mapped(client, admin, ad):
    """Ohne Gruppen-Zuordnung liefert das Verzeichnis nur die Anmeldung; vom Administrator vergebene Rollen bleiben nach dem Login erhalten."""
    client.put("/api/admin/ldap", headers=admin, json={"group_roles": {"admin": "", "planer": ""}, "default_role": "viewer"})
    assert ldap_login(client, "nogr").json()["user"]["roles"] == ["viewer"]                       # neues Konto: Standardrolle
    uid = [u for u in client.get("/api/users", headers=admin).json() if u["username"] == "nogr"][0]["id"]
    assert client.put(f"/api/users/{uid}", headers=admin, json={"roles": ["admin"]}).status_code == 200
    r = ldap_login(client, "nogr")
    assert r.status_code == 200 and r.json()["user"]["roles"] == ["admin"]                       # nicht wieder auf „viewer“ gesetzt
    # sobald Gruppen zugeordnet sind, bestimmt das Verzeichnis die Rollen wieder bei jeder Anmeldung
    client.put("/api/admin/ldap", headers=admin, json={"group_roles": {"admin": "CN=OPP-Admin,OU=G,DC=example,DC=test", "planer": ""}})
    assert ldap_login(client, "nogr").json()["user"]["roles"] == ["viewer"]
