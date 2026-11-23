# Import aus Checkmk

Portwerk liest Geräte und Ports aus dem **Checkmk-HW/SW-Inventar**. Das Inventar enthält für Netzwerkgeräte
(Checkmk-Knoten `networking.interfaces`) Interfaces mit Name, Beschreibung, Geschwindigkeit und Status, dazu Hersteller,
Modell und Seriennummer (`hardware.components.chassis`), die Management-IP und die **LLDP-Nachbarn**
(`networking.lldp_cache.neighbors`, wird für den Soll/Ist-Abgleich in Etappe 3 verwendet).

Der Import läuft über ein kleines Skript auf dem Checkmk-Server ([tools/checkmk_export.py](../tools/checkmk_export.py), nur Python 3,
keine Abhängigkeiten). So braucht Portwerk keinen Zugriff auf Checkmk-Interna; die Umwandlung geschieht im Server und ist getestet.

## Einrichten

1. In Portwerk (als Administrator): Verwaltung → **API-Zugänge** → neuen Zugang mit Umfang **write** anlegen. Das Token `opp_…`
   wird nur einmal angezeigt.
2. Das Skript auf den Checkmk-Server kopieren (als Site-Benutzer oder root ausführbar).

## Verwenden

```bash
export OPP_URL=https://opp.example.com
export OPP_TOKEN=opp_...            # besser als Umgebungsvariable (taucht nicht in der Prozessliste auf)

# 1. Trockenlauf: zeigt, was angelegt/geändert würde, speichert nichts
./checkmk_export.py --site mysite --dry-run

# 2. Import (alle Hosts mit Interfaces), Geräte einem Standort zuordnen
./checkmk_export.py --site mysite --site-code SITE-A

# nur bestimmte Hosts, interne CA für HTTPS
./checkmk_export.py --site mysite --hosts '^sw-' --ca-file /etc/ssl/certs/internal-ca.pem
```

| Option | Bedeutung |
|---|---|
| `--site` / `--inventory-dir` | Checkmk-Site bzw. Verzeichnis der Inventar-JSONs (Standard `/omd/sites/<site>/var/check_mk/inventory`) |
| `--hosts` | regulärer Ausdruck für Hostnamen |
| `--site-code` | Standort-Code, dem alle Geräte zugeordnet werden (Location „Allgemein“); sonst bleibt der Standort leer |
| `--all-interfaces` | auch Loopbacks, VLANs und Tunnel als Ports übernehmen (Standard: nur Ethernet-Ports) |
| `--dry-run` | nichts speichern |
| `--no-atomic` | fehlerhafte Hosts überspringen statt den ganzen Stapel abzulehnen |
| `--batch` | Hosts je Anfrage (Standard 300) |
| `--print` | nur als JSON ausgeben (z. B. zum Prüfen) |

Regelmäßig ausführen (Cron auf dem Checkmk-Server) hält den Bestand aktuell; der Import ist **idempotent**.

## Regeln

- **Schlüssel:** der Checkmk-Hostname (`ext_id`). Wird ein Host in Checkmk umbenannt, aber `ext_id` bleibt gleich, wird das Gerät umbenannt statt doppelt angelegt.
- **Nur Stammdaten:** der Import legt Geräte und Ports an und aktualisiert sie. **Bestehende Verbindungen ändert er nie** – das tun nur Patchaufträge.
- **Leere Werte** in der Quelle überschreiben nichts. Ports, die im Inventar fehlen, werden **nicht** gelöscht.
- **Gerätetyp** wird aus Modell/Produkt geraten (`switch`, `ap`, `firewall`, `router`; sonst `other`) und kann in der Oberfläche korrigiert werden.
- **Medium:** Ports ab 10 Gbit/s werden als `SFP+` geführt, alle anderen als `RJ45` (Standard). Auch das lässt sich nachträglich ändern.
- Hosts ohne Interfaces im Inventar (z. B. Server ohne Netzwerk-Inventar) werden übersprungen und im Ergebnis aufgeführt.

## Direkt per API

Das Skript ruft `POST /api/import/checkmk` auf; das lässt sich auch ohne Skript nutzen:

```json
{"hosts": [{"host": "sw-01", "inventory": { "Nodes": { "networking": { "...": "Inventarbaum wie in var/check_mk/inventory/sw-01.json" } } } }],
 "dry_run": true, "atomic": true, "site_code": "SITE-A", "include_all_interfaces": false, "all_hosts": false}
```

Swagger-Dokumentation: `/api/docs`.

## Soll/Ist-Abgleich (LLDP/CDP)

Der Import übernimmt zusätzlich die Nachbarn aus `networking.lldp_cache.neighbors` und `networking.cdp_cache.neighbors`. Jeder Import ersetzt die Nachbarn
der enthaltenen Geräte; ein Host ohne Nachbartabellen lässt den bisherigen Stand unverändert. Das Menü **Soll/Ist** vergleicht sie mit der dokumentierten
Verkabelung – über Patchfelder und Dosen hinweg bis zum ersten aktiven Gerät:

| Ergebnis | Bedeutung |
|---|---|
| stimmt | Gegenstelle und Port entsprechen der Dokumentation (eine Strecke erscheint nur einmal) |
| anderer Port / anderes Gerät | der gemeldete Nachbar weicht von der Dokumentation ab |
| nicht gesehen | dokumentiert, aber kein Nachbar gemeldet (Gegenstelle spricht LLDP/CDP) |
| nicht dokumentiert | Nachbar gesehen, aber kein Kabel erfasst |
| keine Daten / Port unbekannt | Gegenstelle ohne LLDP/CDP bzw. gemeldeter Port fehlt im Bestand |

Portnamen werden normalisiert (`GigabitEthernet0/3` = `Gi0/3`); Nachbarn werden über den Kurznamen (ohne Domäne) oder die Management-IP dem Gerät zugeordnet.
Reine MAC-Adressen werden ignoriert. API: `GET /api/compare` (Filter `site_id`, `status`), `GET /api/compare/export.csv`.

## VLAN-Soll/Ist

Führt Checkmk im Inventar die Spalten `vlans`/`vlantype` in `networking.interfaces` (Plugin `inv_cisco_vlans`, nur **Cisco**,
CISCO-VLAN-MEMBERSHIP-MIB), übernimmt der Import sie als gemeldete VLANs je Port. Je nach Checkmk-Version stehen die Angaben in der
Interface-Zeile oder in einer eigenen Zeile mit gleichem `index` – beides wird erkannt. Das Export-Skript braucht dafür keine Änderung.

Checkmk meldet nur **Access-VLANs** (`static`, `dynamic`; `multi-VLAN` wird angezeigt, aber nicht bewertet). Trunks und Voice-VLANs
sind nicht enthalten. Der Abgleich steht unter Soll/Ist → „VLANs (Checkmk)“; gemeldete, nicht dokumentierte VLANs lassen sich
mit „Ist übernehmen“ in die Doku eintragen.

## Link zu Checkmk

Unter *Verwaltung → Checkmk* die Adresse der Site eintragen (z. B. `https://monitoring.example.test/prod`). Danach zeigen Rack-Ansicht und Gerätedetails den Link
„In Checkmk öffnen“ zur Host-Seite (Hostname = Hostname in Checkmk).

## Standort aus dem Host-Tag

Mit `--location-tag <Tag-Gruppe>` (z. B. `location`) liest das Export-Tool den Tag je Host per Livestatus: die **Tag-ID wird zum Standort-Code**, der Tag-Titel
(ohne führenden Code) zum Standortnamen. Neue Standorte werden angelegt; Geräte ohne Ort landen in der Location „Allgemein“. Eine genauere Platzierung
(Raum/Rack) am selben Standort bleibt bei erneutem Import erhalten, bei einem anderen Standort im Tag wird das Gerät dorthin verschoben. Hosts ohne Tag-Wert
(leer oder nur Striche) bleiben unverändert; ein ausdrücklich gesetztes `--site-code` hat Vorrang.
