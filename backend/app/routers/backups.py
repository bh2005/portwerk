"""Verwaltung: Sicherung und Wiederherstellung (nur globale Administratoren)."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import audit, backup
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
    return b


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
