"""Externe Sicherungsziele: Sicherungen zusätzlich außerhalb des Servers ablegen.

Typen
  * ``path``   – Verzeichnis im Container, z. B. ein eingehängtes NAS-Share (NFS/SMB wird auf dem Host als Docker-Volume eingehängt)
  * ``s3``     – S3 oder S3-kompatibel (MinIO, Ceph RGW, …); Signatur (SigV4) mit ``httpx``, ohne zusätzliches Paket
  * ``webdav`` – WebDAV (Nextcloud, viele NAS)

Nach jeder automatischen und manuellen Sicherung werden alle aktiven Ziele bedient; Fehler stören die Sicherung nicht, sie stehen im Status des Ziels
und im Audit-Log. Je Ziel gilt eine eigene Aufbewahrung für **automatische** Sicherungen (manuelle bleiben). Optional wird vor der Übertragung
mit einer Passphrase verschlüsselt (AES-256-GCM, Schlüssel per scrypt; Endung ``.enc``), damit auf dem Ziel keine lesbaren Daten liegen.
Die Einstellungen stehen in ``app_settings`` (Schlüssel ``backup_targets``).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import shutil
import ssl
import tempfile
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterator, Optional

import httpx
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException

from . import audit, backup, db

log = logging.getLogger("opp.backup.targets")

SETTING_KEY = "backup_targets"
TYPES = {"path": "Verzeichnis (NAS/NFS/SMB, eingehängt)", "s3": "S3 / S3-kompatibel", "webdav": "WebDAV"}
SECRETS = ("secret_key", "password", "passphrase")
NAME_RE = re.compile(r"^portwerk-(auto|manual)-\d{8}-\d{6}(-\d+)?\.zip(\.enc)?$")
SYNC = False                                        # Tests schalten die Übertragung im Hintergrund ab
TIMEOUT = 120
MAGIC = b"PWENC1"
CHUNK = 1024 * 1024


class TargetError(Exception):
    pass


# ── Einstellungen ─────────────────────────────────────────────────────────────

def _load() -> list[dict]:
    r = db.row("SELECT value FROM app_settings WHERE key = ?", (SETTING_KEY,))
    return json.loads(r["value"]) if r else []


def _store(items: list[dict]) -> None:
    db.put_settings({SETTING_KEY: json.dumps(items)})


def public(t: dict) -> dict:
    out = {k: v for k, v in t.items() if k not in SECRETS}
    for k in SECRETS:
        out[k + "_set"] = bool(t.get(k))
    out["type_label"] = TYPES.get(t["type"], t["type"])
    return out


def list_public() -> list[dict]:
    return [public(t) for t in _load()]


def get(tid: str) -> dict:
    for t in _load():
        if t["id"] == tid:
            return t
    raise HTTPException(404, "Sicherungsziel nicht gefunden")


def _check_url(u: str, what: str) -> str:
    u = str(u or "").strip().rstrip("/")
    if not re.match(r"^https?://[^\s/]+(/[^\s?#]*)?$", u):
        raise HTTPException(422, f"{what}: Adresse im Format https://host/pfad erwartet")
    return u


def save(body: dict, tid: Optional[str] = None) -> dict:
    items = _load()
    cur = next((t for t in items if t["id"] == tid), None) if tid else None
    if tid and not cur:
        raise HTTPException(404, "Sicherungsziel nicht gefunden")
    typ = body.get("type") or (cur or {}).get("type")
    if typ not in TYPES:
        raise HTTPException(422, "Typ ungültig (path, s3 oder webdav)")
    if cur and cur["type"] != typ:
        raise HTTPException(422, "Der Typ eines Ziels lässt sich nicht ändern – bitte neu anlegen")
    t = {**(cur or {"id": secrets.token_hex(4), "type": typ, "enabled": True, "keep": 14, "encrypt": False, "verify_tls": True, "ca_pem": "",
                    "last_at": None, "last_ok": None, "last_msg": "", "last_name": ""})}
    fields = {"name", "enabled", "keep", "encrypt", "verify_tls", "ca_pem", *SECRETS}
    fields |= {"path"} if typ == "path" else {"endpoint", "region", "bucket", "prefix", "access_key", "path_style"} if typ == "s3" else {"url", "user", "prefix"}
    for k in fields:
        if k in body and body[k] is not None:
            if k in SECRETS and body[k] == "":
                continue                                    # leer = unverändert
            t[k] = body[k]
    t["name"] = str(t.get("name", "")).strip()
    if not t["name"]:
        raise HTTPException(422, "Bitte einen Namen angeben")
    if any(o["name"].lower() == t["name"].lower() and o["id"] != t["id"] for o in items):
        raise HTTPException(409, "Ein Ziel mit diesem Namen gibt es schon")
    if not 1 <= int(t["keep"]) <= 365:
        raise HTTPException(422, "Aufbewahren: 1–365")
    t["keep"] = int(t["keep"])
    if t["encrypt"] and not t.get("passphrase"):
        raise HTTPException(422, "Für die Verschlüsselung ist eine Passphrase nötig")
    if typ == "path":
        if not os.path.isabs(str(t.get("path", ""))):
            raise HTTPException(422, "Pfad: absoluter Pfad im Container erwartet (z. B. /backup-extern)")
        t["path"] = str(t["path"]).rstrip("/") or "/"
    elif typ == "s3":
        t.setdefault("region", "us-east-1")
        t["region"] = str(t.get("region") or "us-east-1").strip()
        if not str(t.get("bucket", "")).strip():
            raise HTTPException(422, "S3: Bucket fehlt")
        if not (t.get("access_key") and t.get("secret_key")):
            raise HTTPException(422, "S3: Zugangsschlüssel und Secret nötig")
        t["endpoint"] = _check_url(t["endpoint"], "S3-Endpunkt") if str(t.get("endpoint", "")).strip() else ""
        t["bucket"], t["prefix"] = str(t["bucket"]).strip(), str(t.get("prefix", "")).strip().strip("/")
        t.setdefault("path_style", True)
    else:
        t["url"] = _check_url(t.get("url"), "WebDAV")
        t["prefix"] = str(t.get("prefix", "")).strip().strip("/")
    if cur:
        items[items.index(cur)] = t
    else:
        items.append(t)
    _store(items)
    return public(t)


def delete(tid: str) -> None:
    get(tid)
    _store([t for t in _load() if t["id"] != tid])


def _status(tid: str, ok: bool, msg: str, name: str = "") -> None:
    items = _load()
    for t in items:
        if t["id"] == tid:
            t.update(last_at=time.time(), last_ok=ok, last_msg=msg[:300], last_name=name or t.get("last_name", ""))
    _store(items)


# ── Verschlüsselung ───────────────────────────────────────────────────────────

def _key(passphrase: str, salt: bytes) -> bytes:
    return hashlib.scrypt(passphrase.encode(), salt=salt, n=2 ** 15, r=8, p=1, dklen=32, maxmem=96 * 1024 * 1024)


def encrypt_file(src: Path, dst: Path, passphrase: str) -> None:
    """Datei in Blöcken mit AES-256-GCM verschlüsseln; Block-Zähler und „letzter Block“ stecken in den authentifizierten Daten (Schutz vor Kürzen/Vertauschen)."""
    salt, prefix = os.urandom(16), os.urandom(4)
    head = MAGIC + salt + prefix
    aes = AESGCM(_key(passphrase, salt))
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        fout.write(head)
        buf, i = fin.read(CHUNK), 0
        while True:
            nxt = fin.read(CHUNK)
            last = not nxt
            ct = aes.encrypt(prefix + i.to_bytes(8, "big"), buf, head + (b"\x01" if last else b"\x00"))
            fout.write(len(ct).to_bytes(4, "big") + ct)
            if last:
                break
            buf, i = nxt, i + 1


def decrypt_file(src: Path, dst: Path, passphrase: str) -> None:
    try:
        with open(src, "rb") as fin, open(dst, "wb") as fout:
            head = fin.read(len(MAGIC) + 20)
            if len(head) != len(MAGIC) + 20 or not head.startswith(MAGIC):
                raise TargetError("Die Datei ist nicht verschlüsselt (oder beschädigt)")
            salt, prefix = head[len(MAGIC):len(MAGIC) + 16], head[len(MAGIC) + 16:]
            aes = AESGCM(_key(passphrase, salt))
            i = 0
            while True:
                ln = fin.read(4)
                if not ln:
                    raise TargetError("Die verschlüsselte Datei ist abgeschnitten")
                ct = fin.read(int.from_bytes(ln, "big"))
                last = fin.peek(1) == b""                                    # nach diesem Block ist die Datei zu Ende
                fout.write(aes.decrypt(prefix + i.to_bytes(8, "big"), ct, head + (b"\x01" if last else b"\x00")))
                if last:
                    break
                i += 1
    except InvalidTag:
        raise TargetError("Entschlüsselung fehlgeschlagen: falsche Passphrase oder beschädigte/abgeschnittene Datei")


# ── Backends ──────────────────────────────────────────────────────────────────

def _ssl(cfg: dict):
    ctx = ssl.create_default_context()
    if str(cfg.get("ca_pem", "")).strip():
        ctx.load_verify_locations(cadata=cfg["ca_pem"])
    if not cfg.get("verify_tls", True):
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    return ctx


def _client(cfg: dict) -> httpx.Client:
    """HTTP-Client (Tests ersetzen diese Funktion durch einen Client mit Mock-Transport)."""
    return httpx.Client(verify=_ssl(cfg), timeout=TIMEOUT, follow_redirects=False, trust_env=False)


def _iter_file(p: Path) -> Iterator[bytes]:
    with open(p, "rb") as f:
        while True:
            b = f.read(CHUNK)
            if not b:
                return
            yield b


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    for b in _iter_file(p):
        h.update(b)
    return h.hexdigest()


class PathBackend:
    def __init__(self, cfg: dict):
        self.dir = Path(cfg["path"])

    def put(self, name: str, src: Path) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.dir / (name + ".part")
        shutil.copyfile(src, tmp)
        os.replace(tmp, self.dir / name)

    def list(self) -> list[dict]:
        if not self.dir.is_dir():
            return []
        return [{"name": p.name, "size": p.stat().st_size, "modified": p.stat().st_mtime} for p in self.dir.iterdir() if p.is_file() and NAME_RE.match(p.name)]

    def get(self, name: str, dest: Path) -> None:
        shutil.copyfile(self.dir / name, dest)

    def delete(self, name: str) -> None:
        (self.dir / name).unlink(missing_ok=True)

    def check(self) -> str:
        self.dir.mkdir(parents=True, exist_ok=True)
        probe = self.dir / f".portwerk-test-{secrets.token_hex(3)}"
        probe.write_text("ok")
        probe.unlink()
        return f"Verzeichnis {self.dir} ist beschreibbar"


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def sigv4(method: str, uri: str, query: dict, headers: dict, payload_hash: str, amz_date: str, region: str, access_key: str, secret_key: str,
          service: str = "s3") -> str:
    """AWS Signature Version 4 (Header ``Authorization``). ``headers``: alle zu signierenden Header (Namen beliebig geschrieben)."""
    q = lambda s: urllib.parse.quote(str(s), safe="~")                                     # noqa: E731
    cq = "&".join(f"{q(k)}={q(v)}" for k, v in sorted(query.items()))
    hs = {k.lower(): " ".join(str(v).split()) for k, v in headers.items()}
    names = sorted(hs)
    canonical = "\n".join([method, uri, cq, "".join(f"{n}:{hs[n]}\n" for n in names), ";".join(names), payload_hash])
    date = amz_date[:8]
    scope = f"{date}/{region}/{service}/aws4_request"
    sts = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    k = _hmac(_hmac(_hmac(_hmac(("AWS4" + secret_key).encode(), date), region), service), "aws4_request")
    sig = hmac.new(k, sts.encode(), hashlib.sha256).hexdigest()
    return f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, SignedHeaders={';'.join(names)}, Signature={sig}"


class S3Backend:
    def __init__(self, cfg: dict):
        self.c = cfg
        ep = (cfg.get("endpoint") or "").rstrip("/")
        bucket, region = cfg["bucket"], cfg.get("region") or "us-east-1"
        if not ep:                                                          # AWS: bucket.s3.<region>.amazonaws.com
            self.scheme, self.host, self.base = "https", f"{bucket}.s3.{region}.amazonaws.com", ""
        else:
            u = urllib.parse.urlparse(ep)
            self.scheme = u.scheme
            if cfg.get("path_style", True):
                self.host, self.base = u.netloc, f"{u.path.rstrip('/')}/{bucket}"
            else:
                self.host, self.base = f"{bucket}.{u.netloc}", u.path.rstrip("/")
        self.region, self.prefix = region, str(cfg.get("prefix") or "").strip("/")

    def _key(self, name: str = "") -> str:
        return f"{self.prefix}/{name}" if self.prefix and name else (self.prefix + "/" if self.prefix else name)

    def _do(self, method: str, name: str = "", query: Optional[dict] = None, src: Optional[Path] = None, dest: Optional[Path] = None, key: Optional[str] = None):
        query = query or {}
        uri = urllib.parse.quote(f"{self.base}/{self._key(name) if key is None else key}", safe="/~") or "/"
        empty = hashlib.sha256(b"").hexdigest()
        phash = _sha256_file(src) if src else empty
        amz = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        headers = {"host": self.host, "x-amz-content-sha256": phash, "x-amz-date": amz}
        auth = sigv4(method, uri, query, headers, phash, amz, self.region, self.c["access_key"], self.c["secret_key"])
        h = {"x-amz-content-sha256": phash, "x-amz-date": amz, "Authorization": auth}
        url = f"{self.scheme}://{self.host}{uri}" + ("?" + "&".join(f"{urllib.parse.quote(k, safe='~')}={urllib.parse.quote(str(v), safe='~')}" for k, v in sorted(query.items())) if query else "")
        with _client(self.c) as cl:
            if src:
                h["Content-Length"] = str(src.stat().st_size)
                return cl.request(method, url, headers=h, content=_iter_file(src))
            if dest:
                with cl.stream(method, url, headers=h) as r:
                    if r.status_code == 200:
                        with open(dest, "wb") as f:
                            for b in r.iter_bytes(CHUNK):
                                f.write(b)
                    else:
                        r.read()
                    return r
            return cl.request(method, url, headers=h)

    @staticmethod
    def _ok(r, what: str, good=(200, 204)) -> None:
        if r.status_code not in good:
            m = re.search(r"<Message>(.*?)</Message>", r.text or "") if hasattr(r, "text") else None
            raise TargetError(f"S3 {what}: HTTP {r.status_code}" + (f" – {m.group(1)}" if m else ""))

    def put(self, name: str, src: Path) -> None:
        self._ok(self._do("PUT", name, src=src), "Upload")

    def list(self) -> list[dict]:
        out, token = [], None
        while True:
            q = {"list-type": "2", "prefix": self._key()}
            if token:
                q["continuation-token"] = token
            r = self._do("GET", query=q, key="")
            self._ok(r, "Auflisten")
            root = ET.fromstring(r.text)
            ns = lambda t: re.sub(r"^\{.*?\}", "", t)                       # noqa: E731
            for c in root:
                if ns(c.tag) == "Contents":
                    d = {ns(x.tag): (x.text or "") for x in c}
                    nm = d.get("Key", "")[len(self._key()):]
                    if NAME_RE.match(nm):
                        out.append({"name": nm, "size": int(d.get("Size", 0) or 0), "modified": _iso(d.get("LastModified"))})
            nt = next((x.text for x in root if ns(x.tag) == "NextContinuationToken"), None)
            if not nt:
                return out
            token = nt

    def get(self, name: str, dest: Path) -> None:
        self._ok(self._do("GET", name, dest=dest), "Download", good=(200,))

    def delete(self, name: str) -> None:
        self._ok(self._do("DELETE", name), "Löschen")

    def check(self) -> str:
        probe = f"portwerk-test-{secrets.token_hex(3)}.txt"
        fd, name = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        tmp = Path(name)
        try:
            tmp.write_text("ok")
            self._ok(self._do("PUT", probe, src=tmp), "Schreiben")
            self._ok(self._do("DELETE", probe), "Löschen")
        finally:
            tmp.unlink(missing_ok=True)
        return f"Bucket {self.c['bucket']} ist beschreibbar"


def _iso(s: Optional[str]) -> float:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


class WebDavBackend:
    def __init__(self, cfg: dict):
        self.c = cfg
        self.base = cfg["url"].rstrip("/")
        self.prefix = str(cfg.get("prefix") or "").strip("/")
        self.auth = (cfg.get("user", ""), cfg.get("password", "")) if cfg.get("user") else None

    def _url(self, name: str = "") -> str:
        parts = [p for p in (self.prefix, name) if p]
        return self.base + ("/" + "/".join(urllib.parse.quote(x, safe="/") for x in parts) if parts else "") + ("/" if not name and parts else "")

    def _req(self, method: str, name: str = "", **kw):
        with _client(self.c) as cl:
            if kw.get("dest"):
                dest = kw.pop("dest")
                with cl.stream(method, self._url(name), auth=self.auth, **kw) as r:
                    if r.status_code == 200:
                        with open(dest, "wb") as f:
                            for b in r.iter_bytes(CHUNK):
                                f.write(b)
                    else:
                        r.read()
                    return r
            return cl.request(method, self._url(name), auth=self.auth, **kw)

    def _mkdirs(self) -> None:
        cur = self.base
        for seg in [s for s in self.prefix.split("/") if s]:
            cur += "/" + urllib.parse.quote(seg)
            with _client(self.c) as cl:
                r = cl.request("MKCOL", cur + "/", auth=self.auth)
            if r.status_code not in (201, 405, 200, 301):                 # 405 = gibt es schon
                raise TargetError(f"WebDAV: Ordner anlegen: HTTP {r.status_code}")

    def put(self, name: str, src: Path) -> None:
        self._mkdirs()
        r = self._req("PUT", name, content=_iter_file(src), headers={"Content-Length": str(src.stat().st_size)})
        if r.status_code not in (200, 201, 204):
            raise TargetError(f"WebDAV Upload: HTTP {r.status_code}")

    def list(self) -> list[dict]:
        r = self._req("PROPFIND", headers={"Depth": "1", "Content-Type": "application/xml"},
                      content=b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:getcontentlength/><d:getlastmodified/></d:prop></d:propfind>')
        if r.status_code == 404:
            return []
        if r.status_code not in (200, 207):
            raise TargetError(f"WebDAV Auflisten: HTTP {r.status_code}")
        out, ns = [], lambda t: re.sub(r"^\{.*?\}", "", t)                  # noqa: E731
        for resp in ET.fromstring(r.text):
            d = {}
            for el in resp.iter():
                d[ns(el.tag)] = (el.text or "").strip()
            nm = urllib.parse.unquote(d.get("href", "")).rstrip("/").rsplit("/", 1)[-1]
            if NAME_RE.match(nm):
                try:
                    mod = parsedate_to_datetime(d.get("getlastmodified", "")).timestamp()
                except (TypeError, ValueError):
                    mod = 0.0
                out.append({"name": nm, "size": int(d.get("getcontentlength") or 0), "modified": mod})
        return out

    def get(self, name: str, dest: Path) -> None:
        r = self._req("GET", name, dest=dest)
        if r.status_code != 200:
            raise TargetError(f"WebDAV Download: HTTP {r.status_code}")

    def delete(self, name: str) -> None:
        r = self._req("DELETE", name)
        if r.status_code not in (200, 204, 404):
            raise TargetError(f"WebDAV Löschen: HTTP {r.status_code}")

    def check(self) -> str:
        probe = f"portwerk-test-{secrets.token_hex(3)}.txt"
        self._mkdirs()
        r = self._req("PUT", probe, content=b"ok")
        if r.status_code not in (200, 201, 204):
            raise TargetError(f"WebDAV Schreiben: HTTP {r.status_code}")
        self.delete(probe)
        return f"{self.base}/{self.prefix} ist beschreibbar"


def backend(t: dict):
    return {"path": PathBackend, "s3": S3Backend, "webdav": WebDavBackend}[t["type"]](t)


# ── Übertragen, Aufbewahren, Wiederherstellen ────────────────────────────────

def test(tid: str) -> dict:
    t = get(tid)
    try:
        msg = backend(t).check()
    except (TargetError, OSError, httpx.HTTPError) as e:
        raise HTTPException(502, f"Test fehlgeschlagen: {e}")
    return {"ok": True, "message": msg}


def _kind(name: str) -> str:
    return NAME_RE.match(name).group(1)


def _prune(t: dict, be) -> list[str]:
    """Älteste automatische Sicherungen auf dem Ziel über ``keep`` hinaus löschen."""
    autos = sorted((x for x in be.list() if _kind(x["name"]) == "auto"), key=lambda x: x["name"], reverse=True)
    gone = [x["name"] for x in autos[t["keep"]:]]
    for n in gone:
        be.delete(n)
    return gone


def push_one(t: dict, src: Path) -> str:
    """Eine Sicherung auf ein Ziel übertragen (verschlüsselt, wenn eingestellt). Liefert den Namen auf dem Ziel."""
    name = src.name
    with tempfile.TemporaryDirectory(dir=backup.backup_dir()) as tmp:
        up = src
        if t.get("encrypt"):
            name += ".enc"
            up = Path(tmp) / name
            encrypt_file(src, up, t["passphrase"])
        be = backend(t)
        be.put(name, up)
        _prune(t, be)
    return name


def push_all(src: Path, only: Optional[str] = None) -> list[dict]:
    """Auf alle aktiven Ziele (oder nur ``only``) übertragen; Fehler werden im Status vermerkt, nie geworfen."""
    res = []
    for t in _load():
        if (only and t["id"] != only) or (not only and not t.get("enabled", True)):
            continue
        try:
            name = push_one(t, src)
            _status(t["id"], True, "übertragen", name)
            res.append({"target": t["name"], "ok": True, "name": name})
        except Exception as e:                                                          # noqa: BLE001 – ein Ziel darf die anderen nie blockieren
            log.warning("Sicherungsziel %s: %s", t["name"], e)
            _status(t["id"], False, str(e))
            audit.log("system", "backup.target.error", "backup", src.name, f"{t['name']}: {str(e)[:200]}")
            res.append({"target": t["name"], "ok": False, "error": str(e)})
    return res


def push_async(src: Path, only: Optional[str] = None) -> None:
    if SYNC:
        push_all(src, only)
    else:
        threading.Thread(target=push_all, args=(src, only), daemon=True, name="backup-targets").start()


def remote_items(tid: str) -> list[dict]:
    t = get(tid)
    try:
        items = backend(t).list()
    except (TargetError, OSError, httpx.HTTPError) as e:
        raise HTTPException(502, f"Auflisten fehlgeschlagen: {e}")
    return [{**x, "encrypted": x["name"].endswith(".enc"), "kind": _kind(x["name"])} for x in sorted(items, key=lambda x: x["name"], reverse=True)]


def fetch(tid: str, name: str, workdir: Path) -> Path:
    """Sicherung vom Ziel holen (und entschlüsseln) – liefert eine lokale ZIP-Datei in ``workdir``."""
    t = get(tid)
    if not NAME_RE.match(name):
        raise HTTPException(404, "Sicherung nicht gefunden")
    raw = workdir / ("dl-" + name)
    try:
        backend(t).get(name, raw)
        if name.endswith(".enc"):
            if not t.get("passphrase"):
                raise HTTPException(409, "Für diese verschlüsselte Sicherung fehlt die Passphrase am Ziel")
            out = workdir / name[:-4]
            decrypt_file(raw, out, t["passphrase"])
            return out
        return raw
    except (TargetError, OSError, httpx.HTTPError) as e:
        raise HTTPException(502, f"Download fehlgeschlagen: {e}")
