"""Sicherung und Wiederherstellung: ZIP mit konsistenter Momentaufnahme der Datenbank (``VACUUM INTO``), TLS-Dateien und Manifest.

Sicherungen liegen in ``<data_dir>/backups`` (nur für den Dienst-Benutzer lesbar – sie enthalten Passwort-Hashes und Zugangsdaten).
Automatische Sicherungen (``portwerk-auto-…``) werden täglich angelegt und auf eine Höchstzahl begrenzt; manuelle und die vor einer
Wiederherstellung angelegten Sicherungen bleiben, bis sie gelöscht werden.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import tempfile
import threading
import time
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import HTTPException

from . import db
from .config import settings

log = logging.getLogger("opp.backup")

NAME_RE = re.compile(r"^portwerk-(auto|manual|before-restore)-\d{8}-\d{6}(-\d+)?\.zip$")
KINDS = {"auto": "automatisch", "manual": "manuell", "before-restore": "vor Wiederherstellung"}
DEFAULTS = {"backup_auto": "1", "backup_hour": "2", "backup_keep": "14"}
MAX_DB_BYTES = 2 * 1024 ** 3                 # Obergrenze beim Entpacken (Schutz vor ZIP-Bomben)
_bg_started = False


def backup_dir() -> Path:
    d = Path(settings.data_dir) / "backups"
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    return d


def tls_dir() -> Path:
    return Path(settings.data_dir) / "tls"


def known_migrations() -> set[str]:
    return {f.name for f in db.MIGRATIONS_DIR.glob("*.sql")}


# ── Einstellungen ─────────────────────────────────────────────────────────────

def get_settings() -> dict:
    return {"auto": db.get_setting("backup_auto", DEFAULTS["backup_auto"]) == "1",
            "hour": int(db.get_setting("backup_hour", DEFAULTS["backup_hour"])),
            "keep": int(db.get_setting("backup_keep", DEFAULTS["backup_keep"]))}


def save_settings(auto: bool, hour: int, keep: int) -> dict:
    if not 0 <= hour <= 23:
        raise HTTPException(400, "Uhrzeit: 0–23")
    if not 1 <= keep <= 365:
        raise HTTPException(400, "Anzahl aufzubewahrender Sicherungen: 1–365")
    db.put_settings({"backup_auto": "1" if auto else "0", "backup_hour": hour, "backup_keep": keep})
    return get_settings()


# ── Anlegen, Auflisten, Löschen ───────────────────────────────────────────────

def _new_name(kind: str, now: Optional[float] = None) -> Path:
    base = f"portwerk-{kind}-{time.strftime('%Y%m%d-%H%M%S', time.localtime(now))}"
    p, n = backup_dir() / f"{base}.zip", 1
    while p.exists():
        n += 1
        p = backup_dir() / f"{base}-{n}.zip"
    return p


def create(kind: str = "manual", by: str = "", now: Optional[float] = None) -> dict:
    """Legt eine Sicherung an und liefert ihre Beschreibung (``now`` bestimmt den Dateinamen, Standard: jetzt)."""
    target = _new_name(kind, now)
    with tempfile.TemporaryDirectory(dir=backup_dir()) as tmp:
        snap = os.path.join(tmp, "opp.db")
        with db._lock, db.conn() as c:                                       # konsistent, auch während andere lesen
            c.execute("VACUUM INTO ?", (snap,))
            migrations = [r["name"] for r in c.execute("SELECT name FROM schema_migrations ORDER BY name")]
        from .main import app                                                # spät importieren (Zirkelbezug)
        manifest = {"app": "portwerk", "version": app.version, "created_at": time.time(), "created_by": by, "kind": kind,
                    "migrations": migrations}
        partial = target.with_suffix(".part")
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
            z.write(snap, "opp.db")
            if tls_dir().is_dir():
                for f in sorted(tls_dir().iterdir()):
                    if f.is_file():
                        z.write(f, f"tls/{f.name}")
        os.chmod(partial, 0o600)
        os.replace(partial, target)
    return describe(target)


def describe(p: Path) -> dict:
    kind = NAME_RE.match(p.name).group(1)
    info = {"name": p.name, "kind": kind, "kind_label": KINDS[kind], "size": p.stat().st_size, "created_at": p.stat().st_mtime,
            "created_by": "", "version": "", "tls": False}
    try:
        with zipfile.ZipFile(p) as z:
            m = json.loads(z.read("manifest.json"))
            info.update(created_at=m.get("created_at", info["created_at"]), created_by=m.get("created_by", ""),
                        version=m.get("version", ""), tls=any(n.startswith("tls/") for n in z.namelist()))
    except (zipfile.BadZipFile, KeyError, ValueError):
        info["damaged"] = True
    return info


def path_of(name: str) -> Path:
    if not NAME_RE.match(name):
        raise HTTPException(404, "Sicherung nicht gefunden")
    p = backup_dir() / name
    if not p.is_file():
        raise HTTPException(404, "Sicherung nicht gefunden")
    return p


def list_all() -> list[dict]:
    items = [describe(p) for p in backup_dir().iterdir() if p.is_file() and NAME_RE.match(p.name)]
    return sorted(items, key=lambda x: x["created_at"], reverse=True)


def delete(name: str) -> None:
    path_of(name).unlink()


def prune(keep: int) -> list[str]:
    """Älteste automatische Sicherungen über ``keep`` hinaus löschen."""
    autos = [b for b in list_all() if b["kind"] == "auto"]
    gone = [b["name"] for b in autos[keep:]]
    for n in gone:
        (backup_dir() / n).unlink(missing_ok=True)
    return gone


# ── Wiederherstellen ──────────────────────────────────────────────────────────

def _check_db(path: str) -> dict:
    """Prüft eine Datenbankdatei, bevor sie den Bestand ersetzt."""
    try:
        c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        c.row_factory = sqlite3.Row
        try:
            if c.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise HTTPException(400, "Die Datenbank in der Sicherung ist beschädigt (integrity_check)")
            tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            if not {"schema_migrations", "users", "devices"} <= tables:
                raise HTTPException(400, "Die Datei ist keine Portwerk-Datenbank")
            migrations = {r[0] for r in c.execute("SELECT name FROM schema_migrations")}
            newer = sorted(migrations - known_migrations())
            if newer:
                raise HTTPException(400, f"Die Sicherung stammt aus einer neueren Portwerk-Version (unbekannt: {', '.join(newer)})")
            admins = c.execute("SELECT COUNT(*) FROM users WHERE active = 1 AND (',' || roles || ',') LIKE '%,admin,%'").fetchone()[0]
            if not admins:
                raise HTTPException(400, "Die Sicherung enthält keinen aktiven Administrator – danach wäre keine Anmeldung mehr möglich")
            return {"migrations": len(migrations), "devices": c.execute("SELECT COUNT(*) FROM devices").fetchone()[0]}
        finally:
            c.close()
    except sqlite3.DatabaseError:
        raise HTTPException(400, "Die Datei ist keine gültige SQLite-Datenbank")


def restore_file(src: Path, by: str = "") -> dict:
    """Stellt aus einer Sicherung (ZIP, oder nackte SQLite-Datei) wieder her. Vorher wird der aktuelle Stand gesichert."""
    with tempfile.TemporaryDirectory(dir=backup_dir()) as tmp:
        new_db, tls_files = os.path.join(tmp, "opp.db"), {}
        if zipfile.is_zipfile(src):
            with zipfile.ZipFile(src) as z:
                try:
                    info = z.getinfo("opp.db")
                except KeyError:
                    raise HTTPException(400, "Die Sicherung enthält keine Datenbank (opp.db)")
                if info.file_size > MAX_DB_BYTES:
                    raise HTTPException(400, "Die Datenbank in der Sicherung ist zu groß")
                with z.open(info) as fin, open(new_db, "wb") as fout:
                    fout.write(fin.read())
                for n in z.namelist():                                   # nur flache Dateinamen unter tls/ (kein Pfad-Ausbruch)
                    base = n[4:] if n.startswith("tls/") else ""
                    if base and "/" not in base and "\\" not in base and base not in (".", ".."):
                        tls_files[base] = z.read(n)
        else:
            with open(src, "rb") as fin, open(new_db, "wb") as fout:
                fout.write(fin.read())
        stats = _check_db(new_db)
        os.chmod(new_db, 0o600)
        with db._lock:                                                   # ab hier keine Schreibzugriffe anderer Anfragen
            safety = create("before-restore", by)                        # aktueller Stand – falls die Wiederherstellung ein Irrtum war
            for suffix in ("-journal", "-wal", "-shm"):
                Path(db.db_path() + suffix).unlink(missing_ok=True)
            os.replace(new_db, db.db_path())
            if tls_files:
                tls_dir().mkdir(parents=True, exist_ok=True)
                for f in tls_dir().iterdir():
                    if f.is_file():
                        f.unlink()
                for name, data in tls_files.items():
                    p = tls_dir() / name
                    p.write_bytes(data)
                    os.chmod(p, 0o600)
            applied = db.migrate()                                       # ältere Sicherung auf den aktuellen Stand bringen
    from . import auth
    auth._sessions.clear()                                               # Benutzer können sich geändert haben: alle neu anmelden
    return {**stats, "migrated": applied, "tls": bool(tls_files), "safety_backup": safety["name"]}


# ── Automatik ─────────────────────────────────────────────────────────────────

def run_auto_if_due(now: Optional[float] = None) -> Optional[dict]:
    s = get_settings()
    if not s["auto"]:
        return None
    lt = time.localtime(now or time.time())
    if lt.tm_hour < s["hour"]:
        return None
    today = time.strftime("%Y%m%d", lt)
    if any(b["name"].startswith(f"portwerk-auto-{today}-") for b in list_all()):
        return None
    b = create("auto", "automatisch", now)
    prune(s["keep"])
    from . import audit, backup_targets
    audit.log("system", "backup.auto", "backup", b["name"], f"{b['size']} Bytes")
    backup_targets.push_all(backup_dir() / b["name"])                    # externe Ziele (Fehler stehen im Status der Ziele)
    return b


def start_background(interval: float = 600.0) -> None:
    global _bg_started
    if _bg_started or not settings.backup_background:
        return
    _bg_started = True

    def loop() -> None:
        time.sleep(60)
        while True:
            try:
                run_auto_if_due()
            except Exception:                                            # Thread darf nie sterben
                log.exception("Automatische Sicherung")
            time.sleep(interval)

    threading.Thread(target=loop, daemon=True, name="backup-auto").start()
