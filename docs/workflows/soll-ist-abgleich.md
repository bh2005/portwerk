# Soll/Ist-Abgleich

Der Abgleich (Menü **Soll/Ist**) vergleicht die dokumentierte Verkabelung (**Soll**, auch über Patchfelder und Dosen hinweg) mit den per
LLDP/CDP gemeldeten Nachbarn (**Ist**). Die Nachbardaten kommen mit dem [Checkmk-Import](../checkmk-import.md).

## Ergebnisse

| Ergebnis | Bedeutung | Typische Maßnahme |
|---|---|---|
| stimmt | Soll und Ist passen zusammen | – |
| anderer Port | Gegengerät stimmt, der Port nicht | Dokumentation oder Patchung korrigieren |
| anderes Gerät | Am Port hängt etwas anderes als dokumentiert | Prüfen, ob umgesteckt wurde |
| nicht gesehen | Dokumentiert, aber kein Nachbar gemeldet | Kabel/Gerät prüfen (aus? defekt?) |
| **nicht dokumentiert** | Nachbar gesehen, aber keine Verbindung erfasst | **Verbindung übernehmen** |
| **Port unbekannt** | Der lokale Port fehlt im Bestand | **In Bestand übernehmen** |
| keine Daten | Für das Gerät liegen keine LLDP/CDP-Daten vor | – |

Chips über der Tabelle blenden Ergebnisse ein und aus, der Standortfilter und das Suchfeld grenzen weiter ein.

---

## Workflow 1: Verbindung übernehmen

**Wann:** Die Zeile steht auf *nicht dokumentiert*, und das Gegengerät samt Port ist im Bestand bekannt und noch frei.
Beispiel: `sw-a1:Gi0/3` meldet `sw-a2:Gi0/7`, aber es gibt kein Kabel dazwischen.

1. In der Zeile in der Spalte ganz rechts **Verbindung übernehmen** wählen. Der Link erscheint nur, wenn
   - der lokale Port noch kein Kabel hat,
   - genau **ein** Nachbar gemeldet ist,
   - dessen Port im Bestand bekannt und frei ist.
2. Die Rückfrage bestätigen: `sw-a1:Gi0/3 ↔ sw-a2:Gi0/7 als Direktkabel dokumentieren?`
3. Portwerk legt ein Kabel zwischen den beiden Ports an. Die Zeile wechselt auf *stimmt*, die Gegenseite (`sw-a2:Gi0/7`) verschwindet ebenfalls aus der Liste.

Das Kabel ist **vorläufig** markiert und trägt die Notiz „Aus Soll/Ist-Abgleich übernommen“. In der Port-Tabelle des Geräts steht neben der Verbindung das Kennzeichen *vorläufig*.

**Warum vorläufig?** Zwischen zwei Switchen liegen in der Praxis oft Dose und Patchfeld. Das Direktkabel dokumentiert „es besteht eine Verbindung“ und
lässt den Abgleich grün werden, ohne die Strecke zu behaupten.

### Später: Strecke vervollständigen

Wenn Sie die tatsächliche Strecke kennen (z. B. `sw-a1:Gi0/3 → PP1:12 → Dose B-04 → sw-a2:Gi0/7`), öffnen Sie in der Zeile **Strecke** (oder im Gerätedetail **Verbindung**)
und fügen am Kabel mit **+ Zwischenstation** Patchfeld und Dose ein, siehe [Strecken-Editor](strecken-editor.md#zwischenstation-einfügen). Der Abgleich läuft weiter über Patchfelder und Dosen
und zeigt weiterhin *stimmt*.

Bleibt das Direktkabel richtig, genügt in der Leiste **Strecke vollständig** (oder in der Port-Tabelle **vollständig** neben dem Kennzeichen *vorläufig*). Danach gilt die Verbindung als abschließend dokumentiert.

**Alle noch offenen Kabel auflisten:**

```bash
curl -H "X-Auth-Token: $TOKEN" 'https://opp.example.test/api/cables?provisional=true'
```

---

## Workflow 2: Gerät in den Bestand übernehmen

**Wann:** In der Ist-Spalte steht neben dem Nachbarn *nicht im Bestand*. Beispiel:

| Ergebnis | Gerät : Port | Ist |
|---|---|---|
| Port unbekannt | `sw-a1:2` | `AP-LAGER-01.example.test:Gi0` · LLDP · nicht im Bestand |

1. Hinter dem Nachbarn auf **In Bestand übernehmen** klicken. Die Seitenleiste öffnet sich.
2. Angaben prüfen und anpassen:
   - **Hostname** – vorbelegt mit dem Kurznamen in Kleinbuchstaben (`ap-lager-01`).
   - **Typ** – Vorschlag aus den gemeldeten Fähigkeiten (z. B. *WLAN AP* → Access Point, *Bridge* → Switch, sonst *Sonstiges*). Der Vorschlag ist nur ein Hinweis, im Zweifel selbst wählen.
   - **Verwaltungs-IP** – aus der Meldung, falls vorhanden.
   - **Port am neuen Gerät** – vorbelegt (`Gi0`); leer lassen, wenn kein Port angelegt werden soll.
   - **Verbindung als vorläufiges Direktkabel dokumentieren** – angehakt, sobald ein Port angegeben ist.
3. **Übernehmen.**

**Was angelegt wird**

- das Gerät `ap-lager-01` am **selben Ort** wie das meldende Gerät (`sw-a1`),
- der Port `Gi0` am neuen Gerät,
- der bisher unbekannte lokale Port `2` an `sw-a1` (Zeile *Port unbekannt*),
- das vorläufige Direktkabel `sw-a1:2 ↔ ap-lager-01:Gi0`.

Danach steht die Zeile auf *stimmt*. Ort, Modell und weitere Angaben lassen sich im Gerätedetail nachpflegen.

**Nicht angeboten wird der Link** bei reinen MAC-Adressen als Nachbarname (Telefone, Kameras ohne Namen) und bei Geräten, die schon im Bestand sind.

---

## Workflow 3: Fehlenden Host in Checkmk anlegen

**Voraussetzung:** Die [Checkmk-Anbindung](checkmk-anbindung.md) ist eingerichtet, und Sie haben eine globale Berechtigung.

Im selben Dialog (Workflow 2) erscheint ein Block **Checkmk**. Er prüft beim Öffnen, ob der Host unter dem eingetragenen Hostnamen in Checkmk existiert:

- **In Checkmk vorhanden** – grün, mit Ordner und IP. Es ist nichts weiter zu tun.
- **Nicht in Checkmk vorhanden** – orange. Dann:
  1. **Ordner in Checkmk** wählen (vorbelegt mit dem Standardordner aus der Verwaltung).
  2. **Standort-Tag (location)** prüfen: vorbelegt mit dem Standortcode des meldenden Geräts, z. B. `LOC026`. Leer lassen, wenn das Gerät kein Standort-Tag bekommen soll.
  3. **In Checkmk anlegen (nur Ping)** klicken.

Portwerk legt den Host mit diesen Eigenschaften an:

| Eigenschaft | Wert |
|---|---|
| Ordner | der gewählte (z. B. `/portwerk`) |
| IP-Adresse | die Verwaltungs-IP aus dem Dialog |
| Agent / SNMP | **keiner** (`no-agent`, `no-snmp`) – es läuft nur der Host-Check, also Ping |
| Standort-Tag | `tag_location=LOC026` |
| Label | `source=portwerk` (damit man solche Hosts in Checkmk wiederfindet) |

> **Wichtig:** Der Host ist danach eine **ausstehende Änderung** in Checkmk. Portwerk aktiviert nie selbst.
> Ein Checkmk-Administrator aktiviert die Änderung (*Setup → Änderungen aktivieren*). Erst dann wird der Host überwacht.

**Typischer Gesamtablauf** für ein neu entdecktes Gerät:

1. Abgleich öffnen, Filter *Port unbekannt* / *nicht dokumentiert*.
2. Gerät in den Bestand übernehmen (Workflow 2) **und** im selben Dialog in Checkmk anlegen (Workflow 3).
3. In Checkmk die ausstehende Änderung aktivieren.
4. Beim nächsten Checkmk-Import bekommt das Gerät dort seinen Überwachungsstatus; bei Bedarf in Checkmk auf Agent/SNMP umstellen.

---

## Rechte

| Aktion | Erforderlich |
|---|---|
| Abgleich ansehen | angemeldet, Leserecht auf den Standort |
| Verbindung übernehmen | Schreibrecht auf **beide** Standorte der Ports |
| Gerät in den Bestand übernehmen | Schreibrecht am Standort des meldenden Geräts |
| Host in Checkmk anlegen | Schreibrecht **und** globale Berechtigung |

Jede Übernahme steht im Audit-Log (`cable.adopt`, `device.adopt`, `checkmk.host.create`).

## API

```bash
# Abgleich (optional nach Standort und Ergebnis filtern)
curl -H "X-Auth-Token: $TOKEN" 'https://opp.example.test/api/compare?site_id=3&status=undocumented,unmapped'

# Verbindung übernehmen (Port des Geräts, das den Nachbarn meldet)
curl -X POST -H "X-Auth-Token: $TOKEN" -H 'Content-Type: application/json' \
     -d '{"port_id": 4711}' https://opp.example.test/api/compare/adopt

# Gerät in den Bestand übernehmen (obs_id steht in der Ist-Zeile des Abgleichs)
curl -X POST -H "X-Auth-Token: $TOKEN" -H 'Content-Type: application/json' \
     -d '{"obs_id": 12703, "hostname": "ap-lager-01", "type": "ap", "mgmt_ip": "192.0.2.10",
          "neighbor_port": "Gi0", "create_cable": true}' https://opp.example.test/api/compare/adopt-device
```

Fehlercodes: `409` – nicht übernehmbar (Port schon verbunden, Nachbar nicht eindeutig oder Gerät bereits im Bestand), `403` – Berechtigung fehlt, `400` – Typ ungültig.
