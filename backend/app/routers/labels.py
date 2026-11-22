"""Kabeletiketten mit QR-Code und die Auflösung eines gescannten Codes.

Der QR-Code enthält die Kabelnummer (``<base>/q/k/<Nummer>``), nicht die interne ID: Etiketten werden oft schon während der
Ausführung eines Auftrags geklebt, also bevor das Kabel im Bestand steht, und ein umgestecktes Kabel behält seine Nummer.
Kabel ohne Nummer bekommen ``<base>/q/c/<ID>``.
"""
from __future__ import annotations

from typing import Optional
from urllib.parse import quote, urlsplit

import segno
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from .. import access, db
from ..auth import Principal, current_principal
from . import workorders

router = APIRouter(prefix="/api/labels", tags=["etiketten"])
MAX_LABELS = 1000


def _base(base: Optional[str], request: Request) -> str:
    b = (base or str(request.base_url)).strip().rstrip("/")
    u = urlsplit(b)
    if u.scheme not in ("http", "https") or not u.netloc or u.query or u.fragment:
        raise HTTPException(400, "Basis-URL ungültig (erwartet http(s)://host[:port][/pfad])")
    return b


def _qr(url: str) -> str:
    return segno.make(url, error="m", micro=False).svg_inline(scale=1, border=2, omitsize=True)


def _url(base: str, label: str, cable_id: Optional[int]) -> Optional[str]:
    if label:
        return f"{base}/q/k/{quote(label, safe='')}"
    return f"{base}/q/c/{cable_id}" if cable_id else None


def _end(hostname: str, port: str, device_id: Optional[int] = None) -> dict:
    return {"hostname": hostname, "port": port, "device_id": device_id}


def _visible_device_ids(me: Principal) -> Optional[set]:
    """``None`` = alle sichtbar."""
    clause, args = access.device_clause(me, "d")
    if not clause:
        return None
    return {r["id"] for r in db.rows(f"SELECT d.id FROM devices d WHERE {clause}", tuple(args))}


CABLE_SQL = """SELECT c.id, c.cable_label, c.cable_type, c.length_m, c.color,
                      da.id AS dev_a, da.hostname AS host_a, pa.name AS port_a, db_.id AS dev_b, db_.hostname AS host_b, pb.name AS port_b
               FROM cables c
               JOIN ports pa ON pa.id = c.port_a_id JOIN devices da ON da.id = pa.device_id
               JOIN ports pb ON pb.id = c.port_b_id JOIN devices db_ ON db_.id = pb.device_id"""


def _cable_dict(r: dict) -> dict:
    return {"cable_id": r["id"], "cable_label": r["cable_label"], "cable_type": r["cable_type"], "length_m": r["length_m"],
            "color": r["color"], "a": _end(r["host_a"], r["port_a"], r["dev_a"]), "b": _end(r["host_b"], r["port_b"], r["dev_b"])}


@router.get("")
def labels(
    request: Request,
    cable_ids: list[int] = Query([], description="Kabel-IDs"),
    device_id: Optional[int] = Query(None, description="alle Kabel an diesem Gerät"),
    workorder_id: Optional[int] = Query(None, description="Positionen „herstellen“/„umstecken“ eines Auftrags (auch vor der Bestätigung)"),
    base: Optional[str] = Query(None, description="Adresse der Oberfläche für den QR-Code, z. B. https://portwerk.example"),
    me: Principal = Depends(current_principal),
):
    """Etikettendaten mit QR-Code (SVG) – die Oberfläche setzt sie in das gewählte Format."""
    b = _base(base, request)
    out: list[dict] = []
    vis = _visible_device_ids(me)

    def visible(r: dict) -> bool:
        return vis is None or r["dev_a"] in vis or r["dev_b"] in vis

    if cable_ids:
        ph = ",".join("?" * len(cable_ids))
        rows = [r for r in db.rows(f"{CABLE_SQL} WHERE c.id IN ({ph}) ORDER BY c.cable_label COLLATE NOCASE, c.id", tuple(cable_ids))
                if visible(r)]
        out += [{**_cable_dict(r), "source": "cable"} for r in rows]
    if device_id is not None:
        if not db.row("SELECT id FROM devices WHERE id = ?", (device_id,)):
            raise HTTPException(404, "Gerät nicht gefunden")
        access.require_read(me, access.site_of_device(device_id), "Gerät")
        rows = db.rows(f"{CABLE_SQL} WHERE da.id = ? OR db_.id = ? ORDER BY c.cable_label COLLATE NOCASE, c.id", (device_id, device_id))
        for r in rows:
            d = _cable_dict(r)
            if r["dev_a"] != device_id:                                  # eigenes Gerät zuerst
                d["a"], d["b"] = d["b"], d["a"]
            out.append({**d, "source": "cable"})
    if workorder_id is not None:
        workorders._wo_or_404(workorder_id, me)
        for it in db.rows("""SELECT i.id, i.cable_label, i.cable_type, i.length_m, i.color,
                                    da.id AS dev_a, da.hostname AS host_a, pa.name AS port_a, db_.id AS dev_b, db_.hostname AS host_b, pb.name AS port_b
                             FROM workitems i
                             JOIN ports pa ON pa.id = i.port_a_id JOIN devices da ON da.id = pa.device_id
                             JOIN ports pb ON pb.id = i.port_b_id JOIN devices db_ ON db_.id = pb.device_id
                             WHERE i.workorder_id = ? AND i.action IN ('connect', 'move') ORDER BY i.idx, i.id""", (workorder_id,)):
            out.append({"cable_id": None, "workitem_id": it["id"], "cable_label": it["cable_label"], "cable_type": it["cable_type"],
                        "length_m": it["length_m"], "color": it["color"], "source": "workitem",
                        "a": _end(it["host_a"], it["port_a"], it["dev_a"]), "b": _end(it["host_b"], it["port_b"], it["dev_b"])})
    if len(out) > MAX_LABELS:
        raise HTTPException(400, f"Zu viele Etiketten auf einmal (höchstens {MAX_LABELS})")
    for e in out:
        e["url"] = _url(b, e["cable_label"], e.get("cable_id"))
        e["qr_svg"] = _qr(e["url"]) if e["url"] else None                # Position ohne Nummer: kein eindeutiges Ziel
    return out


@router.get("/resolve")
def resolve(label: Optional[str] = Query(None, max_length=200), cable_id: Optional[int] = None,
            me: Principal = Depends(current_principal)):
    """Ziel eines gescannten Etiketts: wo steckt das Kabel jetzt, ist es geplant, wo steckte es früher?"""
    if not label and cable_id is None:
        raise HTTPException(400, "Kabelnummer oder Kabel-ID angeben")
    vis = _visible_device_ids(me)
    cond, arg = ("c.cable_label = ?", label) if label else ("c.id = ?", cable_id)
    cables = [_cable_dict(r) for r in db.rows(f"{CABLE_SQL} WHERE {cond} ORDER BY c.id", (arg,))
              if vis is None or r["dev_a"] in vis or r["dev_b"] in vis]

    planned = []
    if label:
        for it in db.rows("""SELECT i.id, i.action, i.item_status, i.port_a_id, i.port_b_id, w.id AS wid
                             FROM workitems i JOIN workorders w ON w.id = i.workorder_id
                             WHERE i.cable_label = ? AND i.action IN ('connect', 'move')
                               AND w.status IN ('draft', 'submitted', 'approved', 'in_progress', 'done', 'rework')
                             ORDER BY w.id, i.idx""", (label,)):
            w = db.row("SELECT * FROM workorders WHERE id = ?", (it["wid"],))
            if not workorders._wo_visible(me, w):
                continue
            pa, pb = workorders._port_info(it["port_a_id"]), workorders._port_info(it["port_b_id"])
            planned.append({"workorder": {"id": w["id"], "number": w["number"], "title": w["title"],
                                          "status_label": workorders.STATUS_LABELS.get(w["status"], w["status"])},
                            "action_label": workorders.ACTION_LABELS.get(it["action"], it["action"]), "item_status": it["item_status"],
                            "a": _end(pa["device_hostname"], pa["name"], pa["device_id"]) if pa else None,
                            "b": _end(pb["device_hostname"], pb["name"], pb["device_id"]) if pb else None})

    hcond, harg = ("h.cable_label = ?", label) if label else ("h.cable_id = ?", cable_id)
    history = []
    for h in db.rows(f"""SELECT h.*, pa.device_id AS dev_a, pb.device_id AS dev_b, we.number AS ended_wo
                         FROM cable_history h LEFT JOIN ports pa ON pa.id = h.port_a_id LEFT JOIN ports pb ON pb.id = h.port_b_id
                         LEFT JOIN workorders we ON we.id = h.ended_workorder_id
                         WHERE {hcond} AND h.valid_to IS NOT NULL ORDER BY h.valid_to DESC LIMIT 50""", (harg,)):
        if vis is not None and h["dev_a"] not in vis and h["dev_b"] not in vis:
            continue                                                     # gelöschte Ports: nur mit globaler Sicht
        history.append({"cable_id": h["cable_id"], "cable_label": h["cable_label"], "valid_from": h["valid_from"], "valid_to": h["valid_to"],
                        "a": _end(h["host_a"], h["port_a_name"], h["dev_a"]), "b": _end(h["host_b"], h["port_b_name"], h["dev_b"]),
                        "ended_by": h["ended_by"], "ended_workorder": h["ended_wo"]})
    return {"label": label, "cable_id": cable_id, "cables": cables, "planned": planned, "history": history}
