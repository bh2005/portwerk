"""„Nicht gesehen seit …“: je dokumentierter Verbindung „zuletzt gesehen“ und „fehlt seit“ über mehrere LLDP-Importe;
Anzeige im Soll/Ist-Abgleich und im Aufräumbericht (älteste zuerst, „alt“ ab X Tagen)."""
import time
from types import SimpleNamespace

import pytest

from test_compare import nb

DAY = 86400


@pytest.fixture()
def lab(client, admin, monkeypatch):
    from app import compare
    clock = [time.time() - 30 * DAY]
    monkeypatch.setattr(compare, "time", SimpleNamespace(time=lambda: clock[0]))
    s = client.post("/api/sites", headers=admin, json={"code": "S1", "name": "Werk"}).json()["id"]
    rack = client.post("/api/locations", headers=admin, json={"site_id": s, "kind": "rack", "name": "R1", "rack_units": 20}).json()["id"]

    def dev(name, ports):
        d = client.post("/api/devices", headers=admin, json={"hostname": name, "type": "switch", "location_id": rack}).json()
        return {"id": d["id"], **{n: client.post(f"/api/devices/{d['id']}/ports", headers=admin, json={"name": n}).json()["id"] for n in ports}}
    sw1, sw2, sw3 = dev("sw1", ["Gi1", "Gi2"]), dev("sw2", ["Gi1", "Gi2"]), dev("sw3", ["Gi1"])
    for a, b in ((sw1["Gi1"], sw2["Gi1"]), (sw1["Gi2"], sw2["Gi2"])):
        assert client.put(f"/api/ports/{a}/cable", headers=admin, json={"port_b_id": b}).status_code == 200
    return {"clock": clock, "sw1": sw1, "sw2": sw2, "sw3": sw3}


def at(lab, days_ago, data):
    from app import compare
    lab["clock"][0] = time.time() - days_ago * DAY
    compare.store(data)


def seen(port_id):
    from app import db
    return db.row("SELECT * FROM link_seen WHERE port_id = ?", (port_id,))


BOTH = {"sw1": [nb("Gi1", "sw2", "Gi1"), nb("Gi2", "sw2", "Gi2")], "sw2": [nb("Gi1", "sw1", "Gi1"), nb("Gi2", "sw1", "Gi2")]}
ONLY_GI2 = {"sw1": [nb("Gi2", "sw2", "Gi2")], "sw2": [nb("Gi2", "sw1", "Gi2")]}


def test_missing_since_survives_imports_and_clears(client, admin, lab):
    at(lab, 30, BOTH)
    s1, s2 = lab["sw1"]["Gi1"], lab["sw2"]["Gi1"]
    assert seen(s1)["missing_since"] is None and seen(s2)["last_ok"] == pytest.approx(time.time() - 30 * DAY, abs=60)   # beide Enden
    at(lab, 20, ONLY_GI2)                                                                   # ab hier fehlt Gi1
    at(lab, 5, ONLY_GI2)
    r = seen(s1)
    assert r["missing_since"] == pytest.approx(time.time() - 20 * DAY, abs=60) and r["last_ok"] == pytest.approx(time.time() - 30 * DAY, abs=60)
    rows = {(x["device"], x["port"]): x for x in client.get("/api/compare", headers=admin).json()["rows"]}
    assert rows[("sw1", "Gi1")]["status"] == "not_seen" and rows[("sw1", "Gi1")]["missing_since"] == pytest.approx(r["missing_since"])
    rep = client.get("/api/cleanup?days=14", headers=admin).json()
    ns = rep["not_seen"]
    assert [(x["device"], x["age_days"], x["old"]) for x in ns] == [("sw1", 20, True), ("sw2", 20, True)]
    assert client.get("/api/cleanup?days=30", headers=admin).json()["not_seen"][0]["old"] is False
    at(lab, 1, BOTH)                                                                        # wieder gesehen
    assert seen(s1)["missing_since"] is None and seen(s1)["last_ok"] == pytest.approx(time.time() - DAY, abs=60)


def test_peer_change_restarts_and_removed_cable_drops(client, admin, lab):
    at(lab, 30, BOTH)
    at(lab, 20, ONLY_GI2)
    g1 = lab["sw1"]["Gi1"]
    assert client.put(f"/api/ports/{g1}/cable", headers=admin, json={"port_b_id": lab["sw3"]["Gi1"]}).status_code == 200
    at(lab, 3, {**ONLY_GI2, "sw3": []})                                                     # neues Gegenüber, ebenfalls nicht gesehen
    r = seen(g1)
    assert r["peer_port_id"] == lab["sw3"]["Gi1"] and r["missing_since"] == pytest.approx(time.time() - 3 * DAY, abs=60) and r["last_ok"] is None
    assert seen(lab["sw2"]["Gi1"]) is None                                                  # sw2:Gi1 ist nicht mehr dokumentiert
