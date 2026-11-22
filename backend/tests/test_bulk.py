"""Massenverkabelung, Arbeitslisten (Sammelaktionen, Export) und kombinierte Patchlisten."""
import pytest

from conftest import login


def model_id(client, admin, name):
    return [m for m in client.get("/api/device-models?q=Generisch", headers=admin).json() if m["model"] == name][0]["id"]


def loc(client, admin, site, name, kind, parent=None, **kw):
    r = client.post("/api/locations", headers=admin, json={"site_id": site, "parent_id": parent, "kind": kind, "name": name, **kw})
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture()
def lab(client, admin):
    s = client.post("/api/sites", headers=admin, json={"code": "W1", "name": "Werk"}).json()["id"]
    rz = loc(client, admin, s, "RZ", "room")
    rack = loc(client, admin, s, "R1", "rack", rz, rack_units=20)
    e1 = loc(client, admin, s, "Etage 1", "room")
    rack1 = loc(client, admin, s, "R-E1", "rack", e1, rack_units=12)
    e2 = loc(client, admin, s, "Etage 2", "room")
    rack2 = loc(client, admin, s, "R-E2", "rack", e2, rack_units=12)
    pp = model_id(client, admin, "Patchfeld Cat6A 24 Port")
    mk = lambda host, where, pos, model, **kw: client.post("/api/wizards/device", headers=admin, json={  # noqa: E731
        "hostname": host, "type": kw.pop("type", "patchpanel"), "model_id": model, "location_id": where, "rack_position": pos, **kw}).json()["device_id"]
    out = {"site": s, "rz": rz, "rack": rack, "e1": e1, "rack1": rack1, "e2": e2, "rack2": rack2}
    out["pf_rz"] = mk("pf-rz", rack, 1, pp)
    out["pf_e1"] = mk("pf-e1", rack1, 1, pp)
    out["sw_e2"] = mk("sw-e2", rack2, 1, model_id(client, admin, "Switch 24 Port"), type="switch")
    out["pf_e2"] = mk("pf-e2", rack2, 3, pp)
    return out


def ports(client, admin, **spec):
    r = client.post("/api/wizards/port-list", headers=admin, json=spec)
    assert r.status_code == 200, r.text
    return r.json()


def pairs_of(a, b, n=None, label="K-{n}"):
    n = n or min(len(a), len(b))
    return [{"port_a_id": a[i]["id"], "port_b_id": b[i]["id"], "cable_label": label.format(n=i + 1)} for i in range(n)]


def test_port_list_sides_free_and_natural_order(client, admin, lab):
    back = ports(client, admin, device_id=lab["pf_rz"], side="back")
    assert back["total"] == 24 and all(p["name"].endswith("-back") for p in back["ports"])
    assert [p["name"] for p in back["ports"][:3]] == ["P1-back", "P2-back", "P3-back"] and back["ports"][-1]["name"] == "P24-back"   # natürliche Reihenfolge
    front = ports(client, admin, device_id=lab["pf_rz"], side="front")
    assert front["total"] == 24 and not any(p["name"].endswith("-back") for p in front["ports"])
    assert ports(client, admin, device_id=lab["pf_rz"])["total"] == 48
    assert client.post("/api/wizards/port-list", headers=admin, json={"device_id": lab["pf_rz"], "side": "oben"}).status_code == 400
    assert client.post("/api/wizards/port-list", headers=admin, json={}).status_code == 400
    assert client.post("/api/wizards/port-list", headers=admin, json={"device_id": 9999}).status_code == 404


def test_scenario_trunk_between_two_patchpanels_as_one_order(client, admin, lab):
    a = ports(client, admin, device_id=lab["pf_rz"], side="back")["ports"]
    b = ports(client, admin, device_id=lab["pf_e1"], side="back")["ports"]
    body = {"pairs": pairs_of(a, b, label="TR-{n:02d}"), "cable_type": "Cat6A", "mode": "workorder", "workorder_title": "Trunk RZ ↔ E1"}
    dry = client.post("/api/wizards/bulk-cables", headers=admin, json={**body, "dry_run": True}).json()
    assert dry["dry_run"] and dry["count"] == 24 and dry["cables"][0] == {"from": "pf-rz:P1-back", "to": "pf-e1:P1-back", "label": "TR-01"}
    assert dry["cables"][1]["label"] == "TR-24" and dry["via"] == "Patchauftrag"
    assert client.get("/api/workorders", headers=admin).json() == []                           # Trockenlauf schreibt nichts
    r = client.post("/api/wizards/bulk-cables", headers=admin, json=body)
    assert r.status_code == 200, r.text
    wo = client.get(f"/api/workorders/{r.json()['workorder']['id']}", headers=admin).json()
    assert wo["title"] == "Trunk RZ ↔ E1" and len(wo["items"]) == 24 and wo["progress"] == {"total": 24, "done": 0, "deviation": 0}
    assert {i["action"] for i in wo["items"]} == {"connect"} and wo["items"][23]["cable_label"] == "TR-24"
    assert client.get("/api/cables", headers=admin).json() == []                                # Bestand erst nach Bestätigung


def test_scenario_outlets_to_switch_direct_atomic(client, admin, lab):
    outlets = [client.post("/api/wizards/device", headers=admin, json={"hostname": f"dose-{i:02d}", "type": "outlet", "location_id": lab["e2"],
                                                                      "ports": [{"prefix": "D", "count": 1, "medium": "RJ45"}]}).json()["device_id"] for i in range(1, 9)]
    a = ports(client, admin, location_id=lab["e2"], device_types=["outlet"])["ports"]
    assert [p["hostname"] for p in a] == [f"dose-{i:02d}" for i in range(1, 9)] and all(p["location_path"] == "W1 / Etage 2" for p in a)
    b = ports(client, admin, device_id=lab["sw_e2"])["ports"]
    r = client.post("/api/wizards/bulk-cables", headers=admin, json={"pairs": pairs_of(a, b, label="DO-{n}"), "cable_type": "Cat6A", "mode": "direct"})
    assert r.status_code == 200, r.text
    assert len(r.json()["cable_ids"]) == 8 and r.json()["workorder"] is None
    cables = client.get("/api/cables", headers=admin).json()
    assert len(cables) == 8 and {c["cable_label"] for c in cables} == {f"DO-{i}" for i in range(1, 9)}
    assert ports(client, admin, location_id=lab["e2"], device_types=["outlet"])["total"] == 0                # alle Dosen sind jetzt belegt
    assert ports(client, admin, location_id=lab["e2"], device_types=["outlet"], only_free=False)["total"] == 8
    again = client.post("/api/wizards/bulk-cables", headers=admin, json={"pairs": pairs_of(a, b), "mode": "direct"})
    assert again.status_code == 409 and "bestehen bereits" in again.json()["detail"]                       # nichts Neues
    del outlets


def test_validation_and_busy_ports_single_question(client, admin, lab):
    a = ports(client, admin, device_id=lab["pf_rz"], side="back")["ports"]
    b = ports(client, admin, device_id=lab["pf_e1"], side="back")["ports"]
    post = lambda pairs, **kw: client.post("/api/wizards/bulk-cables", headers=admin, json={"pairs": pairs, "mode": "direct", **kw})  # noqa: E731
    p = pairs_of(a, b, 4)
    assert post([p[0], {**p[1], "port_a_id": p[0]["port_a_id"]}]).status_code == 400                      # Port doppelt
    assert post([{**p[0], "port_b_id": p[0]["port_a_id"]}]).status_code == 400                           # mit sich selbst
    assert post([{**p[0], "port_b_id": 99999}]).status_code == 404
    assert post(p, cable_type="Zauber").status_code == 400
    assert post(p, mode="beamen").status_code == 400
    assert client.post("/api/wizards/bulk-cables", headers=admin, json={"pairs": []}).status_code == 422
    assert post(p).status_code == 200
    # neue Liste auf teilweise belegten Ports: genau eine Rückfrage
    c = ports(client, admin, device_id=lab["pf_e2"], side="back")["ports"]
    new = [{"port_a_id": a[2]["id"], "port_b_id": c[0]["id"], "cable_label": "N1"}, {"port_a_id": a[3]["id"], "port_b_id": c[1]["id"], "cable_label": "N2"},
           {"port_a_id": a[10]["id"], "port_b_id": c[2]["id"], "cable_label": "N3"}]
    q = post(new)
    d = q.json()["detail"]
    assert q.status_code == 409 and d["code"] == "port_busy" and len(d["conflicts"]) == 2 and "2 Port(s)" in d["message"] and "sofort" in d["message"]
    ok = post(new, remove_old=True)
    assert ok.status_code == 200, ok.text
    labels = {x["cable_label"] for x in client.get("/api/cables", headers=admin).json()}
    assert {"N1", "N2", "N3"} <= labels and "K-3" not in labels and "K-4" not in labels and "K-1" in labels                 # K-3/K-4 ersetzt, K-1/K-2 bleiben


def test_bulk_with_removal_order_in_workorder_mode(client, admin, lab):
    a = ports(client, admin, device_id=lab["pf_rz"], side="back")["ports"]
    b = ports(client, admin, device_id=lab["pf_e1"], side="back")["ports"]
    c = ports(client, admin, device_id=lab["pf_e2"], side="back")["ports"]
    client.post("/api/wizards/bulk-cables", headers=admin, json={"pairs": pairs_of(a, b, 3, "ALT-{n}"), "mode": "direct"})
    new = {"pairs": [{"port_a_id": a[0]["id"], "port_b_id": c[0]["id"], "cable_label": "NEU-1"}, {"port_a_id": a[1]["id"], "port_b_id": c[1]["id"], "cable_label": "NEU-2"}], "mode": "workorder"}
    q = client.post("/api/wizards/bulk-cables", headers=admin, json=new)
    assert q.status_code == 409 and "Rückbau-Patchauftrag" in q.json()["detail"]["message"]
    r = client.post("/api/wizards/bulk-cables", headers=admin, json={**new, "remove_old": True})
    assert r.status_code == 200, r.text
    wo = r.json()["workorder"]
    rem = client.get(f"/api/workorders/{wo['removal_order']['id']}", headers=admin).json()
    assert [i["action"] for i in rem["items"]] == ["disconnect", "disconnect"] and rem["required_by"][0]["number"] == wo["number"]


def test_csv_list_parse_and_submit(client, admin, lab):
    text = ("Gerät A;Port A;Gerät B;Port B;Kabelnummer\n"
            "pf-rz;P1-back;pf-e1;P1-back;L-001\n"
            "PF-RZ;p2-back;pf-e1;P2-back;L-002\n"
            "pf-rz;P3-back;pf-xx;P1;L-003\n"
            "pf-rz;P4-back;pf-e1;P99;L-004\n"
            "pf-rz;P1-back;pf-e1;P5-back;L-005\n"
            "\n"
            "pf-rz;P6-back;pf-e1;P6-back\n"
            "zu;kurz\n")
    r = client.post("/api/wizards/bulk-cables/parse", headers=admin, json={"text": text}).json()
    assert [p["cable_label"] for p in r["pairs"]] == ["L-001", "L-002", ""] and r["pairs"][1]["a"] == "PF-RZ:p2-back"
    msgs = {e["line"]: e["message"] for e in r["errors"]}
    assert "pf-xx" in msgs[4] and "P99" in msgs[5] and "mehrfach" in msgs[6] and "4 Spalten" in msgs[9]
    sub = client.post("/api/wizards/bulk-cables", headers=admin, json={"pairs": [{k: p[k] for k in ("port_a_id", "port_b_id", "cable_label")} for p in r["pairs"]], "mode": "direct"})
    assert sub.status_code == 200 and len(sub.json()["cable_ids"]) == 3
    # Tab-getrennt und ohne Kopfzeile (Einfügen aus Excel)
    t2 = client.post("/api/wizards/bulk-cables/parse", headers=admin, json={"text": "pf-rz\tP10-back\tpf-e1\tP10-back\tX1\npf-rz\tP11-back\tpf-e1\tP11-back"}).json()
    assert len(t2["pairs"]) == 2 and not t2["errors"]


def test_worklist_bulk_actions_progress_and_export(client, admin, lab):
    a = ports(client, admin, device_id=lab["pf_rz"], side="back")["ports"]
    b = ports(client, admin, device_id=lab["pf_e1"], side="back")["ports"]
    wid = client.post("/api/wizards/bulk-cables", headers=admin, json={"pairs": pairs_of(a, b, 10), "mode": "workorder", "workorder_title": "Liste"}).json()["workorder"]["id"]
    ids = [i["id"] for i in client.get(f"/api/workorders/{wid}", headers=admin).json()["items"]]
    bulk = lambda action, sel, **kw: client.post(f"/api/workorders/{wid}/items/bulk", headers=admin, json={"ids": sel, "action": action, **kw})  # noqa: E731
    assert bulk("execute", ids).status_code == 409                                                        # erst in Ausführung
    assert bulk("delete", ids[:2]).json()["progress"]["total"] == 8                                       # im Entwurf löschen
    ids = ids[2:]
    for act in ("submit", "approve", "start"):
        assert client.post(f"/api/workorders/{wid}/transition/{act}", headers=admin, json={"override_reason": "Test (allein)"}).status_code == 200
    assert bulk("delete", ids[:1]).status_code == 409
    assert bulk("execute", [99999]).status_code == 404
    r = bulk("execute", ids[:6])
    assert r.status_code == 200 and r.json()["progress"] == {"total": 8, "done": 6, "deviation": 0}
    dev = bulk("execute", ids[6:], item_status="deviation")
    assert dev.status_code == 400                                                                         # Abweichung braucht Notiz
    r = bulk("execute", ids[6:7], item_status="deviation", deviation_note="Dose defekt")
    assert r.json()["progress"] == {"total": 8, "done": 6, "deviation": 1}
    assert bulk("reopen", ids[:2]).json()["progress"]["done"] == 4
    exp = client.get(f"/api/workorders/{wid}/export", headers=admin)
    assert exp.status_code == 200 and exp.content.startswith(b"\xef\xbb\xbf") and "attachment" in exp.headers["content-disposition"]
    rows = exp.text.lstrip("﻿").splitlines()
    assert rows[0].startswith("Auftrag;PA-") and rows[2].startswith("Nr;Aktion") and len(rows) == 3 + 8
    assert "pf-rz:P3-back;pf-e1:P3-back;K-3" in exp.text and "Abweichung" in exp.text and "erledigt" in exp.text


def test_combined_patchlist_from_several_orders(client, admin, lab):
    a = ports(client, admin, device_id=lab["pf_rz"], side="back")["ports"]
    b = ports(client, admin, device_id=lab["pf_e1"], side="back")["ports"]
    sw = ports(client, admin, device_id=lab["sw_e2"])["ports"]
    pf2 = ports(client, admin, device_id=lab["pf_e2"], side="front")["ports"]
    w1 = client.post("/api/wizards/bulk-cables", headers=admin, json={"pairs": pairs_of(a, b, 3, "T-{n}"), "mode": "workorder", "workorder_title": "Trunk"}).json()["workorder"]
    w2 = client.post("/api/wizards/bulk-cables", headers=admin, json={"pairs": pairs_of(pf2, sw, 4, "S-{n}"), "mode": "workorder", "workorder_title": "Etage 2"}).json()["workorder"]
    ids = f"{w1['id']},{w2['id']}"
    r = client.get(f"/api/patchlists?ids={ids}", headers=admin).json()
    assert [o["number"] for o in r["orders"]] == [w1["number"], w2["number"]] and r["summary"]["total"] == 7 and r["summary"]["by_action"] == {"connect": 7}
    groups = [i["group"] for i in r["items"]]
    assert groups == ["W1 / Etage 2 / R-E2"] * 4 + ["W1 / RZ / R1"] * 3                                    # nach Ort gruppiert und sortiert, nicht nach Auftrag
    assert set(groups) == {"W1 / RZ / R1", "W1 / Etage 2 / R-E2"} and r["items"][4]["a"] == "pf-rz:P1-back" and r["items"][4]["b_location"] == "W1 / Etage 1 / R-E1"
    by_order = client.get(f"/api/patchlists?ids={ids}&group=order", headers=admin).json()
    assert [i["group"] for i in by_order["items"]] == [w1["number"]] * 3 + [w2["number"]] * 4
    assert client.get(f"/api/patchlists?ids={w1['id']}&group=none", headers=admin).json()["summary"]["total"] == 3
    # nur offene Positionen
    for act in ("submit", "approve", "start"):
        client.post(f"/api/workorders/{w1['id']}/transition/{act}", headers=admin, json={"override_reason": "Test (allein)"})
    first = client.get(f"/api/workorders/{w1['id']}", headers=admin).json()["items"][0]["id"]
    client.post(f"/api/workorders/{w1['id']}/items/bulk", headers=admin, json={"ids": [first], "action": "execute"})
    assert client.get(f"/api/patchlists?ids={ids}&only_open=true", headers=admin).json()["summary"]["total"] == 6
    csv_r = client.get(f"/api/patchlists/export?ids={ids}", headers=admin)
    assert csv_r.status_code == 200 and csv_r.content.startswith(b"\xef\xbb\xbf") and csv_r.text.count("\n") >= 10 and "T-1" in csv_r.text and "S-4" in csv_r.text
    assert client.get("/api/patchlists?ids=abc", headers=admin).status_code == 400
    assert client.get("/api/patchlists?ids=", headers=admin).status_code == 400
    assert client.get("/api/patchlists?ids=99999", headers=admin).status_code == 404
    assert client.get(f"/api/patchlists?ids={ids}&group=x", headers=admin).status_code == 400


def test_permissions_for_bulk_and_patchlist(client, admin, lab):
    def user(name, role):
        client.post("/api/users", headers=admin, json={"username": name, "password": "Passwort-123", "roles": [], "scopes": [{"role": role, "site_id": lab["site"]}]})
        return login(client, name, "Passwort-123")
    other = client.post("/api/sites", headers=admin, json={"code": "W2", "name": "Fremd"}).json()["id"]
    pl, vw, tk = user("pl", "planer"), user("vw", "viewer"), user("tk", "techniker")
    a = ports(client, admin, device_id=lab["pf_rz"], side="back")["ports"]
    b = ports(client, admin, device_id=lab["pf_e1"], side="back")["ports"]
    body = {"pairs": pairs_of(a, b, 3), "mode": "workorder"}
    assert client.post("/api/wizards/bulk-cables", headers=vw, json=body).status_code == 403
    assert client.post("/api/wizards/bulk-cables", headers=pl, json={**body, "mode": "direct"}).status_code == 403
    ok = client.post("/api/wizards/bulk-cables", headers=pl, json=body)
    assert ok.status_code == 200, ok.text
    wid = ok.json()["workorder"]["id"]
    assert client.get(f"/api/patchlists?ids={wid}", headers=vw).status_code == 200                          # Betrachter dürfen die Liste lesen
    assert client.post(f"/api/workorders/{wid}/items/bulk", headers=vw, json={"ids": [1], "action": "delete"}).status_code == 403
    for act in ("submit", "approve", "start"):
        client.post(f"/api/workorders/{wid}/transition/{act}", headers=admin, json={"override_reason": "Test (allein)"})
    ids = [i["id"] for i in client.get(f"/api/workorders/{wid}", headers=admin).json()["items"]]
    assert client.post(f"/api/workorders/{wid}/items/bulk", headers=pl, json={"ids": ids, "action": "execute"}).status_code == 403   # Planer hakt nicht ab
    assert client.post(f"/api/workorders/{wid}/items/bulk", headers=tk, json={"ids": ids, "action": "execute"}).status_code == 200
    # Fremder Standort: Auftrag und Ports sind unsichtbar
    stranger = client.post("/api/users", headers=admin, json={"username": "fremd", "password": "Passwort-123", "roles": [], "scopes": [{"role": "viewer", "site_id": other}]})
    assert stranger.status_code == 201
    h = login(client, "fremd", "Passwort-123")
    assert client.get(f"/api/patchlists?ids={wid}", headers=h).status_code == 404
    assert client.post("/api/wizards/port-list", headers=h, json={"device_id": lab["pf_rz"]}).status_code == 404
