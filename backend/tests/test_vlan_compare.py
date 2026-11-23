"""VLAN-Soll/Ist über Checkmk (Plugin inv_cisco_vlans): Inventar lesen (auch getrennte Zeilen), bewerten, Ist übernehmen, Rechte."""
import pytest

from conftest import login, make_user


def tree(vlan_rows: dict, split: bool = False, n: int = 8):
    """Interfaces Gi0/1..n; vlan_rows: {Portnummer: (vlans, vlantype)}. split=True: VLANs als eigene Zeilen mit gleichem index (Checkmk 2.3)."""
    rows = []
    for i in range(1, n + 1):
        r = {"index": i, "name": f"Gi0/{i}", "port_type": 6, "speed": 1_000_000_000, "admin_status": 1, "oper_status": 1}
        if i in vlan_rows and not split:
            r["vlans"], r["vlantype"] = vlan_rows[i]
        rows.append(r)
    if split:
        rows += [{"index": i, "vlans": v, "vlantype": t} for i, (v, t) in vlan_rows.items()]
    return {"Nodes": {"networking": {"Nodes": {"interfaces": {"Table": {"Rows": rows}}}}}}


OBS = {1: ("10", "static"), 2: ("20", "static"), 4: ("30", "dynamic"), 5: ("40", "static"), 7: ("1-3, 9", "multi-VLAN")}


@pytest.fixture()
def lab(client, admin):
    s = client.post("/api/sites", headers=admin, json={"code": "S1", "name": "Werk"}).json()
    client.post("/api/sites", headers=admin, json={"code": "S2", "name": "Fremd"})
    r = client.post("/api/import/checkmk", headers=admin, json={"site_code": "S1", "hosts": [
        {"host": "sw1", "inventory": tree(OBS)}, {"host": "sw-ohne", "inventory": tree({})}]})
    assert r.status_code == 200, r.text
    assert r.json()["vlans"] == {"devices": 1, "ports": 5, "unknown_devices": 0}               # sw-ohne liefert keine VLAN-Spalten
    dev = {d["hostname"]: d["id"] for d in client.get("/api/devices?limit=50", headers=admin).json()["items"]}
    ports = {p["name"]: p["id"] for p in client.get(f"/api/devices/{dev['sw1']}/ports", headers=admin).json()}
    cfg = lambda name, **c: client.put(f"/api/ports/{ports[name]}/config", headers=admin, json=c)  # noqa: E731
    cfg("Gi0/1", port_mode="access", access_vid=10)                    # ok
    cfg("Gi0/2", port_mode="access", access_vid=10, voice_vid=30)      # abweichend (Switch: 20)
    cfg("Gi0/3", port_mode="trunk", allowed_vids="10,20")              # plausibel (kein Access-VLAN gemeldet)
    cfg("Gi0/4", port_mode="trunk")                                    # abweichend (Switch: Access 30)
    cfg("Gi0/6", port_mode="access", access_vid=10)                    # nicht gemeldet
    cfg("Gi0/7", port_mode="access", access_vid=1)                     # multi-VLAN: nicht bewertbar
    client.post("/api/vlans", headers=admin, json={"vid": 40, "name": "Kamera"})
    return {"site": s["id"], "dev": dev, "ports": ports}


def test_inventory_rows_merged_and_split():
    from app import checkmk
    joined = checkmk.vlan_rows(tree({1: ("10", "static")}))
    split = checkmk.vlan_rows(tree({1: ("10", "static"), 3: ("1-3", "multi-VLAN")}, split=True))
    assert joined == [{"port": "Gi0/1", "vlans": "10", "vlantype": "static"}]
    assert split == [{"port": "Gi0/1", "vlans": "10", "vlantype": "static"}, {"port": "Gi0/3", "vlans": "1-3", "vlantype": "multi-VLAN"}]
    assert checkmk.vlan_rows(tree({})) is None                                                   # keine VLAN-Spalten = keine Aussage


def test_rating_of_all_cases(client, admin, lab):
    r = client.get("/api/vlans/compare", headers=admin).json()
    assert r["devices"] == 1
    by = {x["port"]: x for x in r["rows"]}
    assert {p: by[p]["status"] for p in by} == {"Gi0/1": "ok", "Gi0/2": "mismatch", "Gi0/3": "plausible", "Gi0/4": "mismatch",
                                                "Gi0/5": "undocumented", "Gi0/6": "not_reported", "Gi0/7": "unrated"}
    assert "Gi0/8" not in by                                                                      # weder Doku noch Meldung
    assert by["Gi0/2"]["why"] == "dokumentiert Access 10, Switch meldet 20" and by["Gi0/4"]["why"].startswith("dokumentiert Trunk")
    assert by["Gi0/5"]["ist"] == "static 40 (Kamera)" and by["Gi0/5"]["adoptable"] and not by["Gi0/7"]["adoptable"]
    assert [x["status"] for x in r["rows"]][:2] == ["mismatch", "mismatch"]                      # Abweichungen zuerst
    assert r["summary"]["mismatch"] == 2 and r["summary"]["ok"] == 1


def test_split_rows_from_checkmk_23(client, admin, lab):
    client.post("/api/import/checkmk", headers=admin, json={"site_code": "S1", "hosts": [{"host": "sw1", "inventory": tree({1: ("20", "static")}, split=True)}]})
    by = {x["port"]: x for x in client.get("/api/vlans/compare", headers=admin).json()["rows"]}
    assert by["Gi0/1"]["status"] == "mismatch"                                                   # Switch meldet jetzt 20
    assert "Gi0/5" not in by and by["Gi0/2"]["status"] == "not_reported"                       # alte Meldungen ersetzt


def test_adopt_observed_vlan(client, admin, lab):
    p = lab["ports"]
    r = client.post("/api/vlans/compare/adopt", headers=admin, json={"port_ids": [p["Gi0/5"], p["Gi0/2"], p["Gi0/7"]]})
    assert r.json() == {"adopted": 2, "skipped": 1}                                              # multi-VLAN wird nicht übernommen
    by = {x["port"]: x for x in client.get("/api/vlans/compare", headers=admin).json()["rows"]}
    assert by["Gi0/5"]["status"] == "ok" and by["Gi0/2"]["status"] == "ok"
    assert by["Gi0/2"]["soll"] == "Access 20 + Voice 30"                                         # Voice-VLAN bleibt erhalten
    h = client.get(f"/api/ports/{p['Gi0/5']}/config-history", headers=admin).json()[0]
    assert h["reason"] == "checkmk" and h["after"] == "Access 40 (Kamera)"


def test_rights_and_scope(client, admin, lab):
    make_user(client, admin, "leser", roles=("viewer",))
    h = login(client, "leser", "Passwort-123")
    assert client.get("/api/vlans/compare", headers=h).status_code == 200
    assert client.post("/api/vlans/compare/adopt", headers=h, json={"port_ids": [lab["ports"]["Gi0/5"]]}).status_code == 403
    client.post("/api/users", headers=admin, json={"username": "fremd", "password": "Passwort-123", "roles": [],
                                                   "scopes": [{"site_id": lab["site"] + 1, "role": "viewer"}]})
    other = login(client, "fremd", "Passwort-123")
    assert client.get("/api/vlans/compare", headers=other).json()["rows"] == []
