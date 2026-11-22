"""LLDP-Prüfung ausgeführter Aufträge: herstellen über ein Patchfeld, trennen, Aktualität der Daten, Abweichung, Auslösung durch den Import."""
import time

import pytest

from test_compare import nb, tree

OVR = {"override_reason": "Test (allein)"}


@pytest.fixture()
def lab(client, admin):
    s = client.post("/api/sites", headers=admin, json={"code": "S1", "name": "Werk"}).json()["id"]
    rack = client.post("/api/locations", headers=admin, json={"site_id": s, "kind": "rack", "name": "R1", "rack_units": 20}).json()["id"]

    def dev(name, dtype, ports, peers=()):
        d = client.post("/api/devices", headers=admin, json={"hostname": name, "type": dtype, "location_id": rack}).json()
        ids = {n: client.post(f"/api/devices/{d['id']}/ports", headers=admin, json={"name": n}).json()["id"] for n in ports}
        for f, b in peers:
            client.put(f"/api/ports/{ids[f]}/peer", headers=admin, json={"peer_port_id": ids[b]})
        return {"id": d["id"], **ids}
    sw = dev("sw1", "switch", ["Gi0/1", "Gi0/2"])
    pf = dev("pf1", "patchpanel", ["P1", "P1-back"], [("P1", "P1-back")])
    pc1 = dev("pc1", "endpoint", ["eth0"])
    pc2 = dev("pc2", "endpoint", ["eth0"])
    assert client.put(f"/api/ports/{pf['P1-back']}/cable", headers=admin, json={"port_b_id": pc1["eth0"]}).status_code == 200   # Dose → PC steht
    assert client.put(f"/api/ports/{sw['Gi0/2']}/cable", headers=admin, json={"port_b_id": pc2["eth0"]}).status_code == 200    # wird getrennt
    return {"sw": sw, "pf": pf, "pc1": pc1, "pc2": pc2}


def run_until_done(client, admin, wid):
    for act in ("submit", "approve", "start"):
        assert client.post(f"/api/workorders/{wid}/transition/{act}", headers=admin, json=OVR).status_code == 200
    for it in client.get(f"/api/workorders/{wid}", headers=admin).json()["items"]:
        client.post(f"/api/workorders/{wid}/items/{it['id']}/execute", headers=admin, json={"item_status": "done"})
    r = client.post(f"/api/workorders/{wid}/transition/finish", headers=admin, json=OVR)
    assert r.status_code == 200
    return r.json()


def order(client, admin, *items):
    wo = client.post("/api/workorders", headers=admin, json={"title": "Prüfling"}).json()
    for it in items:
        assert client.post(f"/api/workorders/{wo['id']}/items", headers=admin, json=it).status_code == 201
    return wo["id"]


def store(neighbors):
    from app import compare
    compare.store(neighbors)


def verify(client, admin, wid):
    r = client.post(f"/api/workorders/{wid}/verify", headers=admin)
    assert r.status_code == 200, r.text
    return r.json()


def test_connect_through_patchpanel(client, admin, lab):
    wid = order(client, admin, {"action": "connect", "port_a_id": lab["sw"]["Gi0/1"], "port_b_id": lab["pf"]["P1"]})
    w = run_until_done(client, admin, wid)
    assert w["lldp_status"] == "none" and w["lldp_detail"][0]["status"] == "unknown"          # noch keine Nachbardaten
    store({"sw1": [nb("GigabitEthernet0/1", "pc1.example.test", "eth0")]})
    r = verify(client, admin, wid)
    assert r["status"] == "ok" and r["items"][0]["ends"] == "sw1:Gi0/1 ↔ pc1:eth0"          # Ende hinter dem Patchfeld gefunden
    detail = client.get(f"/api/workorders/{wid}", headers=admin).json()
    assert detail["lldp_status"] == "ok" and detail["lldp_checked_at"]
    log = client.get("/api/audit", headers=admin).json()
    assert any(e["action"] == "workorder.lldp_ok" for e in (log["items"] if isinstance(log, dict) else log))


def test_stale_data_waits_and_mismatch_is_reported(client, admin, lab):
    from app import db
    store({"sw1": [nb("Gi0/1", "pc1", "eth0")]})
    wid = order(client, admin, {"action": "connect", "port_a_id": lab["sw"]["Gi0/1"], "port_b_id": lab["pf"]["P1"]})
    run_until_done(client, admin, wid)
    db.execute("UPDATE devices SET neighbors_at = ? WHERE hostname = 'sw1'", (time.time() - 3600,))   # vor dem Abhaken gemeldet
    assert verify(client, admin, wid)["status"] == "pending"
    store({"sw1": [nb("Gi0/1", "drucker-7", "p1")]})
    r = verify(client, admin, wid)
    assert r["status"] == "problem" and "drucker-7" in r["items"][0]["text"]


def test_disconnect(client, admin, lab):
    wid = order(client, admin, {"action": "disconnect", "port_a_id": lab["sw"]["Gi0/2"]})
    run_until_done(client, admin, wid)
    store({"sw1": [nb("Gi0/2", "pc2", "eth0")]})
    r = verify(client, admin, wid)
    assert r["status"] == "problem" and r["items"][0]["text"].startswith("noch verbunden")
    store({"sw1": []})
    assert verify(client, admin, wid)["status"] == "ok"


def test_import_triggers_check_and_open_states_only(client, admin, lab):
    wid = order(client, admin, {"action": "connect", "port_a_id": lab["sw"]["Gi0/1"], "port_b_id": lab["pf"]["P1"]})
    run_until_done(client, admin, wid)
    r = client.post("/api/import/checkmk", headers=admin, json={"site_code": "S1", "hosts": [
        {"host": "sw1", "inventory": tree(2, lldp=[nb("Gi0/1", "pc1", "eth0")])}]})
    assert r.status_code == 200 and r.json()["neighbors"]["orders_checked"] >= 1
    assert client.get(f"/api/workorders/{wid}", headers=admin).json()["lldp_status"] == "ok"
    listed = [w for w in client.get("/api/workorders", headers=admin, params={"status": "done"}).json() if w["id"] == wid]
    assert listed[0]["lldp_status"] == "ok"                                                     # Badge in der Liste
    draft = order(client, admin, {"action": "disconnect", "port_a_id": lab["sw"]["Gi0/2"]})                  # Entwurf: wird nicht geprüft
    assert client.post(f"/api/workorders/{draft}/verify", headers=admin).status_code == 409
