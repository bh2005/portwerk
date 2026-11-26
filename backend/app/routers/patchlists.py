"""Patchlisten: mehrere Patchaufträge zu einer gemeinsamen Arbeitsliste zusammenfassen (nach Ort oder nach Auftrag geordnet)."""
from __future__ import annotations

import csv
import io
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from .. import audit, db
from ..auth import Principal, current_principal
from . import masterdata, workorders

router = APIRouter(prefix="/api/patchlists", tags=["patchlisten"])

MAX_ORDERS = 50
ITEM_STATUS = {"open": "offen", "done": "erledigt", "deviation": "Abweichung"}


def _ids(raw: str) -> list[int]:
    try:
        ids = sorted({int(x) for x in raw.split(",") if x.strip()})
    except ValueError:
        raise HTTPException(400, "ids: Komma-getrennte Auftrags-IDs")
    if not ids:
        raise HTTPException(400, "Mindestens einen Patchauftrag angeben")
    if len(ids) > MAX_ORDERS:
        raise HTTPException(400, f"Höchstens {MAX_ORDERS} Aufträge auf einmal")
    return ids


def _end(o: dict, which: str) -> tuple[str, str]:
    """(Beschriftung, Ort) eines Endes einer Position; bei Geräte-Positionen das Gerät."""
    p = o["port_a"] if which == "a" else o["port_b"]
    if p:
        d = db.row("SELECT location_id FROM devices WHERE id = ?", (p["device_id"],))
        return f"{p['device_hostname']}:{p['name']}", masterdata.location_path(d["location_id"]) if d else ""
    if which == "a" and o.get("wan"):
        return f"WAN {o['wan']['name']}" + (f" ({o['wan']['circuit_id']})" if o["wan"]["circuit_id"] else ""), o["wan"]["site_a"]
    if which == "b" and o.get("wan"):
        return o["wan"]["site_b"], ""
    if which == "a" and o["device"]:
        d = db.row("SELECT location_id FROM devices WHERE id = ?", (o["device"]["id"],))
        return o["device"]["hostname"], masterdata.location_path(d["location_id"]) if d else ""
    return "", ""


def _unit(port: Optional[dict]) -> Optional[int]:
    if not port:
        return None
    r = db.row("SELECT rack_position FROM devices WHERE id = ?", (port["device_id"],))
    return r["rack_position"] if r else None


def build(ids: list[int], group: str, only_open: bool, me: Principal) -> dict:
    if group not in ("location", "order", "none"):
        raise HTTPException(400, "group: location, order oder none")
    orders, items = [], []
    for wid in ids:
        w = workorders._wo_or_404(wid, me)                            # unsichtbare Aufträge: 404
        orders.append({"id": w["id"], "number": w["number"], "title": w["title"], "status": w["status"],
                       "status_label": workorders.STATUS_LABELS.get(w["status"], w["status"]), "progress": workorders._progress(w["id"]),
                       "depends_on": workorders._wo_ref(w["depends_on"])})
        for it in db.rows("SELECT * FROM workitems WHERE workorder_id = ? ORDER BY idx, id", (wid,)):
            if only_open and it["item_status"] != "open":
                continue
            o = workorders._item_out(it)
            a, a_loc = _end(o, "a")
            b, b_loc = _end(o, "b")
            if o["action"] == "disconnect" and not b and o["port_a"]:       # Trennen: was steckt jetzt am anderen Ende?
                peer = db.row("""SELECT p.name, d.hostname, d.location_id FROM cables c
                                 JOIN ports p ON p.id = CASE WHEN c.port_a_id = :pid THEN c.port_b_id ELSE c.port_a_id END
                                 JOIN devices d ON d.id = p.device_id
                                 WHERE c.port_a_id = :pid OR c.port_b_id = :pid""", {"pid": o["port_a"]["id"]})
                if peer:
                    b, b_loc = f"{peer['hostname']}:{peer['name']}", masterdata.location_path(peer["location_id"]) if peer["location_id"] else ""
            items.append({
                "id": it["id"], "workorder_id": w["id"], "order": w["number"], "order_status": w["status"], "action": o["action"],
                "action_label": o["action_label"], "a": a, "a_location": a_loc, "b": b, "b_location": b_loc,
                "old_b": (f"{o['old_port_b']['device_hostname']}:{o['old_port_b']['name']}" if o.get("old_port_b") else ""),
                "a_unit": _unit(o["port_a"]), "b_unit": _unit(o["port_b"]), "cfg_text": o["cfg_text"],                # Höheneinheit im Rack (Suche vor Ort)
                "a_device_id": o["port_a"]["device_id"] if o["port_a"] else None, "b_device_id": o["port_b"]["device_id"] if o["port_b"] else None,
                "cable_label": it["cable_label"], "cable_type": it["cable_type"] if it["cable_type"] != "other" else "", "length_m": it["length_m"],
                "color": it["color"], "note": it["note"], "item_status": it["item_status"], "deviation_note": it["deviation_note"],
                "executed_by": it["executed_by"], "executed_at": it["executed_at"], "idx": it["idx"],
            })
    nk = masterdata._natural_key
    if group == "location":                                           # Arbeitsreihenfolge: nach Ort (Rack/Raum), Gerät, Port
        items.sort(key=lambda x: (nk(x["a_location"] or "~"), nk(x["a"]), x["order"], x["idx"]))
        for x in items:
            x["group"] = x["a_location"] or "(ohne Ort)"
    elif group == "order":
        items.sort(key=lambda x: (x["order"], x["idx"]))
        for x in items:
            x["group"] = x["order"]
    else:
        for x in items:
            x["group"] = ""
    summary = {"total": len(items), "done": sum(1 for x in items if x["item_status"] == "done"),
               "deviation": sum(1 for x in items if x["item_status"] == "deviation"),
               "by_action": {k: sum(1 for x in items if x["action"] == k) for k in sorted({x["action"] for x in items})}}
    return {"orders": orders, "items": items, "group": group, "summary": summary}


@router.get("")
def patchlist(ids: str, group: str = "location", only_open: bool = False, me: Principal = Depends(current_principal)):
    """Gemeinsame Liste aller Positionen der gewählten Aufträge, geordnet nach Ort (Standard), nach Auftrag oder unsortiert."""
    return build(_ids(ids), group, only_open, me)


def patchlist_csv(data: dict, lang: str = "de") -> str:
    from .. import i18n
    t = lambda s: i18n.t(lang, s)                                                               # noqa: E731
    buf = io.StringIO()
    wr = csv.writer(buf, delimiter=";")
    wr.writerow([t("Patchliste"), ", ".join(o["number"] for o in data["orders"]), time.strftime("%d.%m.%Y %H:%M")])
    wr.writerow([])
    wr.writerow([t(x) for x in ("Nr", "Ort", "Auftrag", "Aktion", "Gerät/Port A", "Gerät/Port B", "Ort B", "Kabelnummer", "Kabelart", "Länge (m)", "Farbe",
                                "Konfiguration", "Notiz", "Status", "Erledigt von", "Erledigt am", "erledigt ☐")])
    for n, x in enumerate(data["items"], 1):
        done = time.strftime("%d.%m.%Y %H:%M", time.localtime(x["executed_at"])) if x["executed_at"] else ""
        wr.writerow([n, x["a_location"], x["order"], t(x["action_label"]), x["a"], x["b"], x["b_location"], x["cable_label"], x["cable_type"],
                     x["length_m"] or "", x["color"], x["cfg_text"], x["note"], t(ITEM_STATUS.get(x["item_status"], "")), x["executed_by"], done, ""])
    return buf.getvalue()


@router.get("/export")
def patchlist_export(ids: str, group: str = "location", only_open: bool = False, me: Principal = Depends(current_principal)):
    """Patchliste als CSV (Semikolon, UTF-8 mit BOM – öffnet direkt in Excel)."""
    data = build(_ids(ids), group, only_open, me)
    audit.log(me.name, "patchlist.export", "workorder", ",".join(str(o["id"]) for o in data["orders"]), f"{data['summary']['total']} Positionen")
    from .. import i18n
    lang = i18n.principal_lang(me)
    return Response("\ufeff" + patchlist_csv(data, lang), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{i18n.t(lang, "patchliste.csv")}"'})
