"""Vier-Augen-Prinzip: Wer einreicht, gibt nicht frei; wer ausführt, bestätigt nicht. Administratoren dürfen mit Begründung übersteuern."""
import pytest

from conftest import login, make_user


@pytest.fixture()
def team(client, admin):
    for name, roles in (("plan", ("planer",)), ("frei", ("freigeber",)), ("tech", ("techniker",)),
                        ("allrounder", ("planer", "freigeber", "techniker")), ("admin2", ("admin",))):
        make_user(client, admin, name, roles=roles)
    return {n: login(client, n, "Passwort-123") for n in ("plan", "frei", "tech", "allrounder", "admin2")} | {"admin": admin}


def new_order(client, h):
    r = client.post("/api/workorders", headers=h, json={"title": "Test"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def step(client, h, wid, action, reason=None):
    return client.post(f"/api/workorders/{wid}/transition/{action}", headers=h,
                       json={"override_reason": reason} if reason is not None else None)


def test_separate_people_pass_and_are_recorded(client, team):
    wid = new_order(client, team["plan"])
    for who, act in (("plan", "submit"), ("frei", "approve"), ("tech", "start"), ("tech", "finish"), ("frei", "confirm")):
        r = step(client, team[who], wid, act)
        assert r.status_code == 200, (act, r.text)
    w = r.json()
    assert (w["submitted_by"], w["approved_by"], w["finished_by"], w["confirmed_by"]) == ("plan", "frei", "tech", "frei")
    assert w["four_eyes_override"] == []


def test_submitter_may_not_approve_but_may_reject(client, team):
    h = team["allrounder"]
    wid = new_order(client, h)
    assert step(client, h, wid, "submit").status_code == 200
    r = step(client, h, wid, "approve", reason="ich will aber")                 # Begründung hilft nur Administratoren
    assert r.status_code == 409 and r.json()["detail"]["code"] == "four_eyes" and r.json()["detail"]["can_override"] is False
    assert step(client, h, wid, "reject").status_code == 200                   # zurückziehen ist erlaubt


def test_creator_may_not_approve_even_if_someone_else_submitted(client, team):
    wid = new_order(client, team["allrounder"])
    assert step(client, team["plan"], wid, "submit").status_code == 200
    assert step(client, team["allrounder"], wid, "approve").status_code == 409
    assert step(client, team["frei"], wid, "approve").status_code == 200


def test_executor_may_not_confirm(client, team):
    wid = new_order(client, team["plan"])
    step(client, team["plan"], wid, "submit"); step(client, team["frei"], wid, "approve")
    h = team["allrounder"]
    assert step(client, h, wid, "start").status_code == 200 and step(client, h, wid, "finish").status_code == 200
    assert step(client, h, wid, "confirm").status_code == 409
    assert step(client, h, wid, "rework").status_code == 200                   # Nacharbeit anordnen bleibt möglich
    assert step(client, team["tech"], wid, "start").status_code == 200 and step(client, team["tech"], wid, "finish").status_code == 200
    assert step(client, h, wid, "confirm").status_code == 200                  # jetzt hat jemand anderes ausgeführt


def test_admin_override_needs_reason_and_is_audited(client, team):
    a = team["admin"]
    wid = new_order(client, a)
    assert step(client, a, wid, "submit").status_code == 200
    r = step(client, a, wid, "approve")
    assert r.status_code == 409 and r.json()["detail"]["can_override"] is True
    assert step(client, a, wid, "approve", reason="   ").status_code == 409
    r = step(client, a, wid, "approve", reason="Störung Halle 3, niemand erreichbar")
    assert r.status_code == 200 and r.json()["approved_by"] == "admin"
    assert r.json()["four_eyes_override"] == ["approve: admin: Störung Halle 3, niemand erreichbar"]
    log = client.get("/api/audit", headers=a).json()
    entries = log["items"] if isinstance(log, dict) else log
    assert any(e["action"] == "workorder.four_eyes_override" and "Halle 3" in e["detail"] for e in entries)


def test_other_admin_needs_no_override(client, team):
    wid = new_order(client, team["admin"])
    step(client, team["admin"], wid, "submit")
    r = step(client, team["admin2"], wid, "approve")
    assert r.status_code == 200 and r.json()["four_eyes_override"] == []


def test_reason_without_conflict_is_ignored(client, team):
    wid = new_order(client, team["plan"])
    step(client, team["plan"], wid, "submit")
    r = step(client, team["frei"], wid, "approve", reason="unnötig")
    assert r.status_code == 200 and r.json()["four_eyes_override"] == []
