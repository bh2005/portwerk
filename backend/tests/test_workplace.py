"""Arbeitsplatz-Assistent: Dose → Patchfeld → freier Switchport (nach Nähe), Profil/VLAN, Auftrag; bereits verbunden; Prüfungen."""
import pytest

from conftest import login, make_user

OVR = {"override_reason": "Test (allein)"}


@pytest.fixture()
def lab(client, admin):
    s = client.post("/api/sites", headers=admin, json={"code": "W1", "name": "Werk"}).json()["id"]
    loc = lambda kind, name, parent=None, units=None: client.post("/api/locations", headers=admin, json={  # noqa: E731
        "site_id": s, "kind": kind, "name": name, "parent_id": parent, "rack_units": units}).json()["id"]
    e2 = loc("room", "Etage 2")
    r1, r2 = loc("rack", "E2-R1", e2, 20), loc("rack", "E2-R2", e2, 20)
    rz = loc("rack", "RZ-1", None, 42)
    office = loc("room", "Büro 2.17", e2)

    def dev(name, dtype, where, ports, peers=(), media=None):
        d = client.post("/api/devices", headers=admin, json={"hostname": name, "type": dtype, "location_id": where}).json()
        ids = {n: client.post(f"/api/devices/{d['id']}/ports", headers=admin, json={"name": n, "medium": (media or {}).get(n, "RJ45")}).json()["id"] for n in ports}
        for f, b in peers:
            client.put(f"/api/ports/{ids[f]}/peer", headers=admin, json={"peer_port_id": ids[b]})
        return {"id": d["id"], **ids}
    pf = dev("pf-e2", "patchpanel", r1, ["P1", "P1-back", "P2", "P2-back"], [("P1", "P1-back"), ("P2", "P2-back")])
    sw = dev("sw-e2", "switch", r1, ["Gi1", "Gi2", "Te1"], media={"Te1": "SFP+"})
    sib = dev("sw-sib", "switch", r2, ["Gi1"])
    far = dev("sw-rz", "switch", rz, ["Gi1"])
    do1 = dev("do-2.17", "outlet", office, ["1", "1-back"], [("1", "1-back")])
    do2 = dev("do-2.18", "outlet", office, ["1", "1-back"], [("1", "1-back")])                 # ohne Kabel ins Patchfeld
    pc = dev("pc-1", "endpoint", office, ["eth0"])
    assert client.put(f"/api/ports/{do1['1-back']}/cable", headers=admin, json={"port_b_id": pf["P1-back"]}).status_code == 200
    prof = client.post("/api/port-profiles", headers=admin, json={"name": "Büro-PC", "port_mode": "access", "access_vid": 10, "voice_vid": 30}).json()
    return {"site": s, "pf": pf, "sw": sw, "sib": sib, "far": far, "do1": do1, "do2": do2, "pc": pc, "profile": prof["id"]}


def wiz(client, h, **b):
    return client.post("/api/wizards/workplace", headers=h, json=b)


def test_dry_run_finds_patch_point_and_ranks_free_ports(client, admin, lab):
    r = wiz(client, admin, outlet_port_id=lab["do1"]["1"], profile_id=lab["profile"], dry_run=True)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["state"] == "open" and d["patch_point"]["label"] == "pf-e2:P1" and d["user_port"] == "do-2.17:1"
    assert [(c["hostname"], c["port"], c["distance"]) for c in d["candidates"]] == [
        ("sw-e2", "Gi1", 0), ("sw-e2", "Gi2", 0), ("sw-sib", "Gi1", 1), ("sw-rz", "Gi1", 2)]        # Te1 (SFP+) nicht für RJ45
    assert d["switch_port"]["label"] == "sw-e2:Gi1"
    assert d["items"] == [{"action": "connect", "text": "pf-e2:P1 ↔ sw-e2:Gi1 · VLAN: Büro-PC: Access 10 + Voice 30"}]
    assert d["workorder"] == {"new": "Arbeitsplatz do-2.17:1"}
    # auch vom Rückseiten-Port der Dose aus
    assert wiz(client, admin, outlet_port_id=lab["do1"]["1-back"], dry_run=True).json()["patch_point"]["label"] == "pf-e2:P1"


def test_reserved_and_planned_ports_are_skipped(client, admin, lab):
    client.post("/api/reservations", headers=admin, json={"port_ids": [lab["sw"]["Gi1"]], "purpose": "Kamera"})
    wo = client.post("/api/workorders", headers=admin, json={"title": "anderer"}).json()
    client.post(f"/api/workorders/{wo['id']}/items", headers=admin, json={"action": "connect", "port_a_id": lab["sw"]["Gi2"], "port_b_id": lab["pf"]["P2"]})
    d = wiz(client, admin, outlet_port_id=lab["do1"]["1"], dry_run=True).json()
    assert d["switch_port"]["label"] == "sw-sib:Gi1" and "Gi1" not in [c["port"] for c in d["candidates"] if c["hostname"] == "sw-e2"]


def test_create_order_and_confirm(client, admin, lab):
    r = wiz(client, admin, outlet_port_id=lab["do1"]["1"], profile_id=lab["profile"], endpoint_port_id=lab["pc"]["eth0"],
            cable_label="K-217", length_m=1, color="blau")
    assert r.status_code == 200, r.text
    wid = r.json()["workorder"]["id"]
    items = client.get(f"/api/workorders/{wid}", headers=admin).json()["items"]
    assert [i["action"] for i in items] == ["connect", "connect"]
    patch, ep = items
    assert (patch["port_a"]["name"], patch["port_b"]["name"], patch["cable_label"], patch["color"]) == ("P1", "Gi1", "K-217", "blau")
    assert patch["cfg_port"]["name"] == "Gi1" and patch["cfg_text"].startswith("sw-e2:Gi1 → Büro-PC")
    assert ep["port_a"]["device_hostname"] == "do-2.17" and ep["port_b"]["name"] == "eth0" and ep["cable_label"] == "" and not ep["cfg"]
    for act in ("submit", "approve", "start"):
        client.post(f"/api/workorders/{wid}/transition/{act}", headers=admin, json=OVR)
    for it in items:
        client.post(f"/api/workorders/{wid}/items/{it['id']}/execute", headers=admin, json={"item_status": "done"})
    for act in ("finish", "confirm"):
        assert client.post(f"/api/workorders/{wid}/transition/{act}", headers=admin, json=OVR).status_code == 200
    path = client.get(f"/api/ports/{lab['pc']['eth0']}/path", headers=admin).json()
    assert path["complete"] and path["summary"] == "sw-e2:Gi1 → pc-1:eth0"
    gi1 = next(p for p in client.get(f"/api/devices/{lab['sw']['id']}/ports", headers=admin).json() if p["name"] == "Gi1")
    assert gi1["config"]["profile"]["name"] == "Büro-PC"
    # jetzt verbunden: nur noch umkonfigurieren
    d = wiz(client, admin, outlet_port_id=lab["do1"]["1"], dry_run=True).json()
    assert d["state"] == "connected" and d["switch_port"]["label"] == "sw-e2:Gi1"
    assert wiz(client, admin, outlet_port_id=lab["do1"]["1"]).status_code == 400                    # ohne Profil nichts zu tun
    r = wiz(client, admin, outlet_port_id=lab["do1"]["1"], cfg={"port_mode": "access", "access_vid": 20})
    item = client.get(f"/api/workorders/{r.json()['workorder']['id']}", headers=admin).json()["items"][0]
    assert item["action"] == "configure" and item["port_a"]["name"] == "Gi1"


def test_undocumented_busy_existing_order_and_rights(client, admin, lab):
    d = wiz(client, admin, outlet_port_id=lab["do2"]["1"], dry_run=True).json()
    assert d["state"] == "undocumented" and "nicht bis zu einem Patchfeld" in d["why"]
    assert wiz(client, admin, outlet_port_id=lab["do2"]["1"]).status_code == 400
    client.put(f"/api/ports/{lab['far']['Gi1']}/cable", headers=admin, json={"port_b_id": lab["sib"]["Gi1"]})
    r = wiz(client, admin, outlet_port_id=lab["do1"]["1"], switch_port_id=lab["far"]["Gi1"])
    assert r.status_code == 409 and r.json()["detail"]["code"] == "port_busy"
    assert wiz(client, admin, outlet_port_id=lab["do1"]["1"], switch_port_id=lab["pf"]["P2"]).status_code == 400   # kein Switch
    draft = client.post("/api/workorders", headers=admin, json={"title": "Sammel"}).json()
    r = wiz(client, admin, outlet_port_id=lab["do1"]["1"], workorder_id=draft["id"])
    assert r.status_code == 200 and r.json()["workorder"] == {"id": draft["id"], "number": draft["number"], "title": "Sammel", "new": False}
    make_user(client, admin, "leser", roles=("viewer",))
    h = login(client, "leser", "Passwort-123")
    assert wiz(client, h, outlet_port_id=lab["do1"]["1"], dry_run=True).status_code == 403
