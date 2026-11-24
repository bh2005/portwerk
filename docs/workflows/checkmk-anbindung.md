# Checkmk-Anbindung (REST-API)

Mit der REST-Anbindung kann Portwerk **prüfen**, ob ein Gerät in Checkmk existiert, und es als Host **anlegen**. Das ist unabhängig vom
[Checkmk-Import](../checkmk-import.md) (Inventar und LLDP/CDP-Nachbarn nach Portwerk): Dort schiebt ein Skript auf dem Checkmk-Server Daten
nach Portwerk, hier fragt Portwerk Checkmk selbst.

Sicherheitsprinzipien:

- **Eigener Automation-User** mit minimalen Rechten, nicht der Admin.
- **Aktivierung nur ohne fremde Änderungen.** Portwerk legt Hosts als ausstehende Änderung an. Aktivieren lässt sich in Checkmk oder auf Knopfdruck in Portwerk – dort nur, wenn **alle** ausstehenden
  Änderungen vom Portwerk-User stammen. Fremde, noch nicht fertige Änderungen anderer Administratoren werden nie mitaktiviert (Portwerk verweigert, und der User hat kein Recht auf `wato.activateforeign`).
- Neue Hosts bekommen **nur den Host-Check (Ping)**.

## 1. In Checkmk einrichten

Per REST-API (als Administrator, Site `mysite`; Beispiel mit curl):

```bash
B=http://checkmk.example.test/mysite/check_mk/api/1.0
A='Authorization: Bearer admin-user geheim'        # Automation-User mit Adminrechten
H='Content-Type: application/json'

# 1. Rolle „portwerk“ als Klon der Rolle „user“ anlegen
curl -X POST -H "$A" -H "$H" $B/domain-types/user_role/collections/all \
     -d '{"role_id": "user", "new_role_id": "portwerk", "new_alias": "Portwerk (Hosts anlegen, keine Aktivierung)"}'

# 2. Rechte: alle Ordner sehen; Aktivieren erlauben (nur eigene Änderungen), Verwerfen entziehen
curl -X PUT -H "$A" -H "$H" -H 'If-Match: *' $B/objects/user_role/portwerk \
     -d '{"new_permissions": {"wato.all_folders": "yes", "wato.see_all_folders": "yes", "wato.activate": "yes", "wato.activateforeign": "no", "wato.discard": "no"}}'

# 3. Automation-User mit eigenem Secret
curl -X POST -H "$A" -H "$H" $B/domain-types/user_config/collections/all \
     -d '{"username": "portwerk", "fullname": "Portwerk (Automation)",
          "auth_option": {"auth_type": "automation", "secret": "<langes-zufälliges-secret>"},
          "roles": ["portwerk"], "disable_login": false}'
```

Die Rolle `user` bringt bereits die Rechte zum Lesen, Anlegen und Bearbeiten von Hosts mit (`wato.use`, `wato.hosts`, `wato.edit_hosts`, `wato.manage_hosts`).
Das Recht **„Manage tags“** (`wato.hosttags`) bekommt der User bewusst **nicht**; es würde auch das Ändern der Tag-Gruppen erlauben.

Alternativ lassen sich Rolle und User in der Checkmk-Oberfläche anlegen (*Setup → Users → Roles & permissions* bzw. *Users*).

## 2. In Portwerk verbinden

Verwaltung → **Checkmk** → Abschnitt **REST-API: Hosts prüfen und anlegen**:

| Feld | Beispiel | Hinweis |
|---|---|---|
| Anbindung aktiv | ☑ | |
| Adresse der Site (API) | `https://checkmk.example.test/mysite` | ohne `/check_mk/api`; nach Möglichkeit **https** |
| Automation-User | `portwerk` | |
| Secret | (das oben vergebene) | wird nie wieder angezeigt; leer lassen = unverändert |
| Standardordner für neue Hosts | `/portwerk` | Pfad, im Dialog je Host änderbar |
| Zertifikat prüfen / CA | | nur bei https; eigene CA als PEM einfügbar |

**Verbindung testen** muss „Verbunden: Checkmk 2.x …, N Ordner sichtbar“ melden.

> Das Secret liegt in der Portwerk-Datenbank (und damit in deren Sicherungen). Bei einem Verdacht auf Verlust das Secret in Checkmk neu setzen und hier eintragen.
> Bei `http://` geht das Secret unverschlüsselt über das Netz – das ist nur in einem abgeschotteten internen Netz vertretbar.

## 3. Verwenden

Siehe [Soll/Ist-Abgleich, Workflow 3](soll-ist-abgleich.md#workflow-3-fehlenden-host-in-checkmk-anlegen). Kurzfassung:
Beim Übernehmen eines unbekannten Geräts zeigt Portwerk, ob der Host in Checkmk existiert, und bietet bei „nicht vorhanden“ **In Checkmk anlegen (nur Ping)** an.

Was Portwerk an die API schickt (Beispiel):

```json
POST /domain-types/host_config/collections/all?bake_agent=false
{
  "host_name": "ap-lager-01",
  "folder": "/portwerk",
  "attributes": {
    "ipaddress": "192.0.2.10",
    "tag_address_family": "ip-v4-only",
    "tag_agent": "no-agent",
    "tag_snmp_ds": "no-snmp",
    "tag_location": "LOC026",
    "labels": {"source": "portwerk"}
  }
}
```

### Standort-Tag

Hosts bekommen das Tag der Gruppe `location` (Attribut `tag_location`). Der Wert wird aus dem **Standortcode** des meldenden Geräts übernommen
(`LOC026`) und ist im Dialog änderbar. Voraussetzung ist, dass Ihre Checkmk-Tag-Gruppe `location` Werte hat, die den Portwerk-Standortcodes entsprechen
(das ist der Fall, wenn die Standorte aus dem Checkmk-Import stammen). Existiert der Wert in Checkmk nicht, lehnt Checkmk das Anlegen ab, und Portwerk
meldet „Das Standort-Tag … gibt es in Checkmk nicht“.

Andere Tag-Gruppen (z. B. Criticality) setzt Portwerk nicht; es gelten die Vorgaben und Ordnerattribute von Checkmk.

### Danach: aktivieren

Der Host steht als **ausstehende Änderung** da. Es gibt zwei Wege:

- **In Checkmk:** *Setup → Änderungen aktivieren*. Dort sehen Sie auch Änderungen anderer Administratoren.
- **In Portwerk:** Nach dem Anlegen erscheint im Dialog **Ausstehende Änderungen in Checkmk** mit der Liste (Benutzer und Text je Änderung) und dem Button **In Checkmk aktivieren**; derselbe Block steht unter *Verwaltung → Checkmk*.
  Nach einer Rückfrage aktiviert Portwerk die Site und wartet, bis Checkmk fertig ist.

Portwerk aktiviert **nur**, wenn alle ausstehenden Änderungen vom Portwerk-User stammen. Gibt es fremde, ist der Button gesperrt und die Meldung nennt die Benutzer
(„Es gibt 1 fremde ausstehende Änderung(en) von anna – bitte in Checkmk prüfen und dort aktivieren“). Läuft in Checkmk gerade eine Aktivierung, kommt „bitte kurz warten“.
Die Aktivierung nutzt nie `force_foreign_changes`.

Wer die Hosts wiederfinden will, filtert in Checkmk nach dem Label `source:portwerk` oder nach dem Ordner.

## Fehlerbilder

| Meldung in Portwerk | Ursache | Abhilfe |
|---|---|---|
| Die Checkmk-Anbindung ist nicht eingerichtet | Anbindung aus oder Zugangsdaten fehlen | Verwaltung → Checkmk |
| Checkmk nicht erreichbar | Adresse falsch, Firewall, Dienst nicht erreichbar | Adresse/Netz prüfen; vom Portwerk-Server aus `curl <adresse>/check_mk/api/1.0/version` (erwartet 401) |
| Checkmk lehnt die Anmeldung/Berechtigung ab (401) | User oder Secret falsch | Secret in Checkmk neu setzen und eintragen |
| … Berechtigung ab (403) mit „you lack the permission …“ | Rolle des Users zu knapp | Rolle prüfen (siehe Abschnitt 1) |
| Der Host existiert in Checkmk bereits | Hostname schon vergeben (evtl. in anderem Ordner) | Host in Checkmk suchen; andere Schreibweise |
| Hostname ungültig | Leerzeichen/Sonderzeichen | erlaubt sind Buchstaben, Ziffern, `_`, `.` und `-` |
| Das Standort-Tag … gibt es in Checkmk nicht | Standortcode ist kein Wert der Tag-Gruppe `location` | anderen Wert wählen oder leer lassen |
| Hosts in Checkmk anlegen nur mit globaler Berechtigung | Benutzer ist auf Standorte begrenzt | Aufgabe an einen globalen Benutzer geben |
| Es gibt N fremde ausstehende Änderung(en) von … | Andere Administratoren haben noch nicht aktivierte Änderungen | in Checkmk prüfen und dort aktivieren |
| In Checkmk läuft gerade eine Aktivierung | gleichzeitige Aktivierung | kurz warten, erneut versuchen |
| … lehnt die Berechtigung ab (403) beim Aktivieren | Rolle hat kein `wato.activate` | Recht in der Rolle `portwerk` ergänzen (siehe Abschnitt 1) |

## API

```bash
# Ist der Host in Checkmk vorhanden?
curl -H "X-Auth-Token: $TOKEN" 'https://opp.example.test/api/checkmk/host?name=ap-lager-01'
# → {"exists": true, "host_name": "ap-lager-01", "folder": "/portwerk", "ipaddress": "192.0.2.10", "labels": {...}}

# Ordner in Checkmk
curl -H "X-Auth-Token: $TOKEN" https://opp.example.test/api/checkmk/folders

# Ausstehende Änderungen in Checkmk (eigene und fremde)
curl -H "X-Auth-Token: $TOKEN" https://opp.example.test/api/checkmk/pending
# → {"count": 2, "own": 2, "foreign": 0, "changes": [{"user": "portwerk", "text": "…", "time": "…"}], "site": "mysite"}

# Aktivieren (nur ohne fremde Änderungen; 409 sonst)
curl -X POST -H "X-Auth-Token: $TOKEN" https://opp.example.test/api/checkmk/activate
# → {"activated": true, "message": "2 Änderung(en) aktiviert.", "count": 2, "site": "mysite"}

# Host anlegen (nur Ping, ausstehende Änderung)
curl -X POST -H "X-Auth-Token: $TOKEN" -H 'Content-Type: application/json' \
     -d '{"hostname": "ap-lager-01", "ip": "192.0.2.10", "folder": "/portwerk", "location_tag": "LOC026"}' \
     https://opp.example.test/api/checkmk/hosts
# → {"host_name": "ap-lager-01", "folder": "/portwerk", "ping_only": true, "pending_activation": true, "location_tag": "LOC026"}
```
