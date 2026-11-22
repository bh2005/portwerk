"""Verbindungs-Historie: Beginn/Ende jeder Verbindung, wer/welcher Auftrag sie beendet hat, Abfrage zu einem Zeitpunkt."""
from datetime import datetime

import pytest


@pytest.fixture()
def lab(client, admin):
    s = client.post("/api/sites", headers=admin, json={"code": "W1", "name": "Werk"}).json()
    rack = client.post("/api/locations", headers=admin, json={"site_id": s["id"], "kind": "rack", "name": "R1", "rack_units": 20}).json()["id"]

    def dev(name, ports):
        d = client.post("/api/devices", headers=admin, json={"hostname": name, "type": "switch", "location_id": rack}).json()
        return {"id": d["id"], **{n: client.post(f"/api/devices/{d['id']}/ports", headers=admin, json={"name": n, "medium": "RJ45"}).json()["id"]
                                  for n in ports}}
    return {"sw": dev("sw-1", ["Gi1", "Gi2"]), "pc": dev("pc-1", ["eth0"]), "pc2": dev("pc-2", ["eth0"])}


def connect(client, admin, a, b, label=""):
    r = client.put(f"/api/ports/{a}/cable", headers=admin, json={"port_b_id": b, "cable_label": label})
    assert r.status_code == 200, r.text


def hist(client, admin, **params):
    r = client.get("/api/cable-history", headers=admin, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def set_times(hid, start, end=None):
    from app import db
    db.execute("UPDATE cable_history SET valid_from = ?, valid_to = ? WHERE id = ?", (start, end, hid))


def run_order(client, admin, wid):
    wo = client.get(f"/api/workorders/{wid}", headers=admin).json()
    for act in ("submit", "approve", "start"):
        assert client.post(f"/api/workorders/{wid}/transition/{act}", headers=admin).status_code == 200
    for it in wo["items"]:
        assert client.post(f"/api/workorders/{wid}/items/{it['id']}/execute", headers=admin, json={"item_status": "done"}).status_code == 200
    for act in ("finish", "confirm"):
        assert client.post(f"/api/workorders/{wid}/transition/{act}", headers=admin).status_code == 200


def test_replug_keeps_old_connection_in_history(client, admin, lab):
    gi1 = lab["sw"]["Gi1"]
    connect(client, admin, gi1, lab["pc"]["eth0"], "K-1")
    connect(client, admin, gi1, lab["pc2"]["eth0"], "K-2")                     # umstecken: alte Verbindung endet
    h = hist(client, admin, port_id=gi1)
    assert [e["cable_label"] for e in h] == ["K-2", "K-1"]                     # aktuelle zuerst
    new, old = h
    assert new["active"] and new["valid_to"] is None and new["remote"]["hostname"] == "pc-2"
    assert not old["active"] and old["valid_to"] >= old["valid_from"]
    assert old["local"]["port_id"] == gi1 and old["remote"] == {"port_id": lab["pc"]["eth0"], "port_name": "eth0", "hostname": "pc-1",
                                                                "device_id": lab["pc"]["id"]}
    assert old["ended_by"] == "admin" and old["end_reason"] == "manual" and old["ended_workorder"] is None
    # von der Gegenseite aus gesehen ist „local“ der abgefragte Port
    assert hist(client, admin, port_id=lab["pc"]["eth0"])[0]["local"]["hostname"] == "pc-1"


def test_point_in_time_query(client, admin, lab):
    gi1 = lab["sw"]["Gi1"]
    connect(client, admin, gi1, lab["pc"]["eth0"], "ALT")
    connect(client, admin, gi1, lab["pc2"]["eth0"], "NEU")
    new, old = hist(client, admin, port_id=gi1)
    ts = lambda s: datetime.fromisoformat(s).timestamp()  # noqa: E731
    set_times(old["id"], ts("2026-03-01T08:00"), ts("2026-03-10T12:00"))
    set_times(new["id"], ts("2026-03-10T12:00"))
    assert hist(client, admin, port_id=gi1, at="2026-02-28") == []
    assert [e["cable_label"] for e in hist(client, admin, port_id=gi1, at="2026-03-03")] == ["ALT"]
    assert [e["cable_label"] for e in hist(client, admin, port_id=gi1, at="2026-03-10T11:59")] == ["ALT"]
    assert [e["cable_label"] for e in hist(client, admin, port_id=gi1, at="2026-03-10T12:00")] == ["NEU"]   # Ende exklusiv
    assert [e["cable_label"] for e in hist(client, admin, device_id=lab["sw"]["id"], at="2026-04-01")] == ["NEU"]
    assert client.get("/api/cable-history", headers=admin, params={"port_id": gi1, "at": "gestern"}).status_code == 400


def test_workorder_disconnect_records_order(client, admin, lab):
    gi2 = lab["sw"]["Gi2"]
    connect(client, admin, gi2, lab["pc"]["eth0"])
    wo = client.post("/api/workorders", headers=admin, json={"title": "Trennen"}).json()
    r = client.post(f"/api/workorders/{wo['id']}/items", headers=admin, json={"action": "disconnect", "port_a_id": gi2})
    assert r.status_code == 201, r.text
    run_order(client, admin, wo["id"])
    (e,) = hist(client, admin, port_id=gi2)
    assert not e["active"] and e["end_reason"] == "workorder" and e["ended_workorder"] == {"id": wo["id"], "number": wo["number"]}


def test_workorder_connect_records_creating_order(client, admin, lab):
    wo = client.post("/api/workorders", headers=admin, json={"title": "Neu"}).json()
    client.post(f"/api/workorders/{wo['id']}/items", headers=admin,
                json={"action": "connect", "port_a_id": lab["sw"]["Gi1"], "port_b_id": lab["pc"]["eth0"], "cable_label": "WO-1"})
    run_order(client, admin, wo["id"])
    (e,) = hist(client, admin, port_id=lab["sw"]["Gi1"])
    assert e["active"] and e["workorder"]["number"] == wo["number"] and e["cable_label"] == "WO-1"


def test_deleted_port_keeps_history_with_names(client, admin, lab):
    connect(client, admin, lab["sw"]["Gi1"], lab["pc"]["eth0"], "K-9")
    assert client.delete(f"/api/ports/{lab['pc']['eth0']}", headers=admin).status_code in (200, 204)
    (e,) = hist(client, admin, device_id=lab["sw"]["id"])
    assert not e["active"] and e["end_reason"] == ""                              # Trigger hat das Ende festgehalten
    assert e["remote"]["port_id"] is None and e["remote"]["hostname"] == "pc-1" and e["remote"]["port_name"] == "eth0"


def test_attribute_update_follows_active_entry(client, admin, lab):
    connect(client, admin, lab["sw"]["Gi1"], lab["pc"]["eth0"], "VORHER")
    cid = hist(client, admin, port_id=lab["sw"]["Gi1"])[0]["cable_id"]
    r = client.put(f"/api/cables/{cid}", headers=admin, json={"cable_label": "NACHHER", "cable_type": "other"})
    assert r.status_code == 200, r.text
    assert hist(client, admin, port_id=lab["sw"]["Gi1"])[0]["cable_label"] == "NACHHER"


def test_global_listing_and_access(client, admin, lab):
    from conftest import login, make_user
    connect(client, admin, lab["sw"]["Gi1"], lab["pc"]["eth0"])
    assert len(hist(client, admin)) == 1                                           # global: alle Änderungen
    assert client.get("/api/cable-history", headers=admin, params={"port_id": 99999}).status_code == 404
    make_user(client, admin, "leser", roles=("viewer",))
    viewer = login(client, "leser", "Passwort-123")
    assert client.get("/api/cable-history", headers=viewer, params={"port_id": lab["sw"]["Gi1"]}).status_code == 200
