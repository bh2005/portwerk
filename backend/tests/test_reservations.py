"""Port-Reservierungen: Ports freihalten, Rückfrage beim Verplanen, doppelte Verplanung in Aufträgen, Ablauf, Rechte."""
import pytest

from conftest import login, make_user


@pytest.fixture()
def lab(client, admin):
    s = client.post("/api/sites", headers=admin, json={"code": "W1", "name": "Werk"}).json()
    s2 = client.post("/api/sites", headers=admin, json={"code": "W2", "name": "Fremd"}).json()
    rack = client.post("/api/locations", headers=admin, json={"site_id": s["id"], "kind": "rack", "name": "R1", "rack_units": 20}).json()["id"]
    rack2 = client.post("/api/locations", headers=admin, json={"site_id": s2["id"], "kind": "rack", "name": "R2", "rack_units": 20}).json()["id"]

    def dev(name, ports, loc=rack):
        d = client.post("/api/devices", headers=admin, json={"hostname": name, "type": "switch", "location_id": loc}).json()
        return {"id": d["id"], **{n: client.post(f"/api/devices/{d['id']}/ports", headers=admin, json={"name": n, "medium": "RJ45"}).json()["id"]
                                  for n in ports}}
    return {"site": s["id"], "site2": s2["id"], "sw": dev("sw-1", ["Gi1", "Gi2", "Gi3", "Gi4"]), "pc": dev("pc-1", ["eth0"]),
            "pc2": dev("pc-2", ["eth0"]), "far": dev("sw-far", ["Gi1"], rack2)}


def reserve(client, h, ports, purpose="Kamera-Projekt", **kw):
    return client.post("/api/reservations", headers=h, json={"port_ids": ports, "purpose": purpose, **kw})


def cable(client, h, a, b, **kw):
    return client.post("/api/wizards/cable", headers=h, json={"port_a_id": a, "port_b_id": b, "mode": "direct", **kw})


def test_reserve_list_and_port_info(client, admin, lab):
    r = reserve(client, admin, [lab["sw"]["Gi1"], lab["sw"]["Gi2"]], until="2099-12-31")
    assert r.status_code == 201, r.text
    assert {x["port"] for x in r.json()} == {"Gi1", "Gi2"} and r.json()[0]["reserved_by"] == "admin"
    lst = client.get("/api/reservations", headers=admin).json()
    assert [x["port"] for x in lst] == ["Gi1", "Gi2"] and lst[0]["location"] == "W1 / R1" and not lst[0]["expired"]
    ports = {p["name"]: p for p in client.get(f"/api/devices/{lab['sw']['id']}/ports", headers=admin).json()}
    assert ports["Gi1"]["reservation"]["purpose"] == "Kamera-Projekt" and ports["Gi3"]["reservation"] is None
    again = reserve(client, admin, [lab["sw"]["Gi2"], lab["sw"]["Gi3"]], purpose="Anderes")
    assert again.status_code == 409 and again.json()["detail"]["port_ids"] == [lab["sw"]["Gi2"]]
    assert reserve(client, admin, [lab["sw"]["Gi3"]], until="2001-01-01").status_code == 400


def test_free_port_list_skips_reserved_and_planned(client, admin, lab):
    reserve(client, admin, [lab["sw"]["Gi1"]])
    wo = client.post("/api/workorders", headers=admin, json={"title": "Plan"}).json()
    client.post(f"/api/workorders/{wo['id']}/items", headers=admin, json={"action": "connect", "port_a_id": lab["sw"]["Gi2"], "port_b_id": lab["pc"]["eth0"]})
    r = client.post("/api/wizards/port-list", headers=admin, json={"device_id": lab["sw"]["id"], "only_free": True})
    assert r.status_code == 200, r.text
    assert [p["name"] for p in r.json()["ports"]] == ["Gi3", "Gi4"]
    every = {p["name"]: p for p in client.post("/api/wizards/port-list", headers=admin, json={"device_id": lab["sw"]["id"], "only_free": False}).json()["ports"]}
    assert every["Gi1"]["reserved"] == "Kamera-Projekt" and every["Gi2"]["planned"] == wo["number"]


def test_wizard_asks_and_override_releases(client, admin, lab):
    reserve(client, admin, [lab["sw"]["Gi1"]], purpose="Halle 3")
    r = cable(client, admin, lab["sw"]["Gi1"], lab["pc"]["eth0"])
    d = r.json()["detail"]
    assert r.status_code == 409 and d["code"] == "port_reserved" and d["conflicts"][0]["kind"] == "reservation" and "Halle 3" in d["message"]
    assert cable(client, admin, lab["sw"]["Gi1"], lab["pc"]["eth0"], use_reserved=True, dry_run=True).status_code == 200
    assert len(client.get("/api/reservations", headers=admin).json()) == 1                     # Trockenlauf gibt nichts frei
    assert cable(client, admin, lab["sw"]["Gi1"], lab["pc"]["eth0"], use_reserved=True).status_code == 200
    assert client.get("/api/reservations", headers=admin).json() == []
    log = client.get("/api/audit", headers=admin).json()
    assert any(e["action"] == "reservation.override" for e in (log["items"] if isinstance(log, dict) else log))


def test_direct_cable_and_bulk_respect_reservations(client, admin, lab):
    reserve(client, admin, [lab["pc"]["eth0"]])
    r = client.put(f"/api/ports/{lab['sw']['Gi1']}/cable", headers=admin, json={"port_b_id": lab["pc"]["eth0"]})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "port_reserved"
    r = client.post("/api/wizards/bulk-cables", headers=admin, json={"pairs": [{"port_a_id": lab["sw"]["Gi2"], "port_b_id": lab["pc"]["eth0"]}], "mode": "direct"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "port_reserved"


def test_reservation_for_workorder_and_release_on_confirm(client, admin, lab):
    wo = client.post("/api/workorders", headers=admin, json={"title": "Für mich"}).json()
    other = client.post("/api/workorders", headers=admin, json={"title": "Fremd"}).json()
    reserve(client, admin, [lab["sw"]["Gi1"], lab["pc"]["eth0"]], workorder_id=wo["id"])
    item = {"action": "connect", "port_a_id": lab["sw"]["Gi1"], "port_b_id": lab["pc"]["eth0"]}
    r = client.post(f"/api/workorders/{other['id']}/items", headers=admin, json=item)
    assert r.status_code == 409 and r.json()["detail"]["conflicts"][0]["workorder"]["number"] == wo["number"]
    assert client.post(f"/api/workorders/{wo['id']}/items", headers=admin, json=item).status_code == 201       # eigener Auftrag: keine Rückfrage
    items = client.get(f"/api/workorders/{wo['id']}", headers=admin).json()["items"]
    for act in ("submit", "approve", "start"):
        client.post(f"/api/workorders/{wo['id']}/transition/{act}", headers=admin, json={"override_reason": "Test (allein)"})
    client.post(f"/api/workorders/{wo['id']}/items/{items[0]['id']}/execute", headers=admin, json={"item_status": "done"})
    for act in ("finish", "confirm"):
        assert client.post(f"/api/workorders/{wo['id']}/transition/{act}", headers=admin, json={"override_reason": "Test (allein)"}).status_code == 200
    assert client.get("/api/reservations", headers=admin).json() == []                          # nach Bestätigung aufgehoben


def test_double_planning_in_two_orders(client, admin, lab):
    a = client.post("/api/workorders", headers=admin, json={"title": "Erster"}).json()
    b = client.post("/api/workorders", headers=admin, json={"title": "Zweiter"}).json()
    add = lambda wid, **kw: client.post(f"/api/workorders/{wid}/items", headers=admin, json={"action": "connect", **kw})  # noqa: E731
    assert add(a["id"], port_a_id=lab["sw"]["Gi1"], port_b_id=lab["pc"]["eth0"]).status_code == 201
    r = add(b["id"], port_a_id=lab["sw"]["Gi1"], port_b_id=lab["pc2"]["eth0"])
    c = r.json()["detail"]["conflicts"]
    assert r.status_code == 409 and c[0]["kind"] == "planned" and c[0]["workorder"]["number"] == a["number"]
    assert "verplant" in r.json()["detail"]["message"]
    assert add(b["id"], port_a_id=lab["sw"]["Gi1"], port_b_id=lab["pc2"]["eth0"], use_reserved=True).status_code == 201
    assert add(a["id"], port_a_id=lab["sw"]["Gi2"], port_b_id=lab["sw"]["Gi3"]).status_code == 201         # im selben Auftrag kein Konflikt mit sich selbst


def test_expired_reservation_is_free_and_replaced(client, admin, lab):
    from app import db
    reserve(client, admin, [lab["sw"]["Gi1"]], purpose="Alt")
    db.execute("UPDATE port_reservations SET until = '2020-01-01'")
    assert client.get("/api/reservations", headers=admin, params={"expired": True}).json()[0]["expired"]
    assert cable(client, admin, lab["sw"]["Gi1"], lab["pc"]["eth0"], dry_run=True).status_code == 200      # abgelaufen = frei
    assert reserve(client, admin, [lab["sw"]["Gi1"]], purpose="Neu").status_code == 201
    assert [x["purpose"] for x in client.get("/api/reservations", headers=admin).json()] == ["Neu"]


def test_rights(client, admin, lab):
    make_user(client, admin, "leser", roles=("viewer",))
    viewer = login(client, "leser", "Passwort-123")
    assert reserve(client, viewer, [lab["sw"]["Gi1"]]).status_code == 403
    client.post("/api/users", headers=admin, json={"username": "planer1", "password": "Passwort-123", "roles": [],
                                                   "scopes": [{"site_id": lab["site"], "role": "planer"}]})
    planer = login(client, "planer1", "Passwort-123")
    assert reserve(client, planer, [lab["far"]["Gi1"]]).status_code == 404                       # fremder Standort: nicht sichtbar
    mine = reserve(client, planer, [lab["sw"]["Gi1"]]).json()[0]
    theirs = reserve(client, admin, [lab["sw"]["Gi2"]]).json()[0]
    reserve(client, admin, [lab["far"]["Gi1"]], purpose="Fremd")
    assert {x["port"] for x in client.get("/api/reservations", headers=planer).json()} == {"Gi1", "Gi2"}
    assert client.get("/api/reservations", headers=viewer).status_code == 200
    assert client.delete(f"/api/reservations/{theirs['id']}", headers=viewer).status_code == 403
    assert client.put(f"/api/reservations/{mine['id']}", headers=planer, json={"purpose": "Umbenannt"}).json()["purpose"] == "Umbenannt"
    assert client.post("/api/reservations/release", headers=planer, json={"ids": [mine["id"], theirs["id"]]}).json()["released"] == 2
