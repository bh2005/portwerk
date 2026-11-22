"""Pfad-Verfolgung: Switch → Patchfeld RZ → Patchfeld Etage → Datendose → PC, in beide Richtungen, mit offenen Enden, LLDP und Rechten."""
import pytest

from conftest import login


@pytest.fixture()
def lab(client, admin):
    s = client.post("/api/sites", headers=admin, json={"code": "W1", "name": "Werk"}).json()
    s2 = client.post("/api/sites", headers=admin, json={"code": "W2", "name": "Fremd"}).json()
    loc = lambda sid, name: client.post("/api/locations", headers=admin, json={"site_id": sid, "kind": "rack", "name": name, "rack_units": 20}).json()["id"]  # noqa: E731
    rz, e1, far = loc(s["id"], "RZ"), loc(s["id"], "E1"), loc(s2["id"], "X")

    def dev(name, dtype, rack, ports, peers=(), unit=None):
        d = client.post("/api/devices", headers=admin, json={"hostname": name, "type": dtype, "location_id": rack, "rack_position": unit}).json()
        ids = {n: client.post(f"/api/devices/{d['id']}/ports", headers=admin, json={"name": n, "medium": "RJ45"}).json()["id"] for n in ports}
        for f, b in peers:
            assert client.put(f"/api/ports/{ids[f]}/peer", headers=admin, json={"peer_port_id": ids[b]}).status_code == 200
        return {"id": d["id"], **ids}
    sw = dev("sw-1", "switch", rz, ["Gi1", "Gi2"], unit=10)
    prz = dev("pf-rz", "patchpanel", rz, ["P1", "P1-back", "P2", "P2-back"], [("P1", "P1-back"), ("P2", "P2-back")], unit=5)
    pe1 = dev("pf-e1", "patchpanel", e1, ["P1", "P1-back"], [("P1", "P1-back")])
    do = dev("do-1", "outlet", e1, ["1", "1-back"], [("1", "1-back")])
    pc = dev("pc-1", "endpoint", e1, ["eth0"])
    fx = dev("sw-fremd", "switch", far, ["Gi1"])

    def cab(a, b, **kw):
        r = client.put(f"/api/ports/{a}/cable", headers=admin, json={"port_b_id": b, **kw})
        assert r.status_code == 200, r.text
    cab(sw["Gi1"], prz["P1"], cable_label="K-1", color="blau", length_m=2)
    cab(prz["P1-back"], pe1["P1-back"], cable_label="T-1", cable_type="other")
    cab(pe1["P1"], do["1-back"], cable_label="K-2")
    cab(do["1"], pc["eth0"], cable_label="K-3", color="gelb")
    return {"site": s["id"], "sw": sw, "prz": prz, "pe1": pe1, "do": do, "pc": pc, "fx": fx, "cab": cab}


def path(client, h, pid):
    r = client.get(f"/api/ports/{pid}/path", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_full_chain_from_any_port(client, admin, lab):
    for start in (lab["pc"]["eth0"], lab["sw"]["Gi1"], lab["pe1"]["P1-back"], lab["do"]["1"]):
        p = path(client, admin, start)
        assert [n["device"]["hostname"] for n in p["nodes"]] == ["sw-1", "pf-rz", "pf-e1", "do-1", "pc-1"], start   # Switch links
        assert p["complete"] and p["hops"] == 3 and p["ends"] == ["", ""]
        assert p["summary"] == "sw-1:Gi1 → pc-1:eth0"
        assert [n["ports"][0]["start"] or (len(n["ports"]) > 1 and n["ports"][1]["start"]) for n in p["nodes"]].count(True) == 1
    p = path(client, admin, lab["pc"]["eth0"])
    assert [x["name"] for x in p["nodes"][1]["ports"]] == ["P1", "P1-back"] and p["nodes"][1]["passive"]
    assert [x["name"] for x in p["nodes"][2]["ports"]] == ["P1-back", "P1"]
    assert [lk["label"] for lk in p["links"]] == ["K-1", "T-1", "K-2", "K-3"]
    assert p["links"][0]["color"] == "blau" and p["links"][0]["length_m"] == 2
    assert p["nodes"][0]["device"]["location"] == "W1 / RZ" and p["nodes"][0]["device"]["unit"] == 10


def test_open_end_and_unconnected_port(client, admin, lab):
    client.put(f"/api/ports/{lab['do']['1']}/cable", headers=admin, json={"port_b_id": None})          # PC abgezogen
    p = path(client, admin, lab["sw"]["Gi1"])
    assert not p["complete"] and p["ends"] == ["", "offenes Ende"] and p["nodes"][-1]["device"]["hostname"] == "do-1"
    assert p["lldp"] == []
    p = path(client, admin, lab["sw"]["Gi2"])
    assert len(p["nodes"]) == 1 and p["summary"] == "sw-1:Gi2 (nicht verbunden)" and not p["complete"]


def test_panel_without_peer_is_open_end(client, admin, lab):
    client.put(f"/api/ports/{lab['pe1']['P1-back']}/peer", headers=admin, json={"peer_port_id": None})
    p = path(client, admin, lab["sw"]["Gi1"])
    assert p["ends"][1] == "offenes Ende" and p["nodes"][-1]["device"]["hostname"] == "pf-e1"


def test_loop_is_detected(client, admin, lab):
    lab["cab"](lab["prz"]["P2"], lab["prz"]["P2-back"])          # Rangierkabel vorn ↔ hinten am selben Feld
    p = path(client, admin, lab["prz"]["P2"])
    assert "Schleife in der Verkabelung" in p["ends"]


def test_lldp_check_of_both_ends(client, admin, lab):
    from app import compare
    compare.store({"sw-1": [{"local_port": "GigabitEthernet1", "neighbor_name": "pc-1.example.test", "neighbor_port": "eth0"}]})
    p = path(client, admin, lab["pc"]["eth0"])
    assert p["lldp"][0]["status"] == "ok" and p["lldp"][1]["status"] == "unknown"
    compare.store({"sw-1": [{"local_port": "Gi1", "neighbor_name": "drucker-7", "neighbor_port": "p1"}],
                   "pc-1": [{"local_port": "eth0", "neighbor_name": "sw-1", "neighbor_port": "Gi2"}]})
    p = path(client, admin, lab["pc"]["eth0"])
    assert p["lldp"][0]["status"] == "mismatch" and "drucker-7" in p["lldp"][0]["text"]
    assert p["lldp"][1]["status"] == "port_mismatch"


def test_planned_changes_and_reservations_on_ports(client, admin, lab):
    wo = client.post("/api/workorders", headers=admin, json={"title": "Umbau"}).json()
    client.post(f"/api/workorders/{wo['id']}/items", headers=admin, json={"action": "disconnect", "port_a_id": lab["do"]["1"]})
    client.post("/api/reservations", headers=admin, json={"port_ids": [lab["sw"]["Gi1"]], "purpose": "Kamera"})
    p = path(client, admin, lab["sw"]["Gi1"])
    assert p["nodes"][0]["ports"][0]["reservation"] == "Kamera"
    do_ports = {x["name"]: x for x in p["nodes"][3]["ports"]}
    assert do_ports["1"]["planned"] == [{"workorder": {"id": wo["id"], "number": wo["number"]}, "action": "trennen"}]


def test_foreign_site_is_anonymized(client, admin, lab):
    lab["cab"](lab["sw"]["Gi2"], lab["fx"]["Gi1"], cable_label="WAN-Brücke")
    client.post("/api/users", headers=admin, json={"username": "w1", "password": "Passwort-123", "roles": [],
                                                   "scopes": [{"site_id": lab["site"], "role": "viewer"}]})
    h = login(client, "w1", "Passwort-123")
    p = path(client, h, lab["sw"]["Gi2"])
    assert p["nodes"][1]["device"] == {"id": None, "hostname": "(außerhalb deines Bereichs)", "type": "switch", "status": "active",
                                       "location": "", "unit": None}
    assert p["nodes"][1]["ports"][0]["name"] == "…" and "sw-fremd" not in str(p) and p["lldp"] == []
    assert client.get(f"/api/ports/{lab['fx']['Gi1']}/path", headers=h).status_code == 404
