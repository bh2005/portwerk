"""Sicherung und Wiederherstellung: ZIP mit Datenbank, TLS und Manifest; Prüfungen vor dem Ersetzen; Automatik mit Aufbewahrung."""
import io
import json
import shutil
import sqlite3
import time
import zipfile

import pytest

from conftest import ADMIN_PW, login, make_user


@pytest.fixture(autouse=True)
def clean_backups():
    from app import backup
    shutil.rmtree(backup.backup_dir(), ignore_errors=True)
    shutil.rmtree(backup.tls_dir(), ignore_errors=True)
    yield


def sites(client, h):
    return sorted(s["code"] for s in client.get("/api/sites", headers=h).json())


def make_backup(client, admin):
    r = client.post("/api/admin/backups", headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_list_download(client, admin):
    b = make_backup(client, admin)
    assert b["kind"] == "manual" and b["created_by"] == "admin" and b["size"] > 0
    listing = client.get("/api/admin/backups", headers=admin).json()
    assert [x["name"] for x in listing["items"]] == [b["name"]]
    assert listing["settings"] == {"auto": True, "hour": 2, "keep": 14}
    r = client.get(f"/api/admin/backups/{b['name']}/download", headers=admin)
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert {"manifest.json", "opp.db"} <= set(z.namelist())
    m = json.loads(z.read("manifest.json"))
    assert m["app"] == "portwerk" and "0023_four_eyes.sql" in m["migrations"]


def test_restore_roundtrip_and_relogin(client, admin):
    client.post("/api/sites", headers=admin, json={"code": "ALT", "name": "vorher"})
    b = make_backup(client, admin)
    client.post("/api/sites", headers=admin, json={"code": "NEU", "name": "danach"})
    assert client.post(f"/api/admin/backups/{b['name']}/restore", headers=admin, json={}).status_code == 400    # ohne Bestätigung
    r = client.post(f"/api/admin/backups/{b['name']}/restore", headers=admin, json={"confirm": True})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["relogin"] and out["safety_backup"].startswith("portwerk-before-restore-")
    assert client.get("/api/sites", headers=admin).status_code == 401                # alle Sitzungen beendet
    admin = login(client, "admin", ADMIN_PW)
    assert sites(client, admin) == ["ALT"]
    # die Sicherheitskopie enthält den Stand davor – Rückgängig machen
    assert client.post(f"/api/admin/backups/{out['safety_backup']}/restore", headers=admin, json={"confirm": True}).status_code == 200
    assert sites(client, login(client, "admin", ADMIN_PW)) == ["ALT", "NEU"]
    actions = [e["action"] for e in _audit(client, login(client, "admin", ADMIN_PW))]
    assert "backup.restore" in actions


def _audit(client, h):
    log = client.get("/api/audit", headers=h).json()
    return log["items"] if isinstance(log, dict) else log


def test_upload_restore_zip_and_bare_db(client, admin):
    client.post("/api/sites", headers=admin, json={"code": "UP", "name": "Upload"})
    b = make_backup(client, admin)
    data = client.get(f"/api/admin/backups/{b['name']}/download", headers=admin).content
    client.post("/api/sites", headers=admin, json={"code": "WEG", "name": "verschwindet"})
    up = lambda h, content, name="s.zip", confirm=True: client.post("/api/admin/backups/restore-upload", headers=h,  # noqa: E731
                                                                   params={"confirm": confirm}, files={"file": (name, content)})
    assert up(admin, data, confirm=False).status_code == 400
    assert up(admin, data).status_code == 200
    admin = login(client, "admin", ADMIN_PW)
    assert sites(client, admin) == ["UP"]
    raw = zipfile.ZipFile(io.BytesIO(data)).read("opp.db")                           # nackte SQLite-Datei geht auch
    assert up(admin, raw, "opp.db").status_code == 200


def _db_bytes(tmp_path, mutate):
    from app import db
    p = tmp_path / "x.db"
    with sqlite3.connect(db.db_path()) as src, sqlite3.connect(p) as dst:
        src.backup(dst)
    c = sqlite3.connect(p)
    mutate(c)
    c.commit(); c.close()
    return p.read_bytes()


def test_rejects_bad_uploads_without_touching_data(client, admin, tmp_path):
    client.post("/api/sites", headers=admin, json={"code": "BLEIBT", "name": "x"})
    up = lambda content: client.post("/api/admin/backups/restore-upload", headers=admin, params={"confirm": True},  # noqa: E731
                                     files={"file": ("f", content)})
    r = up(b"kein sqlite")
    assert r.status_code == 400 and "SQLite" in r.json()["detail"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("manifest.json", "{}")
    assert "keine Datenbank" in up(buf.getvalue()).json()["detail"]
    newer = _db_bytes(tmp_path, lambda c: c.execute("INSERT INTO schema_migrations VALUES ('9999_zukunft.sql', 0)"))
    assert "neueren" in up(newer).json()["detail"]
    tmp2 = tmp_path / "b"; tmp2.mkdir()
    no_admin = _db_bytes(tmp2, lambda c: c.execute("UPDATE users SET roles = 'viewer'"))
    assert "Administrator" in up(no_admin).json()["detail"]
    foreign = tmp_path / "f.db"
    with sqlite3.connect(foreign) as c:
        c.execute("CREATE TABLE t (x)")
    assert "keine Portwerk" in up(foreign.read_bytes()).json()["detail"]
    assert sites(client, admin) == ["BLEIBT"]                                       # nichts ersetzt, Sitzung gilt weiter
    assert client.get("/api/admin/backups", headers=admin).json()["items"] == []    # keine Sicherheitskopie bei Ablehnung


def test_tls_files_are_saved_and_restored(client, admin):
    from app import backup
    backup.tls_dir().mkdir(parents=True, exist_ok=True)
    (backup.tls_dir() / "fullchain.pem").write_text("ALT")
    b = make_backup(client, admin)
    assert b["tls"]
    (backup.tls_dir() / "fullchain.pem").write_text("NEU")
    (backup.tls_dir() / "privkey.pem").write_text("fremd")
    assert client.post(f"/api/admin/backups/{b['name']}/restore", headers=admin, json={"confirm": True}).json()["tls"]
    assert sorted(p.name for p in backup.tls_dir().iterdir()) == ["fullchain.pem"]
    assert (backup.tls_dir() / "fullchain.pem").read_text() == "ALT"


def test_zip_with_path_traversal_is_contained(client, admin, tmp_path):
    from app import backup
    good = client.get(f"/api/admin/backups/{make_backup(client, admin)['name']}/download", headers=admin).content
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(good)) as src, zipfile.ZipFile(buf, "w") as z:
        z.writestr("opp.db", src.read("opp.db"))
        z.writestr("tls/../../boese.txt", "x")
        z.writestr("tls/ok.pem", "ok")
    r = client.post("/api/admin/backups/restore-upload", headers=admin, params={"confirm": True}, files={"file": ("f.zip", buf.getvalue())})
    assert r.status_code == 200, r.text
    assert [p.name for p in backup.tls_dir().iterdir()] == ["ok.pem"]
    assert not (backup.tls_dir().parent.parent / "boese.txt").exists()


def test_names_and_permissions(client, admin):
    assert client.get("/api/admin/backups/..%2Fopp.db/download", headers=admin).status_code == 404
    assert client.delete("/api/admin/backups/irgendwas.zip", headers=admin).status_code == 404
    make_user(client, admin, "planer1", roles=("planer",))
    h = login(client, "planer1", "Passwort-123")
    assert client.get("/api/admin/backups", headers=h).status_code == 403
    assert client.post("/api/admin/backups", headers=h).status_code == 403
    b = make_backup(client, admin)
    assert client.delete(f"/api/admin/backups/{b['name']}", headers=admin).status_code == 200
    assert client.get("/api/admin/backups", headers=admin).json()["items"] == []


def test_auto_backup_once_per_day_and_prune(client, admin):
    from app import backup
    r = client.put("/api/admin/backups/settings", headers=admin, json={"auto": True, "hour": 3, "keep": 2})
    assert r.status_code == 200
    day = lambda d, h: time.mktime((2026, 11, d, h, 0, 0, 0, 0, -1))  # noqa: E731
    assert backup.run_auto_if_due(day(20, 2)) is None                                # vor der Uhrzeit
    names = []
    for d in (20, 21, 22):
        b = backup.run_auto_if_due(day(d, 4))
        assert b and b["kind"] == "auto" and f"-202611{d}-" in b["name"]
        assert backup.run_auto_if_due(day(d, 5)) is None                             # einmal pro Tag
        names.append(b["name"])
    left = [x["name"] for x in backup.list_all() if x["kind"] == "auto"]
    assert sorted(left) == sorted(names[1:])                                         # nur die zwei neuesten bleiben
    client.put("/api/admin/backups/settings", headers=admin, json={"auto": False, "hour": 3, "keep": 2})
    assert backup.run_auto_if_due(day(23, 4)) is None
