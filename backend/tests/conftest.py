import os
import sys
import tempfile

import pytest

_TMP = tempfile.mkdtemp(prefix="opp-test-")
os.environ["OPP_DATA_DIR"] = _TMP
os.environ["OPP_ADMIN_USERNAME"] = "admin"
os.environ["OPP_ADMIN_PASSWORD"] = "Start-Passwort-1"
os.environ["OPP_BACKUP_BACKGROUND"] = "0"
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

ADMIN_PW = "Start-Passwort-1"


@pytest.fixture()
def client():
    """Frische Datenbank und frische Sitzungen je Test."""
    from app import auth, db
    from app.main import app
    from fastapi.testclient import TestClient
    if os.path.exists(db.db_path()):
        os.remove(db.db_path())
    auth._sessions.clear()
    with TestClient(app) as c:          # Startup legt Schema und Start-Admin an
        yield c


def login(client, user="admin", pw=ADMIN_PW):
    r = client.post("/auth/login", json={"username": user, "password": pw})
    assert r.status_code == 200, r.text
    return {"X-Auth-Token": r.json()["token"]}


@pytest.fixture()
def admin(client):
    return login(client)


def make_user(client, admin, name="viewer1", roles=("viewer",), pw="Passwort-123"):
    r = client.post("/api/users", headers=admin, json={"username": name, "password": pw, "roles": list(roles)})
    assert r.status_code == 201, r.text
    return r.json()


def make_token(client, admin, scope="write", name="skript"):
    r = client.post("/api/tokens", headers=admin, json={"name": name, "scope": scope})
    assert r.status_code == 201, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


@pytest.fixture()
def site(client, admin):
    r = client.post("/api/sites", headers=admin, json={"code": "SITE-A", "name": "Standort A"})
    assert r.status_code == 201, r.text
    return r.json()
