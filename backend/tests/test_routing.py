"""Autorouting: fehlende Patchungen zwischen Quell- und Zielport finden und als Patchauftrag planen."""
import pytest

from conftest import login, make_user


@pytest.fixture()
def plant(client, admin):
    """Raum R mit Rack1 (Server, pp1) und Rack3 (sw3, pp3); Trunks pp1:B1–pp3:B1 und pp1:B2–pp3:B2; zweiter Raum R2 ohne Verbindung."""
    post = lambda path, **j: client.post(path, headers=admin, json=j)                       # noqa: E731
    site = post("/api/sites", code="RT", name="Routing").json()["id"]
    loc = lambda name, kind, parent=None: post("/api/locations", site_id=site, name=name, kind=kind, parent_id=parent, **({"rack_units": 42} if kind == "rack" else {})).json()["id"]  # noqa: E731
    room, room2 = loc("R", "room"), loc("R2", "room")
    rack1, rack2, rack3, rack9 = loc("Rack1", "rack", room), loc("Rack2", "rack", room), loc("Rack3", "rack", room), loc("Rack9", "rack", room2)
    ids = {}

    def dev(host, typ, rack, ports, status="active"):
        d = post("/api/devices", hostname=host, type=typ, location_id=rack, status=status).json()["id"]
        ids[host] = {n: post(f"/api/devices/{d}/ports", name=n).json()["id"] for n in ports}
        ids[host]["_id"] = d
        return ids[host]

    srv = dev("srv1", "server", rack1, ["NIC1", "NIC2"])
    pp1 = dev("pp1", "patchpanel", rack1, [f"{x}{i}" for i in range(1, 5) for x in "FB"])
    pp3 = dev("pp3", "patchpanel", rack3, [f"{x}{i}" for i in range(1, 5) for x in "FB"])
    sw3 = dev("sw3", "switch", rack3, ["Gi1", "Gi2", "Gi3"])
    dev("srv2", "server", rack2, ["NIC1"])                                                  # in Rack2: ohne eigenes Patchfeld
    dev("sw9", "switch", rack9, ["Gi1"])
    dev("pp9", "patchpanel", rack9, ["F1", "B1"])
    for pp in (pp1, pp3, ids["pp9"]):
        for i in range(1, 5 if pp is not ids["pp9"] else 2):
            assert client.put(f"/api/ports/{pp[f'F{i}']}/peer", headers=admin, json={"peer_port_id": pp[f"B{i}"]}).status_code == 200
    cab = lambda a, b: client.put(f"/api/ports/{a}/cable", headers=admin, json={"port_b_id": b, "cable_type": "Cat6"}).status_code      # noqa: E731
    assert cab(pp1["B1"], pp3["B1"]) == 200 and cab(pp1["B2"], pp3["B2"]) == 200
    return {"ids": ids, "site": site, "rack1": rack1, "rack2": rack2, "room": room, "cab": cab, "srv": srv, "sw3": sw3, "pp1": pp1, "pp3": pp3}


def route(client, admin, **kw):
    r = client.post("/api/routing/plan", headers=admin, json={"dry_run": True, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def cord_labels(rt):
    return [(c["a_label"], c["b_label"]) for c in rt["cords"]]


def test_route_via_two_patchpanels(client, admin, plant):
    r = route(client, admin, source_port_id=plant["srv"]["NIC1"], target_port_id=plant["sw3"]["Gi2"])
    rt = r["routes"][0]
    assert cord_labels(rt) == [("srv1:NIC1", "pp1:F1"), ("pp3:F1", "sw3:Gi2")]                  # zwei neue Patchkabel, dazwischen der Trunk
    assert rt["stations"] == 2 and rt["existing_cables"] == 1 and rt["between_racks"] == 0
    assert [s["type"] for s in rt["steps"]] == ["cord", "station", "cable", "station", "cord"]
    assert r["cable_type"] == "Cat6" and len(r["routes"]) >= 2                                   # Alternativen (anderer Trunk)
    assert cord_labels(r["routes"][1]) != cord_labels(rt)


def test_target_already_patched_needs_one_cord(client, admin, plant):
    assert plant["cab"](plant["pp3"]["F1"], plant["sw3"]["Gi2"]) == 200                        # Switch hängt schon am Patchfeld in Rack3
    rt = route(client, admin, source_port_id=plant["srv"]["NIC1"], target_port_id=plant["sw3"]["Gi2"])["routes"][0]
    assert cord_labels(rt) == [("srv1:NIC1", "pp1:F1")] and rt["existing_cables"] == 2          # Trunk + vorhandenes Kabel zum Switch


def test_busy_and_reserved_ports_are_skipped(client, admin, plant):
    assert plant["cab"](plant["pp1"]["F1"], plant["srv"]["NIC2"]) == 200                       # pp1:F1 belegt
    assert client.post("/api/reservations", headers=admin, json={"port_ids": [plant["pp3"]["F1"]], "purpose": "Reserve"}).status_code in (200, 201)
    rt = route(client, admin, source_port_id=plant["ids"]["srv2"]["NIC1"], target_port_id=plant["sw3"]["Gi2"])["routes"][0]
    used = [x for c in cord_labels(rt) for x in c]
    assert "pp1:F1" not in used and "pp3:F1" not in used                                        # belegt bzw. reserviert
    assert rt["between_racks"] >= 1                                                             # srv2 steht in Rack2: Patchkabel zwischen Racks im Raum


def test_no_route_between_rooms(client, admin, plant):
    r = route(client, admin, source_port_id=plant["srv"]["NIC1"], target_port_id=plant["ids"]["sw9"]["Gi1"])
    assert r["routes"] == [] and r["why"]
    resp = client.post("/api/routing/plan", headers=admin, json={"dry_run": False, "source_port_id": plant["srv"]["NIC1"], "target_port_id": plant["ids"]["sw9"]["Gi1"]})
    assert resp.status_code == 409


def test_plan_creates_workorder_for_existing_source(client, admin, plant):
    r = client.post("/api/routing/plan", headers=admin, json={"dry_run": False, "source_port_id": plant["srv"]["NIC1"], "target_port_id": plant["sw3"]["Gi2"],
                                                              "workorder_title": "Server anbinden"})
    assert r.status_code == 200, r.text
    wo = r.json()["workorder"]
    d = client.get(f"/api/workorders/{wo['id']}", headers=admin).json()
    assert d["title"] == "Server anbinden" and d["status"] == "draft"
    assert len(d["items"]) == 2 and all(i["action"] == "connect" for i in d["items"])
    pa = {(i["port_a"]["id"], i["port_b"]["id"]) for i in d["items"]}
    assert pa == {(plant["srv"]["NIC1"], plant["pp1"]["F1"]), (plant["pp3"]["F1"], plant["sw3"]["Gi2"])}
    # die Ports sind jetzt verplant: eine zweite Planung weicht aus bzw. nutzt andere Ports
    rt = route(client, admin, source_port_id=plant["srv"]["NIC2"], target_port_id=plant["sw3"]["Gi3"])["routes"][0]
    assert ("pp1:F1" not in [x for c in cord_labels(rt) for x in c]) and ("pp3:F1" not in [x for c in cord_labels(rt) for x in c])


def test_plan_with_new_planned_device(client, admin, plant):
    nd = {"hostname": "srv-neu", "type": "server", "location_id": plant["rack1"], "nic_count": 2}
    r = route(client, admin, new_device=nd, target_port_id=plant["sw3"]["Gi2"])
    assert r["new_device"] is True and cord_labels(r["routes"][0])[0] == ("srv-neu:NIC1", "pp1:F1")
    assert client.get("/api/devices?q=srv-neu", headers=admin).json()["items"] == []            # Vorschau legt nichts an
    resp = client.post("/api/routing/plan", headers=admin, json={"dry_run": False, "new_device": nd, "target_port_id": plant["sw3"]["Gi2"]})
    assert resp.status_code == 200, resp.text
    out = resp.json()
    dev = client.get(f"/api/devices/{out['device_id']}", headers=admin).json()
    assert dev["hostname"] == "srv-neu" and dev["status"] == "planned" and [p["name"] for p in dev["ports"]] == ["NIC1", "NIC2"]
    d = client.get(f"/api/workorders/{out['workorder']['id']}", headers=admin).json()
    actions = sorted(i["action"] for i in d["items"])
    assert actions == ["connect", "connect", "install_device"]                                 # Einbau + zwei Patchkabel
    assert client.post("/api/routing/plan", headers=admin, json={"dry_run": False, "new_device": nd, "target_port_id": plant["sw3"]["Gi2"]}).status_code == 409   # Hostname vergeben


def test_validation_and_permissions(client, admin, plant):
    post = lambda **j: client.post("/api/routing/plan", headers=admin, json=j).status_code     # noqa: E731
    assert post(target_port_id=plant["sw3"]["Gi2"]) == 400                                       # weder Quelle noch neues Gerät
    assert post(source_port_id=plant["srv"]["NIC1"], new_device={"hostname": "x", "location_id": plant["rack1"]}, target_port_id=plant["sw3"]["Gi2"]) == 400
    assert post(source_port_id=plant["srv"]["NIC1"], target_port_id=plant["pp1"]["F1"]) == 400    # Ziel an Patchfeld
    assert post(source_port_id=plant["srv"]["NIC1"], target_port_id=plant["srv"]["NIC2"]) == 400  # selbes Gerät
    assert post(source_port_id=plant["srv"]["NIC1"], target_port_id=999999) == 404
    make_user(client, admin, "betrachter", roles=("viewer",))
    h = login(client, "betrachter", "Passwort-123")
    assert client.post("/api/routing/plan", headers=h, json={"dry_run": True, "source_port_id": plant["srv"]["NIC1"], "target_port_id": plant["sw3"]["Gi2"]}).status_code == 403
