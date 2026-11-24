"""Externe Sicherungsziele: Pfad (NAS/NFS/SMB eingehängt), S3, WebDAV; Verschlüsselung, Aufbewahrung, Fehlerverhalten."""
import hashlib
import re
import shutil
import zipfile
from pathlib import Path

import httpx
import pytest

from app import backup, backup_targets


@pytest.fixture(autouse=True)
def clean(client, monkeypatch):
    shutil.rmtree(backup.backup_dir(), ignore_errors=True)
    monkeypatch.setattr(backup_targets, "SYNC", True)
    from app import db
    db.put_settings({backup_targets.SETTING_KEY: "[]"})
    yield
    db.put_settings({backup_targets.SETTING_KEY: "[]"})


def add(client, admin, **kw):
    r = client.post("/api/admin/backups/targets", headers=admin, json=kw)
    assert r.status_code == 201, r.text
    return r.json()


def backup_now(client, admin):
    r = client.post("/api/admin/backups", headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


def test_sigv4_matches_aws_test_vector():
    """Beispiel „GET Object mit Range“ aus der AWS-Dokumentation zu Signature Version 4."""
    empty = hashlib.sha256(b"").hexdigest()
    auth = backup_targets.sigv4("GET", "/test.txt", {}, {"host": "examplebucket.s3.amazonaws.com", "range": "bytes=0-9", "x-amz-content-sha256": empty,
                                                         "x-amz-date": "20130524T000000Z"}, empty, "20130524T000000Z", "us-east-1",
                                "AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY")
    assert auth == ("AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request,"
                    " SignedHeaders=host;range;x-amz-content-sha256;x-amz-date,"
                    " Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41")


def test_encrypt_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_targets, "CHUNK", 1000)                                 # mehrere Blöcke
    src, enc, out = tmp_path / "a.bin", tmp_path / "a.enc", tmp_path / "a.out"
    data = bytes(range(256)) * 20 + b"ende"
    src.write_bytes(data)
    backup_targets.encrypt_file(src, enc, "geheim")
    assert enc.read_bytes()[:6] == b"PWENC1" and data[:50] not in enc.read_bytes()
    backup_targets.decrypt_file(enc, out, "geheim")
    assert out.read_bytes() == data
    with pytest.raises(backup_targets.TargetError):
        backup_targets.decrypt_file(enc, tmp_path / "x", "falsch")
    cut = tmp_path / "cut.enc"                                                          # abgeschnitten (letzter Block fehlt)
    raw = enc.read_bytes()
    first_len = int.from_bytes(raw[26:30], "big")
    cut.write_bytes(raw[:30 + first_len])
    with pytest.raises(backup_targets.TargetError):
        backup_targets.decrypt_file(cut, tmp_path / "y", "geheim")
    empty = tmp_path / "empty"
    empty.write_bytes(b"")
    backup_targets.encrypt_file(empty, tmp_path / "e.enc", "p")
    backup_targets.decrypt_file(tmp_path / "e.enc", tmp_path / "e.out", "p")
    assert (tmp_path / "e.out").read_bytes() == b""


def test_validation_and_secrets(client, admin, tmp_path):
    bad = lambda **kw: client.post("/api/admin/backups/targets", headers=admin, json=kw).status_code            # noqa: E731
    assert bad(type="ftp", name="x") == 422
    assert bad(type="path", name="x", path="relativ") == 422
    assert bad(type="s3", name="x", bucket="b") == 422                                   # Zugangsdaten fehlen
    assert bad(type="s3", name="x", bucket="b", access_key="a", secret_key="s", endpoint="ftp://x") == 422
    assert bad(type="webdav", name="x", url="nope") == 422
    assert bad(type="path", name="x", path=str(tmp_path), encrypt=True) == 422            # Passphrase fehlt
    t = add(client, admin, type="s3", name="Archiv", bucket="b", access_key="AK", secret_key="SK", endpoint="http://s3.example.test:9000")
    assert t["secret_key_set"] is True and "secret_key" not in t and t["region"] == "us-east-1"
    lst = client.get("/api/admin/backups/targets", headers=admin).json()
    assert [x["name"] for x in lst["items"]] == ["Archiv"] and "secret_key" not in lst["items"][0] and set(lst["types"]) == {"path", "s3", "webdav"}
    assert bad(type="path", name="archiv", path=str(tmp_path)) == 409                     # Name doppelt (ohne Groß/Klein)
    up = client.put(f"/api/admin/backups/targets/{t['id']}", headers=admin, json={"keep": 3})
    assert up.status_code == 200 and up.json()["keep"] == 3 and up.json()["secret_key_set"] is True    # Secret bleibt
    assert backup_targets.get(t["id"])["secret_key"] == "SK"
    assert client.put(f"/api/admin/backups/targets/{t['id']}", headers=admin, json={"type": "path", "path": "/x"}).status_code == 422   # Typ fix
    assert client.delete(f"/api/admin/backups/targets/{t['id']}", headers=admin).status_code == 200
    assert client.get("/api/admin/backups/targets", headers=admin).json()["items"] == []
    assert client.get("/api/admin/backups/targets", headers={}).status_code in (401, 403)


def test_path_target_manual_and_auto(client, admin, tmp_path):
    dest = tmp_path / "nas"
    t = add(client, admin, type="path", name="NAS", path=str(dest), keep=2)
    r_ = client.post(f"/api/admin/backups/targets/{t['id']}/test", headers=admin); assert r_.status_code == 200, r_.text
    b = backup_now(client, admin)                                                        # manuell → sofort extern
    assert (dest / b["name"]).is_file() and zipfile.is_zipfile(dest / b["name"])
    st = client.get("/api/admin/backups/targets", headers=admin).json()["items"][0]
    assert st["last_ok"] is True and st["last_name"] == b["name"]
    items = client.get(f"/api/admin/backups/targets/{t['id']}/items", headers=admin).json()
    assert [i["name"] for i in items] == [b["name"]] and items[0]["kind"] == "manual" and items[0]["encrypted"] is False
    # Aufbewahrung: nur automatische, je Ziel; manuelle bleiben
    import time
    for n in range(3):
        a = backup.create("auto", "test", now=time.time() - 3600 * (10 - n))
        backup_targets.push_all(backup.backup_dir() / a["name"])
    names = sorted(p.name for p in dest.iterdir())
    assert sum("-auto-" in n for n in names) == 2 and sum("-manual-" in n for n in names) == 1
    # erneut übertragen
    r = client.post(f"/api/admin/backups/{b['name']}/push", headers=admin)
    assert r.status_code == 200 and r.json()["results"][0]["ok"] is True
    assert client.post("/api/admin/backups/portwerk-manual-20200101-000000.zip/push", headers=admin).status_code == 404


def test_encrypted_target_and_fetch(client, admin, tmp_path):
    dest = tmp_path / "enc"
    t = add(client, admin, type="path", name="Verschlüsselt", path=str(dest), encrypt=True, passphrase="pw-123")
    b = backup_now(client, admin)
    assert (dest / (b["name"] + ".enc")).is_file() and not (dest / b["name"]).exists()
    assert zipfile.is_zipfile(dest / (b["name"] + ".enc")) is False                      # nicht lesbar
    items = client.get(f"/api/admin/backups/targets/{t['id']}/items", headers=admin).json()
    assert items[0]["encrypted"] is True
    got = backup_targets.fetch(t["id"], b["name"] + ".enc", tmp_path)
    assert got.name == b["name"] and zipfile.is_zipfile(got)                              # entschlüsselt, gültige Sicherung
    # Wiederherstellung vom Ziel verlangt Bestätigung
    assert client.post(f"/api/admin/backups/targets/{t['id']}/restore", headers=admin, json={"name": b["name"] + ".enc"}).status_code == 400
    assert client.post(f"/api/admin/backups/targets/{t['id']}/restore", headers=admin, json={"name": "../etc/passwd", "confirm": True}).status_code == 404


def test_failing_target_does_not_break_backup(client, admin, tmp_path):
    blocker = tmp_path / "datei"
    blocker.write_text("x")
    t = add(client, admin, type="path", name="Kaputt", path=str(blocker / "unter"))      # unter einer Datei: nicht anlegbar
    good = add(client, admin, type="path", name="Gut", path=str(tmp_path / "gut"))
    b = backup_now(client, admin)                                                        # Sicherung gelingt trotzdem
    assert (backup.backup_dir() / b["name"]).is_file() and (tmp_path / "gut" / b["name"]).is_file()
    st = {x["name"]: x for x in client.get("/api/admin/backups/targets", headers=admin).json()["items"]}
    assert st["Kaputt"]["last_ok"] is False and st["Kaputt"]["last_msg"] and st["Gut"]["last_ok"] is True
    assert client.post(f"/api/admin/backups/targets/{t['id']}/test", headers=admin).status_code == 502
    off = client.put(f"/api/admin/backups/targets/{good['id']}", headers=admin, json={"enabled": False}).json()
    assert off["enabled"] is False
    b2 = backup_now(client, admin)
    assert not (tmp_path / "gut" / b2["name"]).exists()                                  # deaktiviertes Ziel wird übersprungen


# ── S3 und WebDAV über simulierte Server ──────────────────────────────────────

S3_NS = "http://s3.amazonaws.com/doc/2006-03-01/"


def fake_s3(store, seen):
    def handler(req: httpx.Request):
        seen.append(req)
        path = req.url.path
        m = re.match(r"^/bucket/(.*)$", path)
        if not m:
            return httpx.Response(404, text="<Error><Message>no bucket</Message></Error>")
        key = m.group(1)
        if req.method == "PUT":
            store[key] = req.read()
            return httpx.Response(200)
        if req.method == "DELETE":
            store.pop(key, None)
            return httpx.Response(204)
        if req.method == "GET" and req.url.params.get("list-type") == "2":
            pre = req.url.params.get("prefix", "")
            body = "".join(f"<Contents><Key>{k}</Key><Size>{len(v)}</Size><LastModified>2026-11-24T10:00:00.000Z</LastModified></Contents>"
                           for k, v in sorted(store.items()) if k.startswith(pre))
            return httpx.Response(200, text=f'<ListBucketResult xmlns="{S3_NS}">{body}<IsTruncated>false</IsTruncated></ListBucketResult>')
        if req.method == "GET":
            return httpx.Response(200, content=store[key]) if key in store else httpx.Response(404)
        return httpx.Response(405)
    return handler


def test_s3_target(client, admin, monkeypatch):
    store, seen = {}, []
    monkeypatch.setattr(backup_targets, "_client", lambda cfg: httpx.Client(transport=httpx.MockTransport(fake_s3(store, seen))))
    t = add(client, admin, type="s3", name="S3", bucket="bucket", access_key="AKTEST", secret_key="SKTEST", endpoint="http://s3.example.test:9000",
            prefix="portwerk/prod", keep=1)
    r_ = client.post(f"/api/admin/backups/targets/{t['id']}/test", headers=admin); assert r_.status_code == 200, r_.text
    assert store == {}                                                                   # Testobjekt wurde wieder gelöscht
    b = backup_now(client, admin)
    key = f"portwerk/prod/{b['name']}"
    assert key in store and zipfile.ZipFile(__import__("io").BytesIO(store[key])).namelist()[0] == "manifest.json"
    put = [r for r in seen if r.method == "PUT"][-1]
    assert put.headers["authorization"].startswith("AWS4-HMAC-SHA256 Credential=AKTEST/") and put.headers["host"] == "s3.example.test:9000"
    assert put.headers["x-amz-content-sha256"] == hashlib.sha256(store[key]).hexdigest()
    items = client.get(f"/api/admin/backups/targets/{t['id']}/items", headers=admin).json()
    assert [i["name"] for i in items] == [b["name"]] and items[0]["modified"] > 0
    got = backup_targets.fetch(t["id"], b["name"], Path(backup.backup_dir()))
    assert zipfile.is_zipfile(got)
    got.unlink()
    # Aufbewahrung 1: zweite automatische Sicherung verdrängt die erste
    import time
    for n in range(2):
        a = backup.create("auto", "t", now=time.time() - 7200 * (3 - n))
        backup_targets.push_all(backup.backup_dir() / a["name"])
    assert sum("-auto-" in k for k in store) == 1 and any("-manual-" in k for k in store)
    err = client.put(f"/api/admin/backups/targets/{t['id']}", headers=admin, json={"bucket": "falsch"}).json()
    assert err["bucket"] == "falsch"
    assert client.post(f"/api/admin/backups/targets/{t['id']}/test", headers=admin).status_code == 502                 # Meldung bei Fehlern


def test_webdav_target(client, admin, monkeypatch):
    store, calls = {}, []

    def handler(req: httpx.Request):
        calls.append((req.method, req.url.path))
        name = req.url.path.rsplit("/", 1)[-1]
        if req.method == "MKCOL":
            return httpx.Response(201)
        if req.method == "PUT":
            store[name] = req.read()
            return httpx.Response(201)
        if req.method == "DELETE":
            store.pop(name, None)
            return httpx.Response(204)
        if req.method == "PROPFIND":
            rows = "".join(f'<d:response><d:href>/dav/sich/{k}</d:href><d:propstat><d:prop><d:getcontentlength>{len(v)}</d:getcontentlength>'
                           f'<d:getlastmodified>Tue, 24 Nov 2026 10:00:00 GMT</d:getlastmodified></d:prop></d:propstat></d:response>' for k, v in store.items())
            return httpx.Response(207, text=f'<?xml version="1.0"?><d:multistatus xmlns:d="DAV:"><d:response><d:href>/dav/sich/</d:href></d:response>{rows}</d:multistatus>')
        if req.method == "GET":
            return httpx.Response(200, content=store[name])
        return httpx.Response(405)
    monkeypatch.setattr(backup_targets, "_client", lambda cfg: httpx.Client(transport=httpx.MockTransport(handler)))
    t = add(client, admin, type="webdav", name="Cloud", url="http://dav.example.test/dav", prefix="sich", user="u", password="p")
    r_ = client.post(f"/api/admin/backups/targets/{t['id']}/test", headers=admin); assert r_.status_code == 200, r_.text
    b = backup_now(client, admin)
    assert b["name"] in store and ("MKCOL", "/dav/sich/") in calls
    items = client.get(f"/api/admin/backups/targets/{t['id']}/items", headers=admin).json()
    assert [i["name"] for i in items] == [b["name"]] and items[0]["size"] == len(store[b["name"]])
    assert zipfile.is_zipfile(backup_targets.fetch(t["id"], b["name"], Path(backup.backup_dir())))
