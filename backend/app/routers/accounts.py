"""Anmeldung, Benutzerverwaltung, API-Zugänge und Audit-Log."""
from __future__ import annotations

import json
import re
import sqlite3
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Security
from pydantic import BaseModel

from .. import audit, auth, db
from ..auth import Principal, current_principal, require_admin, require_user, require_user_admin, session_header
from ..schemas import ChangePassword, LoginRequest, PasswordReset, TokenCreate, UserCreate, UserUpdate
from ..security import hash_password, new_api_token, token_hash, verify_password

router = APIRouter(tags=["konten"])

_NAME_RE = re.compile(r"^[A-Za-z0-9._\-@]{1,64}$")


# ── Anmeldung ─────────────────────────────────────────────────────────────────

@router.post("/auth/login")
def auth_login(body: LoginRequest):
    return auth.login(body.username, body.password)


@router.post("/auth/logout")
def auth_logout(token: Optional[str] = Security(session_header), _: Principal = Depends(require_user)):
    if token:
        auth.logout(token)
    return {"ok": True}


@router.get("/auth/me")
def auth_me(p: Principal = Depends(current_principal)):
    if p.kind == "token":
        return {"kind": "token", "name": p.name, "scope": p.scope}
    u = db.row("SELECT * FROM users WHERE id = ?", (p.user_id,))
    return {"kind": "user", **auth.public_user(u)}


class NotifyPrefsIn(BaseModel):
    confirm_suggest: Optional[bool] = None
    assigned: Optional[bool] = None
    my_orders: Optional[bool] = None
    lldp_problem: Optional[bool] = None
    reservation_expiry: Optional[bool] = None


class UiPrefsIn(BaseModel):
    default_site_id: Optional[int] = None            # None = kein Standard-Standort
    start_page: str = ""                              # leer = Übersicht (am Handy für Techniker: mobile Ansicht)


@router.put("/auth/me/preferences")
def set_my_preferences(body: UiPrefsIn, p: Principal = Depends(require_user)):
    """Standard-Standort und Startseite (gelten auf allen Geräten)."""
    from .. import access
    if body.start_page and body.start_page not in auth.START_PAGES:
        raise HTTPException(400, "Startseite unbekannt")
    if body.default_site_id is not None:
        if not db.row("SELECT id FROM sites WHERE id = ?", (body.default_site_id,)):
            raise HTTPException(404, "Standort nicht gefunden")
        access.require_read(p, body.default_site_id, "Standort")
    prefs = {"default_site_id": body.default_site_id, "start_page": body.start_page}
    db.execute("UPDATE users SET ui_prefs = ? WHERE id = ?", (json.dumps(prefs), p.user_id))
    audit.log(p.name, "user.ui_prefs", "user", p.user_id, json.dumps(prefs))
    return auth.ui_prefs(json.dumps(prefs))


class AbsenceIn(BaseModel):
    start_date: str
    end_date: str
    deputy_id: Optional[int] = None
    note: str = ""


@router.get("/auth/me/absences")
def my_absences(p: Principal = Depends(require_user)):
    from .. import absences
    return {"absences": absences.listing(p.user_id), "represents": absences.represented_by(p.user_id)}


@router.post("/auth/me/absences", status_code=201)
def add_my_absence(body: AbsenceIn, p: Principal = Depends(require_user)):
    """Abwesenheit eintragen; im Zeitraum gehen Benachrichtigungen an die Vertretung."""
    from .. import absences
    a = absences.create(p.user_id, body.start_date, body.end_date, body.deputy_id, body.note, p.name)
    audit.log(p.name, "user.absence", "user", p.user_id, f"{a['start_date']} – {a['end_date']}" + (f", Vertretung {a['deputy']['username']}" if a["deputy"] else ""))
    return a


@router.delete("/auth/me/absences/{aid}")
def delete_my_absence(aid: int, p: Principal = Depends(require_user)):
    if not db.row("SELECT id FROM user_absences WHERE id = ? AND user_id = ?", (aid, p.user_id)):
        raise HTTPException(404, "Abwesenheit nicht gefunden")
    db.execute("DELETE FROM user_absences WHERE id = ?", (aid,))
    audit.log(p.name, "user.absence_delete", "user", p.user_id, str(aid))
    return {"ok": True}


@router.get("/api/users/{uid}/absences")
def user_absences(uid: int, me: Principal = Depends(require_admin)):
    from .. import absences
    return absences.listing(uid)


@router.post("/api/users/{uid}/absences", status_code=201)
def add_user_absence(uid: int, body: AbsenceIn, me: Principal = Depends(require_admin)):
    """Administratoren tragen Abwesenheiten für andere ein (z. B. Krankheit)."""
    from .. import absences
    if not db.row("SELECT id FROM users WHERE id = ?", (uid,)):
        raise HTTPException(404, "Benutzer nicht gefunden")
    a = absences.create(uid, body.start_date, body.end_date, body.deputy_id, body.note, me.name)
    audit.log(me.name, "user.absence", "user", uid, f"{a['start_date']} – {a['end_date']} (eingetragen von {me.name})")
    return a


@router.delete("/api/users/{uid}/absences/{aid}")
def delete_user_absence(uid: int, aid: int, me: Principal = Depends(require_admin)):
    if not db.row("SELECT id FROM user_absences WHERE id = ? AND user_id = ?", (aid, uid)):
        raise HTTPException(404, "Abwesenheit nicht gefunden")
    db.execute("DELETE FROM user_absences WHERE id = ?", (aid,))
    audit.log(me.name, "user.absence_delete", "user", uid, str(aid))
    return {"ok": True}


@router.get("/auth/me/sessions")
def my_sessions(p: Principal = Depends(require_user)):
    return {"active": auth.active_sessions(p.user_id)}


@router.post("/auth/me/logout-others")
def logout_others(p: Principal = Depends(require_user)):
    """Alle anderen Anmeldungen beenden (z. B. nach Verlust eines Geräts); diese Sitzung bekommt ein neues Token."""
    before = auth.active_sessions(p.user_id)
    auth.revoke_sessions(p.user_id)
    token = auth.new_session(p.user_id)
    audit.log(p.name, "auth.logout_others", "user", p.user_id, f"{max(0, before - 1)} andere Anmeldung(en) beendet")
    return {"token": token, "ended": max(0, before - 1)}


@router.put("/auth/me/notifications")
def set_my_notifications(body: NotifyPrefsIn, p: Principal = Depends(require_user)):
    """Eigene E-Mail-Benachrichtigungen an/aus (der zentrale Schalter in Verwaltung → E-Mail bleibt Hauptschalter)."""
    from .. import notifications
    u = db.row("SELECT * FROM users WHERE id = ?", (p.user_id,))
    cur = notifications.prefs(u["notify_prefs"])
    cur.update({k: v for k, v in body.model_dump().items() if v is not None})
    db.execute("UPDATE users SET notify_prefs = ? WHERE id = ?", (json.dumps(cur), u["id"]))
    audit.log(p.name, "user.notify_prefs", "user", u["id"], ", ".join(f"{k}={'an' if v else 'aus'}" for k, v in cur.items()))
    return cur


@router.post("/auth/change-password")
def change_password(body: ChangePassword, p: Principal = Depends(require_user)):
    u = db.row("SELECT * FROM users WHERE id = ?", (p.user_id,))
    if u["source"] != "local":
        raise HTTPException(400, "Das Passwort dieses Kontos wird im Verzeichnisdienst geändert")
    if not verify_password(body.current_password, u["password_hash"]):
        raise HTTPException(401, "Aktuelles Passwort falsch")
    auth.check_password_policy(body.new_password)
    db.execute("UPDATE users SET password_hash = ?, token_version = token_version + 1 WHERE id = ?",
               (hash_password(body.new_password), u["id"]))
    for t in [t for t, s in auth._sessions.items() if s["uid"] == u["id"]]:
        auth._sessions.pop(t, None)
    audit.log(p.name, "auth.password_change", "user", u["id"])
    return {"ok": True, "token": auth.new_session(u["id"])}       # alle anderen Sitzungen sind beendet, diese bleibt gültig


# ── Benutzerverwaltung (globale Administratoren und Bereichs-Administratoren) ─

def _get_user(uid: int) -> dict:
    u = db.row("SELECT * FROM users WHERE id = ?", (uid,))
    if not u:
        raise HTTPException(404, "Benutzer nicht gefunden")
    return u


def _last_admin_guard(u: dict, new_roles: list[str], new_active: bool) -> None:
    """Der letzte aktive Administrator darf weder herabgestuft noch deaktiviert/gelöscht werden."""
    if "admin" in auth.parse_roles(u["roles"]) and u["active"] and ("admin" not in new_roles or not new_active):
        n = db.row("SELECT COUNT(*) AS n FROM users WHERE active = 1 AND id <> ? AND (',' || roles || ',') LIKE '%,admin,%'", (u["id"],))["n"]
        if n == 0:
            raise HTTPException(400, "Der letzte aktive Administrator kann nicht geändert werden")


def _in_my_area(me: Principal, u: dict) -> bool:
    """Darf ich diesen Benutzer sehen? Globale Admins alle; Bereichs-Admins Benutzer mit einer Zuweisung in ihren Standorten."""
    if me.is_admin:
        return True
    return any(s["site_id"] in me.admin_sites for s in auth.user_scopes(u["id"]))


def _fully_mine(me: Principal, u: dict) -> bool:
    """Gehört der Benutzer ausschließlich zu meinem Verwaltungsbereich (keine globale Rolle, keine fremden Standorte)?
    Nur dann darf ich ihn sperren, löschen oder sein Passwort zurücksetzen."""
    if me.is_admin:
        return True
    scopes = auth.user_scopes(u["id"])
    return not auth.parse_roles(u["roles"]) and bool(scopes) and all(s["site_id"] in me.admin_sites for s in scopes)


def _user_for(me: Principal, uid: int) -> dict:
    u = _get_user(uid)
    if not _in_my_area(me, u):
        raise HTTPException(404, "Benutzer nicht gefunden")          # Existenz außerhalb des eigenen Bereichs nicht verraten
    return u


def _user_out(me: Principal, u: dict) -> dict:
    out = auth.public_user(u)
    if not me.is_admin:                                              # Bereichs-Admins sehen nur Zuweisungen ihrer Standorte
        out["scopes"] = [s for s in out["scopes"] if s["site_id"] in me.admin_sites]
        out["limited"] = not _fully_mine(me, u)
    else:
        out["limited"] = False
    return out


def _clean_scopes(me: Principal, items) -> list[tuple[str, int]]:
    """Prüft gewünschte Bereichs-Rechte: bekannte Rolle, vorhandener Standort, bei Bereichs-Admins nur eigene Standorte."""
    out: list[tuple[str, int]] = []
    for it in items:
        if it.role not in auth.ROLES:
            raise HTTPException(400, f"Unbekannte Rolle: {it.role} (erlaubt: {', '.join(auth.ROLES)})")
        if not db.row("SELECT id FROM sites WHERE id = ?", (it.site_id,)):
            raise HTTPException(400, f"Standort {it.site_id} nicht gefunden")
        if not me.is_admin and it.site_id not in me.admin_sites:
            raise HTTPException(403, "Rechte dürfen nur für Standorte vergeben werden, für die du Administrator bist")
        if (it.role, it.site_id) not in out:
            out.append((it.role, it.site_id))
    return out


def _set_manual_scopes(me: Principal, uid: int, wanted: list[tuple[str, int]]) -> None:
    """Ersetzt die manuellen Zuweisungen im eigenen Verwaltungsbereich (global: alle); AD-Zuweisungen bleiben unberührt."""
    cur = db.rows("SELECT id, site_id FROM user_scopes WHERE user_id = ? AND source = 'manual'", (uid,))
    for r in cur:
        if me.is_admin or r["site_id"] in me.admin_sites:
            db.execute("DELETE FROM user_scopes WHERE id = ?", (r["id"],))
    for role, site_id in wanted:
        db.execute("INSERT OR IGNORE INTO user_scopes(user_id, role, site_id, source) VALUES (?,?,?, 'manual')", (uid, role, site_id))


@router.get("/api/users")
def list_users(me: Principal = Depends(require_user_admin)):
    rows = db.rows("SELECT * FROM users ORDER BY username COLLATE NOCASE")
    return [_user_out(me, u) for u in rows if _in_my_area(me, u)]


@router.post("/api/users", status_code=201)
def create_user(body: UserCreate, me: Principal = Depends(require_user_admin)):
    name = body.username.strip()
    if not _NAME_RE.match(name):
        raise HTTPException(400, "Benutzername: 1–64 Zeichen (Buchstaben, Ziffern, . _ - @)")
    if body.roles and not me.is_admin:
        raise HTTPException(403, "Globale Rollen vergeben nur globale Administratoren – bitte Rechte für einen Standort wählen")
    roles = auth.check_roles(body.roles, allow_empty=True)
    scopes = _clean_scopes(me, body.scopes)
    if not roles and not scopes:
        raise HTTPException(400, "Mindestens eine globale Rolle oder eine Berechtigung für einen Standort ist erforderlich")
    auth.check_password_policy(body.password)
    try:
        uid = db.execute("INSERT INTO users(username, full_name, email, roles, source, password_hash, created_at) VALUES (?,?,?,?,?,?,?)",
                         (name, body.full_name.strip(), body.email.strip(), ",".join(roles), "local", hash_password(body.password), time.time()))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Benutzername existiert bereits")
    _set_manual_scopes(me, uid, scopes)
    audit.log(me.name, "user.create", "user", uid, f"{name} [{','.join(roles) or '-'}] Standorte: {_scope_text(scopes)}")
    return _user_out(me, _get_user(uid))


def _scope_text(scopes) -> str:
    return ", ".join(f"{r}@{s}" for r, s in scopes) or "-"


@router.put("/api/users/{uid}")
def update_user(uid: int, body: UserUpdate, me: Principal = Depends(require_user_admin)):
    u = _user_for(me, uid)
    old_roles = auth.parse_roles(u["roles"])
    if body.roles is not None and not me.is_admin and sorted(body.roles) != sorted(old_roles):
        raise HTTPException(403, "Globale Rollen ändern nur globale Administratoren")
    roles = auth.check_roles(body.roles, allow_empty=True) if body.roles is not None else old_roles
    active = body.active if body.active is not None else bool(u["active"])
    if active != bool(u["active"]) and not _fully_mine(me, u):
        raise HTTPException(403, "Dieser Benutzer gehört auch zu anderen Bereichen – Sperren nur durch globale Administratoren")
    _last_admin_guard(u, roles, active)
    wanted = _clean_scopes(me, body.scopes) if body.scopes is not None else None
    db.execute("UPDATE users SET roles=?, active=?, full_name=?, email=? WHERE id=?",
               (",".join(roles), 1 if active else 0, body.full_name.strip() if body.full_name is not None else u["full_name"],
                body.email.strip() if body.email is not None else u["email"], uid))
    if wanted is not None:
        _set_manual_scopes(me, uid, wanted)
    if u["source"] == "local" and not roles and not auth.user_scopes(uid):
        raise HTTPException(400, "Mindestens eine globale Rolle oder eine Berechtigung für einen Standort ist erforderlich")
    if not active or roles != old_roles:
        auth.revoke_sessions(uid)                                # neue Rechte gelten sofort
    audit.log(me.name, "user.update", "user", uid,
              f"{u['username']} [{','.join(roles) or '-'}] aktiv={active}" + (f" Standorte: {_scope_text(wanted)}" if wanted is not None else ""))
    return _user_out(me, _get_user(uid))


@router.post("/api/users/{uid}/reset-password")
def reset_password(uid: int, body: PasswordReset, me: Principal = Depends(require_user_admin)):
    u = _user_for(me, uid)
    if not _fully_mine(me, u):
        raise HTTPException(403, "Dieser Benutzer gehört auch zu anderen Bereichen – nur globale Administratoren dürfen das")
    if u["source"] != "local":
        raise HTTPException(400, "Verzeichnisdienst-Benutzer haben kein lokales Passwort")
    auth.check_password_policy(body.new_password)
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(body.new_password), uid))
    auth.revoke_sessions(uid)
    audit.log(me.name, "user.password_reset", "user", uid, u["username"])
    return {"ok": True}


@router.post("/api/users/{uid}/revoke-sessions")
def revoke_user_sessions(uid: int, me: Principal = Depends(require_user_admin)):
    u = _user_for(me, uid)
    if not _fully_mine(me, u):
        raise HTTPException(403, "Dieser Benutzer gehört auch zu anderen Bereichen – nur globale Administratoren dürfen das")
    auth.revoke_sessions(uid)
    audit.log(me.name, "user.revoke_sessions", "user", uid, u["username"])
    return {"ok": True}


@router.delete("/api/users/{uid}")
def delete_user(uid: int, me: Principal = Depends(require_user_admin)):
    u = _user_for(me, uid)
    if u["id"] == me.user_id:
        raise HTTPException(400, "Das eigene Konto kann nicht gelöscht werden")
    if not _fully_mine(me, u):
        raise HTTPException(403, "Dieser Benutzer gehört auch zu anderen Bereichen – nur globale Administratoren dürfen ihn löschen")
    _last_admin_guard(u, [], False)
    auth.revoke_sessions(uid)
    db.execute("DELETE FROM users WHERE id = ?", (uid,))
    audit.log(me.name, "user.delete", "user", uid, u["username"])
    return {"ok": True}


# ── API-Zugänge (Admin) ───────────────────────────────────────────────────────

def _token_out(t: dict) -> dict:
    return {k: t[k] for k in ("id", "name", "prefix", "scope", "created_by", "created_at", "expires_at", "last_used_at")} | {"revoked": bool(t["revoked"])}


@router.get("/api/tokens")
def list_tokens(_: Principal = Depends(require_admin)):
    return [_token_out(t) for t in db.rows("SELECT * FROM api_tokens ORDER BY id DESC")]


@router.post("/api/tokens", status_code=201)
def create_token(body: TokenCreate, me: Principal = Depends(require_admin)):
    if body.scope not in ("read", "write"):
        raise HTTPException(400, "Umfang muss 'read' oder 'write' sein")
    raw = new_api_token()
    now = time.time()
    tid = db.execute("INSERT INTO api_tokens(name, prefix, token_hash, scope, created_by, created_at, expires_at) VALUES (?,?,?,?,?,?,?)",
                     (body.name.strip(), raw[:10], token_hash(raw), body.scope, me.name, now,
                      now + body.expires_days * 86400 if body.expires_days else None))
    audit.log(me.name, "token.create", "token", tid, f"{body.name} ({body.scope})")
    return {**_token_out(db.row("SELECT * FROM api_tokens WHERE id = ?", (tid,))), "token": raw,
            "hinweis": "Das Token wird nur jetzt angezeigt und kann nicht erneut abgerufen werden."}


@router.delete("/api/tokens/{tid}")
def revoke_token(tid: int, me: Principal = Depends(require_admin)):
    t = db.row("SELECT * FROM api_tokens WHERE id = ?", (tid,))
    if not t:
        raise HTTPException(404, "API-Zugang nicht gefunden")
    db.execute("UPDATE api_tokens SET revoked = 1 WHERE id = ?", (tid,))
    audit.log(me.name, "token.revoke", "token", tid, t["name"])
    return {"ok": True}


# ── Audit-Log ─────────────────────────────────────────────────────────────────

@router.get("/api/audit")
def get_audit(limit: int = 200, offset: int = 0, q: str = "", actor: str = "", action: str = "", entity: str = "",
              date_from: str = "", date_to: str = "", _: Principal = Depends(require_admin)):
    """Audit-Log mit Suche (``q``) und Filtern (Benutzer, Aktion bzw. Präfix, Objektart, Zeitraum); ``offset`` zum Nachladen."""
    for name, v in (("date_from", date_from), ("date_to", date_to)):
        if v:
            try:
                audit.day_start(v)
            except ValueError:
                raise HTTPException(400, f"{name}: Datum im Format JJJJ-MM-TT erwartet")
    return audit.search(q.strip(), actor.strip(), action.strip(), entity.strip(), date_from, date_to, limit, offset)


@router.get("/api/audit/facets")
def get_audit_facets(_: Principal = Depends(require_admin)):
    return audit.facets()
