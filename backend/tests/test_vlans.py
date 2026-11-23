"""VLAN/Portprofil als Attribut: Katalog, Profile, Konfiguration am Port mit Historie, Aufträge (umkonfigurieren / beim Herstellen)."""
import io

import pytest
from fastapi import HTTPException
from pypdf import PdfReader

from conftest import login, make_user

OVR = {"override_reason": "Test (allein)"}


@pytest.fixture()
def lab(client, admin):
    s = client.post("/api/sites", headers=admin, json={"code": "W1", "name": "Werk"}).json()
    s2 = client.post("/api/sites", headers=admin, json={"code": "W2", "name": "Fremd"}).json()
    rack = client.post("/api/locations", headers=admin, json={"site_id": s["id"], "kind": "rack", "name": "R1", "rack_units": 20}).json()["id"]

    def dev(name, dtype, ports):
        d = client.post("/api/devices", headers=admin, json={"hostname": name, "type": dtype, "location_id": rack}).json()
        return {"id": d["id"], **{n: client.post(f"/api/devices/{d['id']}/ports", headers=admin, json={"name": n}).json()["id"] for n in ports}}
    v = lambda vid, name, site=None: client.post("/api/vlans", headers=admin, json={"vid": vid, "name": name, "site_id": site})  # noqa: E731
    assert v(10, "Büro").status_code == 201 and v(20, "Drucker").status_code == 201 and v(30, "Voice").status_code == 201
    assert v(20, "Drucker Werk", s["id"]).status_code == 201                        # standortbezogen überschreibt den Namen
    prof = lambda **b: client.post("/api/port-profiles", headers=admin, json=b).json()  # noqa: E731
    return {"site": s["id"], "site2": s2["id"], "sw": dev("sw-1", "switch", ["Gi1", "Gi2", "Gi3"]), "sw2": dev("sw-2", "switch", ["Gi1"]),
            "pc": dev("pc-1", "endpoint", ["eth0"]), "pf": dev("pf-1", "patchpanel", ["P1"]),
            "printer": prof(name="Drucker", port_mode="access", access_vid=20),
            "office": prof(name="Büro-PC", port_mode="access", access_vid=10, voice_vid=30),
            "ap": prof(name="Access Point", port_mode="trunk", allowed_vids="40-42, 10,20", native_vid=99)}


def run(client, admin, wid, status="done"):
    for act in ("submit", "approve", "start"):
        assert client.post(f"/api/workorders/{wid}/transition/{act}", headers=admin, json=OVR).status_code == 200
    for it in client.get(f"/api/workorders/{wid}", headers=admin).json()["items"]:
        client.post(f"/api/workorders/{wid}/items/{it['id']}/execute", headers=admin, json={"item_status": status, "deviation_note": "anders"})
    for act in ("finish", "confirm"):
        assert client.post(f"/api/workorders/{wid}/transition/{act}", headers=admin, json=OVR).status_code == 200


def test_vid_list_normalization():
    from app.portcfg import parse_vids, vid_set
    assert parse_vids(" 40-42, 10;20,11 ") == "10-11,20,40-42" and parse_vids("") == ""
    assert vid_set("10-11,20") == {10, 11, 20}
    for bad in ("0", "4095", "20-10", "x"):
        with pytest.raises(HTTPException):
            parse_vids(bad)


def test_catalog_and_profiles(client, admin, lab):
    assert client.post("/api/vlans", headers=admin, json={"vid": 10, "name": "doppelt"}).status_code == 409
    assert client.post("/api/vlans", headers=admin, json={"vid": 5000, "name": "x"}).status_code == 422
    vl = client.get("/api/vlans", headers=admin, params={"site_id": lab["site2"]}).json()
    assert {v["vid"] for v in vl} == {10, 20, 30}                                   # nur globale (W2 hat keine eigenen)
    assert lab["ap"]["allowed_vids"] == "10,20,40-42" and lab["ap"]["access_vid"] is None
    assert client.post("/api/port-profiles", headers=admin, json={"name": "kaputt", "port_mode": "access"}).status_code == 400
    assert client.post("/api/port-profiles", headers=admin, json={"name": "drucker", "port_mode": "access", "access_vid": 20}).status_code == 409
    profiles = {p["name"]: p for p in client.get("/api/port-profiles", headers=admin).json()}
    assert profiles["Büro-PC"]["text"] == "Access 10 + Voice 30" and profiles["Access Point"]["text"] == "Trunk 10,20,40-42 · native 99"
    make_user(client, admin, "leser", roles=("viewer",))
    h = login(client, "leser", "Passwort-123")
    assert client.post("/api/vlans", headers=h, json={"vid": 50, "name": "x"}).status_code == 403
    assert client.post("/api/port-profiles", headers=h, json={"name": "y", "port_mode": "access", "access_vid": 1}).status_code == 403
    assert client.get("/api/port-profiles", headers=h).status_code == 200


def test_direct_port_config_with_history_and_usage(client, admin, lab):
    gi1 = lab["sw"]["Gi1"]
    r = client.put(f"/api/ports/{gi1}/config", headers=admin, json={"profile_id": lab["printer"]["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["access_vid"] == 20 and r.json()["text"] == "Drucker: Access 20 (Drucker Werk)"          # Name des Standorts vor globalem
    port = next(p for p in client.get(f"/api/devices/{lab['sw']['id']}/ports", headers=admin).json() if p["id"] == gi1)
    assert port["config"]["profile"]["name"] == "Drucker"
    client.put(f"/api/ports/{lab['sw']['Gi2']}/config", headers=admin, json={"profile_id": lab["ap"]["id"]})
    usage = client.get("/api/vlans/usage", headers=admin, params={"vid": 20}).json()
    assert {(u["port"], tuple(u["as"])) for u in usage} == {("Gi1", ("access",)), ("Gi2", ("trunk",))}
    assert next(v for v in client.get("/api/vlans", headers=admin).json() if v["vid"] == 20 and v["site_id"] is None)["ports"] == 2
    client.put(f"/api/ports/{gi1}/config", headers=admin, json={"port_mode": "access", "access_vid": 10})          # eigene Werte, kein Profil
    client.put(f"/api/ports/{gi1}/config", headers=admin, json={"port_mode": "access", "access_vid": 10})          # unverändert: kein Eintrag
    client.put(f"/api/ports/{gi1}/config", headers=admin, json={})                                                 # nicht mehr dokumentiert
    hist = client.get(f"/api/ports/{gi1}/config-history", headers=admin).json()
    assert [(h["before"], h["after"]) for h in hist] == [("Access 10 (Büro)", "nicht dokumentiert"),
                                                         ("Drucker: Access 20 (Drucker Werk)", "Access 10 (Büro)"),
                                                         ("nicht dokumentiert", "Drucker: Access 20 (Drucker Werk)")]
    assert client.put(f"/api/ports/{gi1}/config", headers=admin, json={"port_mode": "access"}).status_code == 400   # Access ohne VLAN


def test_configure_item_applied_on_confirm(client, admin, lab):
    gi3 = lab["sw"]["Gi3"]
    wo = client.post("/api/workorders", headers=admin, json={"title": "VLAN"}).json()
    add = lambda **b: client.post(f"/api/workorders/{wo['id']}/items", headers=admin, json={"action": "configure", **b})  # noqa: E731
    assert add(port_a_id=gi3).status_code == 400                                                    # ohne Ziel
    assert add(port_a_id=gi3, port_b_id=lab["pc"]["eth0"], cfg={"port_mode": "access", "access_vid": 20}).status_code == 400
    r = add(port_a_id=gi3, cfg={"profile_id": lab["office"]["id"]})
    assert r.status_code == 201 and r.json()["cfg_text"] == "sw-1:Gi3 → Büro-PC: Access 10 (Büro) + Voice 30 (Voice)"
    assert client.get(f"/api/ports/{gi3}/path", headers=admin).json()["nodes"][0]["ports"][0]["planned"][0]["action"] == "umkonfigurieren"
    pdf = client.get(f"/api/workorders/{wo['id']}/pdf", headers=admin).content
    assert "Konfiguration: sw-1:Gi3" in "".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
    assert "Büro-PC" in client.get(f"/api/workorders/{wo['id']}/export", headers=admin).text
    run(client, admin, wo["id"])
    assert client.get(f"/api/ports/{gi3}/config-history", headers=admin).json()[0]["workorder"]["number"] == wo["number"]
    assert client.get(f"/api/ports/{gi3}/path", headers=admin).json()["nodes"][0]["ports"][0]["config"].startswith("Büro-PC")


def test_connect_with_target_config(client, admin, lab):
    wo = client.post("/api/workorders", headers=admin, json={"title": "Drucker"}).json()
    add = lambda **b: client.post(f"/api/workorders/{wo['id']}/items", headers=admin, json={"action": "connect", **b})  # noqa: E731
    r = add(port_a_id=lab["pc"]["eth0"], port_b_id=lab["sw"]["Gi1"], cfg={"profile_id": lab["printer"]["id"]})
    assert r.status_code == 201 and r.json()["cfg_port"]["id"] == lab["sw"]["Gi1"]                  # Switch-Ende automatisch
    assert add(port_a_id=lab["sw"]["Gi2"], port_b_id=lab["sw2"]["Gi1"], cfg={"port_mode": "access", "access_vid": 10}).status_code == 400   # zwei Switches
    assert add(port_a_id=lab["sw"]["Gi2"], port_b_id=lab["sw2"]["Gi1"], cfg={"port_mode": "access", "access_vid": 10},
               cfg_port_id=lab["pc"]["eth0"]).status_code == 400                                     # Port gehört nicht zur Position
    assert add(port_a_id=lab["sw"]["Gi2"], port_b_id=lab["sw2"]["Gi1"], cfg={"port_mode": "trunk", "allowed_vids": "10,20"},
               cfg_port_id=lab["sw2"]["Gi1"]).status_code == 201
    run(client, admin, wo["id"])
    ports = {p["name"]: p for p in client.get(f"/api/devices/{lab['sw']['id']}/ports", headers=admin).json()}
    assert ports["Gi1"]["config"]["text"].startswith("Drucker") and ports["Gi1"]["cable"]
    assert client.get(f"/api/devices/{lab['sw2']['id']}/ports", headers=admin).json()[0]["config"]["allowed_vids"] == "10,20"
    disc = client.post("/api/workorders", headers=admin, json={"title": "kein Ziel bei trennen"}).json()
    assert client.post(f"/api/workorders/{disc['id']}/items", headers=admin,
                       json={"action": "disconnect", "port_a_id": lab["sw"]["Gi1"], "cfg": {"port_mode": "access", "access_vid": 10}}).status_code == 400


def test_deviation_does_not_apply(client, admin, lab):
    wo = client.post("/api/workorders", headers=admin, json={"title": "Abw"}).json()
    client.post(f"/api/workorders/{wo['id']}/items", headers=admin, json={"action": "configure", "port_a_id": lab["sw"]["Gi3"],
                                                                         "cfg": {"port_mode": "access", "access_vid": 10}})
    run(client, admin, wo["id"], status="deviation")
    assert next(p for p in client.get(f"/api/devices/{lab['sw']['id']}/ports", headers=admin).json() if p["name"] == "Gi3")["config"] is None
