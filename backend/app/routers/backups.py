"""Verwaltung: Sicherung und Wiederherstellung (nur globale Administratoren)."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import audit, backup, backup_targets
from ..auth import Principal, require_admin

router = APIRouter(prefix="/api/admin/backups", tags=["verwaltung"])
MAX_UPLOAD = 2 * 1024 ** 3


class BackupSettingsIn(BaseModel):
    auto: bool = True
    hour: int = Field(2, ge=0, le=23)
    keep: int = Field(14, ge=1, le=365)


class RestoreIn(BaseModel):
    confirm: bool = Field(False, description="Muss true sein: der aktuelle Bestand wird ersetzt")


def _need_confirm(confirm: bool) -> None:
    if not confirm:
        raise HTTPException(400, "Wiederherstellung ersetzt den gesamten Bestand – bitte ausdrücklich bestätigen (confirm=true)")


@router.get("")
def list_backups(_: Principal = Depends(require_admin)):
    return {"settings": backup.get_settings(), "items": backup.list_all()}


@router.put("/settings")
def put_settings(body: BackupSettingsIn, me: Principal = Depends(require_admin)):
    out = backup.save_settings(body.auto, body.hour, body.keep)
    audit.log(me.name, "backup.settings", "settings", "backup", f"automatisch={out['auto']}, {out['hour']} Uhr, behalten={out['keep']}")
    return out


@router.post("", status_code=201)
def create_backup(me: Principal = Depends(require_admin)):
    b = backup.create("manual", me.name)
    audit.log(me.name, "backup.create", "backup", b["name"], f"{b['size']} Bytes")
    backup_targets.push_async(backup.backup_dir() / b["name"])                         # externe Ziele im Hintergrund
    return b


# ── Externe Ziele (NAS/NFS-Pfad, S3, WebDAV) ────────────────────────────────

class TargetIn(BaseModel):
    type: Optional[str] = None
    name: Optional[str] = Field(default=None, max_length=80)
    enabled: Optional[bool] = None
    keep: Optional[int] = Field(default=None, ge=1, le=365)
    encrypt: Optional[bool] = None
    passphrase: Optional[str] = Field(default=None, max_length=200)
    verify_tls: Optional[bool] = None
    ca_pem: Optional[str] = Field(default=None, max_length=20000)
    path: Optional[str] = Field(default=None, max_length=300)
    endpoint: Optional[str] = Field(default=None, max_length=300)
    region: Optional[str] = Field(default=None, max_length=60)
    bucket: Optional[str] = Field(default=None, max_length=120)
    prefix: Optional[str] = Field(default=None, max_length=200)
    access_key: Optional[str] = Field(default=None, max_length=200)
    secret_key: Optional[str] = Field(default=None, max_length=300)
    path_style: Optional[bool] = None
    url: Optional[str] = Field(default=None, max_length=300)
    user: Optional[str] = Field(default=None, max_length=120)
    password: Optional[str] = Field(default=None, max_length=300)


class TargetRestoreIn(BaseModel):
    name: str
    confirm: bool = False


@router.get("/targets")
def list_targets(_: Principal = Depends(require_admin)):
    return {"types": backup_targets.TYPES, "items": backup_targets.list_public()}


@router.post("/targets", status_code=201)
def create_target(body: TargetIn, me: Principal = Depends(require_admin)):
    out = backup_targets.save(body.model_dump(exclude_none=True))
    audit.log(me.name, "backup.target.create", "backup", out["id"], f"{out['name']} ({out['type']})")
    return out


@router.put("/targets/{tid}")
def update_target(tid: str, body: TargetIn, me: Principal = Depends(require_admin)):
    out = backup_targets.save(body.model_dump(exclude_none=True), tid)
    audit.log(me.name, "backup.target.update", "backup", tid, f"{out['name']} ({out['type']})")
    return out


@router.delete("/targets/{tid}")
def delete_target(tid: str, me: Principal = Depends(require_admin)):
    backup_targets.delete(tid)
    audit.log(me.name, "backup.target.delete", "backup", tid)
    return {"ok": True}


@router.post("/targets/{tid}/test")
def test_target(tid: str, _: Principal = Depends(require_admin)):
    return backup_targets.test(tid)


@router.get("/targets/{tid}/items")
def target_items(tid: str, _: Principal = Depends(require_admin)):
    return backup_targets.remote_items(tid)


@router.post("/targets/{tid}/restore")
def restore_from_target(tid: str, body: TargetRestoreIn, me: Principal = Depends(require_admin)):
    _need_confirm(body.confirm)
    with tempfile.TemporaryDirectory(dir=backup.backup_dir()) as tmp:
        src = backup_targets.fetch(tid, body.name, Path(tmp))
        return _restored(me, f"{backup_targets.get(tid)['name']}: {body.name}", backup.restore_file(src, me.name))


@router.post("/{name}/push")
def push_backup(name: str, target: Optional[str] = None, me: Principal = Depends(require_admin)):
    """Eine vorhandene Sicherung (erneut) auf alle aktiven bzw. das angegebene Ziel übertragen."""
    p = backup.path_of(name)
    if not backup_targets.NAME_RE.match(name):
        raise HTTPException(400, "Nur automatische und manuelle Sicherungen werden extern abgelegt")
    res = backup_targets.push_all(p, target)
    if not res:
        raise HTTPException(409, "Kein aktives Sicherungsziel eingerichtet")
    audit.log(me.name, "backup.push", "backup", name, "; ".join(f"{r['target']}: {'ok' if r['ok'] else 'Fehler'}" for r in res))
    return {"results": res}


@router.get("/{name}/download")
def download_backup(name: str, me: Principal = Depends(require_admin)):
    p = backup.path_of(name)
    audit.log(me.name, "backup.download", "backup", name)
    return FileResponse(p, media_type="application/zip", filename=name)


@router.delete("/{name}")
def delete_backup(name: str, me: Principal = Depends(require_admin)):
    backup.delete(name)
    audit.log(me.name, "backup.delete", "backup", name)
    return {"ok": True}


def _restored(me: Principal, source: str, out: dict) -> dict:
    audit.log(me.name, "backup.restore", "backup", source,
              f"Geräte: {out['devices']}, nachgezogene Migrationen: {len(out['migrated'])}, TLS: {out['tls']}, "
              f"vorher gesichert als {out['safety_backup']}")
    return {**out, "relogin": True}


@router.post("/{name}/restore")
def restore_backup(name: str, body: RestoreIn, me: Principal = Depends(require_admin)):
    _need_confirm(body.confirm)
    return _restored(me, name, backup.restore_file(backup.path_of(name), me.name))


@router.post("/restore-upload")
def restore_upload(file: UploadFile = File(...), confirm: bool = False, me: Principal = Depends(require_admin)):
    """Wiederherstellung aus einer hochgeladenen Sicherung (ZIP von Portwerk oder nackte SQLite-Datei)."""
    _need_confirm(confirm)
    fd, tmp = tempfile.mkstemp(dir=backup.backup_dir(), suffix=".upload")
    try:
        with os.fdopen(fd, "wb") as out:
            shutil.copyfileobj(file.file, out, length=1024 * 1024)
        if Path(tmp).stat().st_size > MAX_UPLOAD:
            raise HTTPException(400, "Datei zu groß")
        return _restored(me, file.filename or "Upload", backup.restore_file(Path(tmp), me.name))
    finally:
        Path(tmp).unlink(missing_ok=True)
