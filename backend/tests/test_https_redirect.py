"""HTTP -> HTTPS-Weiterleitung (FORCE_HTTPS): nur mit laufendem HTTPS-Listener, ACME-HTTP-01 und /health bleiben auf HTTP erreichbar."""
import pytest


@pytest.fixture()
def tls(client, tmp_path, monkeypatch):
    """Eigenes TLS-Verzeichnis; Weiterleitung eingeschaltet, Marker „HTTPS-Listener läuft“ wird je Test gesetzt."""
    from app import acme_client, main
    monkeypatch.setattr(acme_client, "TLS_DIR", tmp_path)
    monkeypatch.setattr(main, "FORCE_HTTPS", True)
    monkeypatch.setattr(main, "PUBLIC_HTTPS_PORT", "443")

    def serving(on=True):
        marker = tmp_path / "serving"
        marker.write_text("1") if on else marker.unlink(missing_ok=True)
    return serving


def get(client, path, host="portwerk.example.test:8084"):
    return client.get(path, headers={"Host": host}, follow_redirects=False)


def test_redirect_to_https_default_port_keeps_path_and_query(client, tls):
    tls(True)
    r = get(client, "/api/stats?site=1&x=a%20b")
    assert r.status_code == 308
    assert r.headers["location"] == "https://portwerk.example.test/api/stats?site=1&x=a%20b"          # Port des HTTP-Listeners entfällt, 443 ist Standard


def test_redirect_uses_public_https_port(client, tls, monkeypatch):
    from app import main
    monkeypatch.setattr(main, "PUBLIC_HTTPS_PORT", "8443")
    tls(True)
    assert get(client, "/").headers["location"] == "https://portwerk.example.test:8443/"


def test_no_redirect_while_https_listener_is_not_running(client, tls):
    tls(False)                                       # kein Zertifikat/Listener -> nie aussperren
    assert get(client, "/health").status_code == 200
    assert get(client, "/api/openapi.json").status_code == 200                                      # unabhängig vom gebauten Frontend


def test_acme_challenge_and_health_stay_on_http(client, tls):
    tls(True)
    assert get(client, "/health").status_code == 200
    r = get(client, "/.well-known/acme-challenge/unbekannt")
    assert r.status_code != 308 and "location" not in r.headers                                    # CA muss über HTTP prüfen können


def test_redirect_off_by_default(client, tls, monkeypatch):
    from app import main
    monkeypatch.setattr(main, "FORCE_HTTPS", False)
    tls(True)
    assert get(client, "/api/openapi.json").status_code == 200


def test_ipv6_literal_host_and_post_method(client, tls):
    tls(True)
    assert get(client, "/api/stats", host="[2001:db8::1]:8084").headers["location"] == "https://[2001:db8::1]/api/stats"
    r = client.post("/auth/login", json={"username": "x", "password": "y"}, headers={"Host": "portwerk.example.test"}, follow_redirects=False)
    assert r.status_code == 308                       # 308 behält die Methode (POST bleibt POST)
