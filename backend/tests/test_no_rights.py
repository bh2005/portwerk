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
