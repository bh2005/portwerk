"""Aufräumbericht: vorläufige Kabel, von LLDP nicht gesehene Verbindungen, abgelaufene Reservierungen, liegengebliebene Aufträge,
geplante Geräte ohne Auftrag; Bereichs-Sicht; Wochenmail an die globalen Administratoren."""
import time
from datetime import date

import pytest

from conftest import login
from test_notify import fake_smtp  # noqa: F401  (Fixture)

DAY = 86400


@pytest.fixture()
def lab(client, admin):
    from app import compare, db
    s1 = client.post("/api/sites", headers=admin, json={"code": "S1", "name": "Werk"}).json()["id"]
    s2 = client.post("/api/sites", headers=admin, json={"code": "S2", "name": "Lager"}).json()["id"]
    r1 = client.post("/api/locations", headers=admin, json={"site_id": s1, "kind": "rack", "name": "R1", "rack_units": 20}).json()["id"]
    r2 = client.post("/api/locations", headers=admin, json={"site_id": s2, "kind": "rack", "name": "R2", "rack_units": 20}).json()["id"]

    def dev(name, dtype, loc, ports, status="active"):
        d = client.post("/api/devices", headers=admin, json={"hostname": name, "type": dtype, "location_id": loc, "status": status}).json()
        return {"id": d["id"], **{n: client.post(f"/api/devices/{d['id']}/ports", headers=admin, json={"name": n}).json()["id"] for n in ports}}
    sw1, sw2 = dev("sw1", "switch", r1, ["Gi1", "Gi2"]), dev("sw2", "switch", r1, ["Gi1"])
    sw3, ap1, ap2 = dev("sw3", "switch", r2, ["Gi1", "Gi2"]), dev("ap1", "ap", r2, ["eth0"]), dev("ap2", "ap", r2, ["eth0"])
    neu, neu2 = dev("neu-sw", "switch", r1, ["Gi1"], "planned"), dev("neu-sw2", "switch", r1, ["Gi1"], "planned")
    cab = lambda a, b: client.put(f"/api/ports/{a}/cable", headers=admin, json={"port_b_id": b}).json()["cable"]["id"]  # noqa: E731
    cab(sw1["Gi1"], sw2["Gi1"])                                                         # dokumentiert, LLDP sieht nichts
    old, fresh = cab(sw3["Gi1"], ap1["eth0"]), cab(sw3["Gi2"], ap2["eth0"])
    db.execute("UPDATE cables SET provisional = 1, created_at = ? WHERE id = ?", (time.time() - 40 * DAY, old))
    db.execute("UPDATE cables SET provisional = 1 WHERE id = ?", (fresh,))
    compare.store({"sw1": [], "sw2": []})
    res = client.post("/api/reservations", headers=admin, json={"port_ids": [sw1["Gi2"]], "purpose": "Kamera"}).json()[0]
    db.execute("UPDATE port_reservations SET until = '2020-01-01' WHERE id = ?", (res["id"],))
    stale = client.post("/api/workorders", headers=admin, json={"title": "vergessen", "location_id": r1}).json()
    db.execute("UPDATE workorders SET created_at = ?, updated_at = ? WHERE id = ?", (time.time() - 50 * DAY, time.time() - 45 * DAY, stale["id"]))
    busy = client.post("/api/workorders", headers=admin, json={"title": "aktuell", "location_id": r1}).json()
    assert client.post(f"/api/workorders/{busy['id']}/items", headers=admin,
                       json={"action": "connect", "port_a_id": neu2["Gi1"], "port_b_id": sw1["Gi2"]}).status_code in (200, 201)
    client.post("/api/users", headers=admin, json={"username": "w1", "password": "Passwort-123", "roles": [], "scopes": [{"site_id": s1, "role": "planer"}]})
    return {"s1": s1, "s2": s2, "old": old, "fresh": fresh, "stale": stale, "res": res["id"], "neu": neu, "sw1": sw1}


def test_report_sections(client, admin, lab):
    r = client.get("/api/cleanup", headers=admin)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["counts"] == {"provisional": 2, "not_seen": 2, "expired": 1, "stale_orders": 1, "planned": 1}
    old = next(x for x in d["provisional"] if x["cable_id"] == lab["old"])
    assert old["old"] and old["age_days"] == 40 and old["a"]["text"] == "sw3:Gi1" and old["b"]["text"] == "ap1:eth0"
    assert not next(x for x in d["provisional"] if x["cable_id"] == lab["fresh"])["old"]
    assert d["provisional"][0]["cable_id"] == lab["old"]                                  # älteste zuerst
    assert sorted((x["device"], x["soll"]) for x in d["not_seen"]) == [("sw1", "sw2:Gi1"), ("sw2", "sw1:Gi1")]
    assert d["expired"][0]["id"] == lab["res"] and d["expired"][0]["text"] == "sw1:Gi2"
    assert d["stale_orders"][0]["number"] == lab["stale"]["number"] and d["stale_orders"][0]["age_days"] == 45
    assert [x["hostname"] for x in d["planned"]] == ["neu-sw"]                            # neu-sw2 steckt in einem offenen Auftrag
    assert client.get("/api/cleanup?days=50", headers=admin).json()["counts"]["stale_orders"] == 0
    assert not client.get("/api/cleanup?days=50", headers=admin).json()["provisional"][0]["old"]


def test_scope_and_site_filter(client, admin, lab):
    h = login(client, "w1", "Passwort-123")
    c = client.get("/api/cleanup", headers=h).json()["counts"]
    assert c == {"provisional": 0, "not_seen": 2, "expired": 1, "stale_orders": 1, "planned": 1}          # nur Standort S1
    assert client.get(f"/api/cleanup?site_id={lab['s2']}", headers=h).status_code == 404      # fremder Standort
    c2 = client.get(f"/api/cleanup?site_id={lab['s2']}", headers=admin).json()["counts"]
    assert c2 == {"provisional": 2, "not_seen": 0, "expired": 0, "stale_orders": 0, "planned": 0}
    assert client.get("/api/cables?provisional=true", headers=h).json() == []
    assert len(client.get("/api/cables?provisional=true", headers=admin).json()) == 2


def test_completing_and_releasing_clears_report(client, admin, lab):
    from app import db
    db.execute("UPDATE cables SET provisional = 0 WHERE id = ?", (lab["old"],))
    assert client.post("/api/reservations/release", headers=admin, json={"ids": [lab["res"]]}).status_code == 200
    c = client.get("/api/cleanup", headers=admin).json()["counts"]
    assert c["provisional"] == 1 and c["expired"] == 0


def test_weekly_mail(client, admin, lab, fake_smtp, monkeypatch):  # noqa: F811
    from app import cleanup, db, notifications
    monkeypatch.setattr(notifications, "SEND_IN_BACKGROUND", False)
    client.put("/api/admin/mail", headers=admin, json={"enabled": True, "host": "mail.example.test", "port": 25, "from_addr": "opp@example.test",
                                                       "public_url": "https://pw.example.test"})
    db.execute("UPDATE users SET email = 'admin@example.test' WHERE username = 'admin'")
    monday, tuesday = date(2026, 11, 23), date(2026, 11, 24)
    assert cleanup.weekly_mail(tuesday) == 0 and fake_smtp.sent == []                    # nur montags
    assert cleanup.weekly_mail(monday) == 1
    m = fake_smtp.sent[0]
    assert m["To"] == "admin@example.test" and m["Subject"] == "[Portwerk] Aufräumbericht: 7 offene Punkte"
    body = m.get_body(preferencelist=("plain",)).get_content()
    assert "Vorläufige Kabel: 2" in body and "sw3:Gi1 ↔ ap1:eth0 (seit 40 Tagen)" in body and "https://pw.example.test/cleanup" in body
    assert cleanup.weekly_mail(monday) == 0 and len(fake_smtp.sent) == 1                 # einmal je Woche
    assert client.post("/api/cleanup/mail", headers=admin).json() == {"recipients": 1}  # „jetzt senden“
    h = login(client, "w1", "Passwort-123")
    assert client.post("/api/cleanup/mail", headers=h).status_code == 403
    client.put("/auth/me/notifications", headers=admin, json={"cleanup_report": False})
    assert client.post("/api/cleanup/mail", headers=admin).status_code == 409            # abbestellt
