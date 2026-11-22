"""Arbeitsanweisung als PDF: einzelner Patchauftrag oder Patchliste aus mehreren Aufträgen."""
from __future__ import annotations

from typing import Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response

from .. import audit, mailer, workpdf
from ..auth import Principal, current_principal
from . import masterdata, patchlists, workorders

router = APIRouter(tags=["arbeitsanweisung"])

PRIORITY_LABELS = {"low": "niedrig", "normal": "normal", "high": "hoch", "critical": "kritisch"}
NOT_RELEASED = ("draft", "submitted", "rejected", "rework")


def public_base(base: Optional[str], request: Optional[Request]) -> str:
    """Adresse der Oberfläche für Links/QR-Codes: Parameter, sonst „Öffentliche Adresse“ aus den E-Mail-Einstellungen, sonst die Anfrage."""
    b = (base or mailer.settings().get("public_url") or (str(request.base_url) if request else "")).strip().rstrip("/")
    if not b:
        return ""
    u = urlsplit(b)
    if u.scheme not in ("http", "https") or not u.netloc or u.query or u.fragment:
        raise HTTPException(400, "Basis-URL ungültig (erwartet http(s)://host[:port][/pfad])")
    return b


def _fmt_date(d: Optional[str]) -> str:
    return workpdf._fmt_date(d)


def workorder_pdf(w: dict, me: Principal, base: str) -> bytes:
    data = patchlists.build([w["id"]], "location", False, me)
    assignee = workorders._assignee(w.get("assigned_to"))
    dep = workorders._wo_ref(w.get("depends_on"))
    period = " – ".join(x for x in (_fmt_date(w["planned_from"]), _fmt_date(w["planned_to"])) if x)
    meta = [("Status", workorders.STATUS_LABELS.get(w["status"], w["status"])),
            ("Priorität", PRIORITY_LABELS.get(w["priority"], w["priority"])),
            ("Ort", masterdata.location_path(w["location_id"]) if w["location_id"] else ""),
            ("Zeitraum", period),
            ("Zugewiesen an", (assignee["full_name"] or assignee["username"]) if assignee else ""),
            ("Angelegt von", w["created_by"]),
            ("Freigegeben von", w.get("approved_by", "")),
            ("Positionen", f"{data['summary']['total']} (erledigt: {data['summary']['done']})"),
            ("Voraussetzung", f"Rückbau {dep['number']} zuerst bestätigen (jetzt: {dep['status_label']})" if dep and dep["blocking"] else "")]
    warning = ""
    if w["status"] in NOT_RELEASED:
        warning = "Noch nicht freigegeben – nicht ausführen."
    elif w["status"] == "confirmed":
        warning = "Bereits bestätigt – nur zur Dokumentation."
    elif dep and dep["blocking"]:
        warning = f"Erst ausführen, wenn der Rückbau-Auftrag {dep['number']} bestätigt ist."
    notes = [w["description"], f"Notiz: {w['note']}" if w["note"] else ""]
    return workpdf.render(data, title=f"Arbeitsanweisung {w['number']}", subtitle=w["title"], meta=meta, notes=notes,
                          qr_url=f"{base}/workorders/{w['id']}" if base else "", warning=warning, by=me.name)


def patchlist_pdf(ids: list[int], group: str, only_open: bool, me: Principal) -> tuple[bytes, dict]:
    data = patchlists.build(ids, group, only_open, me)
    numbers = ", ".join(o["number"] for o in data["orders"])
    blocked = [o["number"] for o in data["orders"] if o["status"] in NOT_RELEASED]
    meta = [("Aufträge", numbers), ("Positionen", f"{data['summary']['total']} (erledigt: {data['summary']['done']})"),
            ("Ordnung", {"location": "nach Ort", "order": "nach Auftrag", "none": "unsortiert"}[group]),
            ("Umfang", "nur offene Positionen" if only_open else "")]
    warning = f"Nicht freigegeben – nicht ausführen: {', '.join(blocked)}" if blocked else ""
    pdf = workpdf.render(data, title="Patchliste", subtitle=numbers, meta=meta, notes=[], warning=warning, by=me.name, multi=len(ids) > 1)
    return pdf, data


def _pdf_response(content: bytes, filename: str) -> Response:
    return Response(content, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/api/workorders/{wid}/pdf")
def get_workorder_pdf(wid: int, request: Request, base: Optional[str] = Query(None), me: Principal = Depends(current_principal)):
    """Arbeitsanweisung eines Patchauftrags als PDF (A4 quer, nach Ort gruppiert, mit QR-Code zum Auftrag)."""
    w = workorders._wo_or_404(wid, me)
    content = workorder_pdf(w, me, public_base(base, request))
    audit.log(me.name, "workorder.pdf", "workorder", wid, w["number"])
    return _pdf_response(content, f"{w['number']}-arbeitsanweisung.pdf")


@router.get("/api/patchlists/pdf")
def get_patchlist_pdf(ids: str, group: str = "location", only_open: bool = False, me: Principal = Depends(current_principal)):
    """Patchliste aus mehreren Aufträgen als PDF."""
    content, data = patchlist_pdf(patchlists._ids(ids), group, only_open, me)
    audit.log(me.name, "patchlist.pdf", "workorder", ",".join(str(o["id"]) for o in data["orders"]), f"{data['summary']['total']} Positionen")
    return _pdf_response(content, "patchliste.pdf")
