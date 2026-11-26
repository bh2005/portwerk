"""Benachrichtigung: Aufträge und Patchlisten per E-Mail senden, Aufträgen einen Benutzer zuweisen, SMTP-Einstellungen (Verwaltung)."""
from __future__ import annotations

import html as _html
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from .. import absences, access, audit, auth, db, i18n, mailer, notifications
from ..auth import Principal, current_principal, require_admin, require_user
from ..schemas import AssignIn, MailSettingsIn, MailTestIn, PatchlistSendIn, SendIn
from . import documents, masterdata, patchlists, workorders

router = APIRouter(tags=["benachrichtigung"])

SEND_ROLES = ["planer", "freigeber", "techniker", "admin"]
MAX_LISTED = 60                                   # so viele Positionen stehen im Text der E-Mail, der Rest im Anhang/Link


# ── Verwaltung: SMTP ──────────────────────────────────────────────────────────

@router.get("/api/admin/mail")
def get_mail(_: Principal = Depends(require_admin)):
    return mailer.public()


@router.put("/api/admin/mail")
def put_mail(body: MailSettingsIn, me: Principal = Depends(require_admin)):
    out = mailer.save(body.model_dump(exclude_unset=True))
    audit.log(me.name, "settings.mail.save", "settings", "mail", f"aktiv={out['enabled']}, Server={out['host']}:{out['port']}, Domains={','.join(out['allowed_domains']) or 'alle'}")
    return out


@router.post("/api/admin/mail/test")
def test_mail(body: MailTestIn, me: Principal = Depends(require_admin)):
    cfg = mailer.require_enabled()
    to = mailer.check_recipients([body.to], cfg)
    lang = i18n.principal_lang(me)
    mailer.send(cfg, to, i18n.t(lang, "Portwerk: Testnachricht"),
                i18n.t(lang, "Das ist eine Testnachricht von Portwerk, gesendet von {name}.\n\nWenn du sie liest, funktioniert der E-Mail-Versand.", name=me.name))
    audit.log(me.name, "mail.test", "settings", "mail", body.to)
    return {"ok": True, "to": to}


# ── Benutzerverzeichnis für die Auswahl ───────────────────────────────────────

def _site_of_order(w: dict) -> Optional[int]:
    return access.site_of_location(w["location_id"])


def _user_has_access(u: dict, site_id: Optional[int]) -> bool:
    """Darf dieser Benutzer den Auftrag eines Standorts sehen? (globale Rolle oder irgendeine Zuweisung an dem Standort)"""
    if auth.parse_roles(u["roles"]):
        return True
    return site_id is not None and bool(db.row("SELECT 1 AS x FROM user_scopes WHERE user_id = ? AND site_id = ? LIMIT 1", (u["id"], site_id)))


@router.get("/api/directory/users")
def directory(workorder_id: Optional[int] = None, me: Principal = Depends(require_user)):
    """Benutzer zur Auswahl (Empfänger/Zuweisung); mit ``workorder_id`` nur solche, die den Auftrag sehen dürfen. Keine E-Mail-Adressen im Klartext."""
    site = None
    if workorder_id:
        site = _site_of_order(workorders._wo_or_404(workorder_id, me))
    out = []
    for u in db.rows("SELECT * FROM users WHERE active = 1 ORDER BY username COLLATE NOCASE"):
        if workorder_id and not _user_has_access(u, site):
            continue
        roles = auth.parse_roles(u["roles"]) or sorted({r["role"] for r in db.rows("SELECT role FROM user_scopes WHERE user_id = ? AND site_id IS ?", (u["id"], site))})
        out.append({"id": u["id"], "username": u["username"], "full_name": u["full_name"], "has_email": bool(u["email"]), "roles": roles,
                    "absent": absences.info(u["id"])})
    return out


# ── Texte ─────────────────────────────────────────────────────────────────────

def _link(cfg: dict, path: str) -> str:
    return f"{cfg['public_url']}{path}" if cfg.get("public_url") else ""


def _row_text(n: int, a: str, b: str, action: str, label: str, ctype: str) -> str:
    extra = ", ".join(x for x in (label, ctype) if x)
    return f"{n:>3}. {action}: {a}" + (f" → {b}" if b else "") + (f"  [{extra}]" if extra else "")


def _compose(me: Principal, intro: str, message: str, meta: list[tuple[str, str]], link: str, rows: list[tuple], total: int, attached: bool,
             lang: str = "de", items_label: str = "Positionen ({n}):") -> tuple[str, str]:
    """(Text, HTML) einer Auftrags-/Patchlisten-Mail in ``lang``. ``intro`` ist bereits übersetzt; Schlüssel in ``meta`` und Aktionen in ``rows``
    werden hier übersetzt. ``rows``: (Nr, Aktion, A, B, Kabelnummer, Kabelart, Ort)."""
    t = lambda s, **kw: i18n.t(lang, s, **kw)                                                   # noqa: E731
    sender = me.name
    meta = [(t(k), v) for k, v in meta if v]
    rows = [(r[0], t(r[1]), *r[2:]) for r in rows]
    more = total - len(rows)
    lines = [f"{sender} {intro}", ""]
    if message.strip():
        lines += [message.strip(), ""]
    lines += [f"{k}: {v}" for k, v in meta]
    if link:
        lines.append(t("Öffnen: {link}", link=link))
    lines += ["", t(items_label, n=total)]
    lines += [_row_text(r[0], r[2], r[3], r[1], r[4], r[5]) for r in rows]
    if more > 0:
        lines.append(t("… und {n} weitere – vollständige Liste im Anhang." if attached else "… und {n} weitere – vollständige Liste im System.", n=more))
    elif attached:
        lines.append("\n" + t("Die Arbeitsliste liegt im Anhang (PDF zum Drucken, CSV für Excel)."))
    esc = _html.escape
    h = [f"<p>{esc(sender)} {esc(intro)}</p>"]
    if message.strip():
        h.append(f"<p style='white-space:pre-wrap'>{esc(message.strip())}</p>")
    h.append("<table cellpadding='3' style='border-collapse:collapse;font-size:13px'>" + "".join(f"<tr><td style='color:#64748b'>{esc(k)}</td><td>{esc(v)}</td></tr>" for k, v in meta) + "</table>")
    if link:
        h.append(f"<p><a href='{esc(link)}'>{esc(t('Im System öffnen'))}</a></p>")
    h.append(f"<p><b>{esc(t('Positionen ({n})', n=total))}</b></p><table cellpadding='4' style='border-collapse:collapse;font-size:12px;border:1px solid #cbd5e1'>"
             f"<tr style='background:#f1f5f9'><th align=left>{esc(t('Nr'))}</th><th align=left>{esc(t('Aktion'))}</th><th align=left>{esc(t('Seite A'))}</th>"
             f"<th align=left>{esc(t('Seite B'))}</th><th align=left>{esc(t('Kabel'))}</th></tr>"
             + "".join(f"<tr style='border-top:1px solid #e2e8f0'><td>{r[0]}</td><td>{esc(r[1])}</td><td>{esc(r[2])}</td><td>{esc(r[3])}</td><td>{esc(' '.join(x for x in (r[4], r[5]) if x))}</td></tr>" for r in rows)
             + "</table>")
    if more > 0:
        h.append(f"<p>{esc(t('… und {n} weitere – vollständige Liste im Anhang.' if attached else '… und {n} weitere – vollständige Liste im System.', n=more))}</p>")
    return "\n".join(lines), "".join(h)


def _recipients(body: SendIn, cfg: dict, site_ids: list) -> tuple[list[str], list[str]]:
    """E-Mail-Adressen aus Benutzern und freien Adressen. Benutzer ohne Zugriff auf den Standort werden abgelehnt (Datenschutz)."""
    emails, skipped = list(body.emails), []
    for uid in body.user_ids:
        u = db.row("SELECT * FROM users WHERE id = ? AND active = 1", (uid,))
        if not u:
            raise HTTPException(400, f"Benutzer {uid} nicht gefunden")
        if not all(_user_has_access(u, s) for s in site_ids):
            raise HTTPException(400, f"{u['username']} hat keinen Zugriff auf diesen Standort – bitte zuerst Rechte vergeben")
        if not u["email"]:
            skipped.append(u["username"])
        else:
            emails.append(u["email"])
    return mailer.check_recipients(emails, cfg), skipped


# ── Auftrag senden ────────────────────────────────────────────────────────────

@router.post("/api/workorders/{wid}/send")
def send_workorder(wid: int, body: SendIn, me: Principal = Depends(current_principal)):
    """Sendet einen Patchauftrag per E-Mail an Benutzer und/oder freie Adressen (mit Zusammenfassung, Link und optional der Arbeitsliste als CSV)."""
    w = workorders._wo_or_404(wid, me)
    workorders._require_role(me, SEND_ROLES, w)
    cfg = mailer.require_enabled()
    to, skipped = _recipients(body, cfg, [_site_of_order(w)])
    mailer.rate_check(me.name)
    items = [workorders._item_out(i) for i in db.rows("SELECT * FROM workitems WHERE workorder_id = ? ORDER BY idx, id", (wid,))]
    rows = []
    for n, o in enumerate(items[:MAX_LISTED] if body.include_list else [], 1):
        a = f"{o['port_a']['device_hostname']}:{o['port_a']['name']}" if o["port_a"] else (o["device"]["hostname"] if o["device"] else "")
        b = f"{o['port_b']['device_hostname']}:{o['port_b']['name']}" if o["port_b"] else ""
        rows.append((n, o["action_label"], a, b, o["cable_label"], o["cable_type"] if o["cable_type"] != "other" else "", ""))
    loc = db.row("SELECT id FROM locations WHERE id = ?", (w["location_id"],))
    lang = i18n.principal_lang(me)                                         # Versand an mehrere (auch freie) Adressen: Sprache des Absenders
    t = lambda s, **kw: i18n.t(lang, s, **kw)                               # noqa: E731
    meta = [("Auftrag", f"{w['number']} – {w['title']}"), ("Status", t(workorders.STATUS_LABELS.get(w["status"], w["status"]))),
            ("Priorität", t(documents.PRIORITY_LABELS.get(w["priority"], w["priority"]))), ("Ort", masterdata.location_path(loc["id"]) if loc else ""),
            ("Zeitraum", " – ".join(x for x in (w["planned_from"], w["planned_to"]) if x))]
    text, html = _compose(me, t("hat dir den Patchauftrag {number} gesendet.", number=w["number"]), body.message, meta, _link(cfg, f"/workorders/{wid}"), rows, len(items),
                          body.attach_csv or body.attach_pdf, lang)
    att = [(t("{number}-arbeitsliste.csv", number=w["number"]), ("﻿" + workorders.worklist_csv(w, lang)).encode("utf-8"), "text/csv")] if body.attach_csv else []
    if body.attach_pdf:
        att.append((t("{number}-arbeitsanweisung.pdf", number=w["number"]), documents.workorder_pdf(w, me, documents.public_base(None, None), lang), "application/pdf"))
    mailer.send(cfg, to, t("[Portwerk] {number} {title} ({n} Positionen)", number=w["number"], title=w["title"], n=len(items)), text, html, att)
    audit.log(me.name, "workorder.send", "workorder", wid, f"{w['number']} an {', '.join(to)}")
    return {"sent_to": to, "skipped_no_email": skipped, "items": len(items)}


@router.post("/api/patchlists/send")
def send_patchlist(body: PatchlistSendIn, me: Principal = Depends(current_principal)):
    """Sendet eine kombinierte Patchliste (mehrere Aufträge) per E-Mail."""
    ids = sorted(set(body.ids))
    data = patchlists.build(ids, body.group, body.only_open, me)
    sites = []
    for o in data["orders"]:
        w = workorders._wo_or_404(o["id"], me)
        workorders._require_role(me, SEND_ROLES, w)
        sites.append(_site_of_order(w))
    cfg = mailer.require_enabled()
    to, skipped = _recipients(body, cfg, sites)
    mailer.rate_check(me.name)
    items = data["items"]
    rows = [(n, x["action_label"], x["a"], x["b"], x["cable_label"], x["cable_type"], x["a_location"]) for n, x in enumerate(items[:MAX_LISTED] if body.include_list else [], 1)]
    lang = i18n.principal_lang(me)
    t = lambda s, **kw: i18n.t(lang, s, **kw)                               # noqa: E731
    meta = [("Aufträge", ", ".join(f"{o['number']} {o['title']}" for o in data["orders"])),
            ("Sortierung", t({"location": "nach Ort", "order": "nach Auftrag", "none": "Auftragsreihenfolge"}[body.group])),
            ("Fortschritt", t("{a} von {b} erledigt", a=data["summary"]["done"], b=data["summary"]["total"]))]
    link = _link(cfg, f"/patchlist?ids={','.join(str(i) for i in ids)}")
    text, html = _compose(me, t("hat dir eine Patchliste mit {n} Auftrag/Aufträgen gesendet.", n=len(data["orders"])), body.message, meta, link, rows, len(items),
                          body.attach_csv or body.attach_pdf, lang)
    att = [(t("patchliste.csv"), ("﻿" + patchlists.patchlist_csv(data, lang)).encode("utf-8"), "text/csv")] if body.attach_csv else []
    if body.attach_pdf:
        att.append((t("patchliste.pdf"), documents.patchlist_pdf(ids, body.group, body.only_open, me, lang)[0], "application/pdf"))
    mailer.send(cfg, to, t("[Portwerk] Patchliste {numbers} ({n} Positionen)", numbers=", ".join(o["number"] for o in data["orders"]), n=len(items)), text, html, att)
    audit.log(me.name, "patchlist.send", "workorder", ",".join(str(i) for i in ids), f"{len(items)} Positionen an {', '.join(to)}")
    return {"sent_to": to, "skipped_no_email": skipped, "items": len(items)}


# ── Zuweisen ──────────────────────────────────────────────────────────────────

@router.post("/api/workorders/{wid}/assign")
def assign_workorder(wid: int, body: AssignIn, me: Principal = Depends(current_principal)):
    """Weist den Auftrag einem Benutzer zu (er sieht ihn unter „Meine Aufgaben“) und benachrichtigt ihn auf Wunsch per E-Mail."""
    w = workorders._wo_or_404(wid, me)
    workorders._require_role(me, ["planer", "freigeber", "admin"], w)
    u = None
    if body.user_id:
        u = db.row("SELECT * FROM users WHERE id = ? AND active = 1", (body.user_id,))
        if not u:
            raise HTTPException(400, "Benutzer nicht gefunden")
        if not _user_has_access(u, _site_of_order(w)):
            raise HTTPException(400, f"{u['username']} hat keinen Zugriff auf diesen Standort – bitte zuerst Rechte vergeben")
    db.execute("UPDATE workorders SET assigned_to = ?, assigned_at = ?, updated_at = ? WHERE id = ?", (body.user_id, time.time() if u else None, time.time(), wid))
    audit.log(me.name, "workorder.assign", "workorder", wid, f"{w['number']} -> {u['username'] if u else '(niemand)'}")
    out = workorders._wo_out(db.row("SELECT * FROM workorders WHERE id = ?", (wid,)), with_items=True)
    out["notified"], out["notify_note"] = False, ""
    if u and body.notify and u["id"] != me.user_id:
        cfg = mailer.settings()
        if not cfg["enabled"]:
            out["notify_note"] = "E-Mail-Versand ist nicht eingerichtet – keine Benachrichtigung gesendet"
        elif not u["email"]:
            out["notify_note"] = f"{u['username']} hat keine E-Mail-Adresse hinterlegt – keine Benachrichtigung gesendet"
        elif (dep := absences.deputy_for(u["id"])) and dep["email"] and _user_has_access(dep, _site_of_order(w)):
            # abwesend mit Vertretung: die Mail geht an die Vertretung (die Zuweisung bleibt bei der gewählten Person)
            try:
                mailer.check_recipients([dep["email"]], cfg)
                mailer.rate_check(me.name)
                n = db.row("SELECT COUNT(*) AS n FROM workitems WHERE workorder_id = ?", (wid,))["n"]
                until = absences.current(u["id"])["end_date"]
                lang = i18n.user_lang(dep)                                 # Sprache der Vertretung
                t = lambda s, **kw: i18n.t(lang, s, **kw)                   # noqa: E731
                meta = [("Auftrag", f"{w['number']} – {w['title']}"),
                        ("Zugewiesen an", t("{name} (abwesend bis {until})", name=u["full_name"] or u["username"], until=until)), ("Positionen", str(n))]
                text, html = _compose(me, t("hat den Patchauftrag {number} {name} zugewiesen – du erhältst die Nachricht in Vertretung.", number=w["number"],
                                            name=u["full_name"] or u["username"]),
                                      body.message, meta, _link(cfg, f"/workorders/{wid}"), [], n, False, lang)
                if notifications.wants(dep, "assigned"):
                    mailer.send(cfg, [dep["email"]], t("[Portwerk] In Vertretung: {number} {title}", number=w["number"], title=w["title"]), text, html)
                    out["notified"] = True
                out["notify_note"] = f"{u['username']} ist abwesend bis {until} – " + (f"E-Mail an die Vertretung {dep['username']} gesendet" if out["notified"]
                                                                                       else f"die Vertretung {dep['username']} hat diese E-Mails abbestellt")
            except HTTPException as e:
                out["notify_note"] = f"Zugewiesen, aber E-Mail an die Vertretung nicht gesendet: {e.detail}"
        elif not notifications.wants(u, "assigned"):
            out["notify_note"] = f"{u['username']} hat E-Mails bei Zuweisung abbestellt – keine Benachrichtigung gesendet"
        else:
            try:
                mailer.check_recipients([u["email"]], cfg)
                mailer.rate_check(me.name)
                n = db.row("SELECT COUNT(*) AS n FROM workitems WHERE workorder_id = ?", (wid,))["n"]
                lang = i18n.user_lang(u)                                   # Sprache des Empfängers
                t = lambda s, **kw: i18n.t(lang, s, **kw)                   # noqa: E731
                meta = [("Auftrag", f"{w['number']} – {w['title']}"), ("Status", t(workorders.STATUS_LABELS.get(w["status"], w["status"]))), ("Positionen", str(n))]
                text, html = _compose(me, t("hat dir den Patchauftrag {number} zugewiesen.", number=w["number"]), body.message, meta,
                                      _link(cfg, f"/workorders/{wid}"), [], n, False, lang, items_label="Positionen im System ({n}):")
                mailer.send(cfg, [u["email"]], t("[Portwerk] Dir zugewiesen: {number} {title}", number=w["number"], title=w["title"]), text, html)
                out["notified"] = True
            except HTTPException as e:                                    # die Zuweisung bleibt bestehen, nur die Mail ging nicht
                out["notify_note"] = f"Zugewiesen, aber E-Mail nicht gesendet: {e.detail}"
    return out
