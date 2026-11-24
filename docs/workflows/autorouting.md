# Autorouting

Das Autorouting plant die **fehlenden Patchungen** zwischen einem Quellport (z. B. der Netzwerkkarte eines Servers) und einem Zielport (z. B. einem Switchport) automatisch
und legt daraus einen Patchauftrag an. Ist die Quelle ein neues Gerät, wird es mit angelegt – als **geplant**.

## Wo

- **Racks & Schränke → Autorouting:** Quelle ist ein **neues Gerät** in dem gewählten Rack.
- **Gerät → Port → Autorouting** (bei Ports ohne Kabel an aktiven Geräten): Quelle ist dieser **vorhandene Port**.

Erforderlich ist die Rolle *Planer* am Standort.

## Workflow: neuen Server anbinden

Beispiel: Ein neuer Server `srv-db-07` kommt in `Rack1`, `NIC1` soll auf `SW-03` Port `Gi0/2` (Rack3, selber Raum).

1. In der Rack-Ansicht **Autorouting** wählen, Quelle *neues Gerät (als „geplant“ anlegen)*.
2. Hostname `srv-db-07`, Rack `Rack1`, Typ *Server*, Höhe (HE) und – falls gewünscht – Position, **Netzwerk-Ports** `NIC` × `2`, Medium `RJ45`, **Port für die Route** `NIC1`.
   Der Assistent legt die Ports als einfache Portgruppe an (`NIC1` … `NICn`). Geräte aus einem Katalogmodell legen Sie wie bisher mit dem Geräte-Assistenten an und wählen sie danach als *vorhandenen Port*.
3. Ziel: `SW-03` suchen und den Port `Gi0/2` wählen.
4. **Route suchen.** Portwerk zeigt bis zu drei Vorschläge, der erste ist der empfohlene:

   ```
   ● srv-db-07:NIC1
   [neu]        → PP-R1:F7            neues Patchkabel (im selben Rack)
   [Station]    → PP-R1:B7            Durchschleifung vorn → hinten
   [vorhanden]  → PP-R3:B7            vorhandener Trunk
   [Station]    → PP-R3:F7
   [neu]        → SW-03:Gi0/2         neues Patchkabel (im selben Rack)
   ```
   „2 neue Patchkabel, 2 Stationen, 1 vorhandenes Kabel“.
5. Vorschlag wählen, bei Bedarf Titel und Kabelart (Standard: passend zum Medium, z. B. Cat6) anpassen, **Patchauftrag anlegen**.

Ergebnis: ein Patchauftrag (Entwurf) mit
- **Einbau** von `srv-db-07` (das Gerät steht mit Status *geplant* im Rack; es gilt nach der Bestätigung des Auftrags als eingebaut),
- einer Position **herstellen** je neuem Patchkabel: `srv-db-07:NIC1 ↔ PP-R1:F7` und `PP-R3:F7 ↔ SW-03:Gi0/2`.

Alle beteiligten Ports sind danach **verplant**; eine zweite Route weicht automatisch auf andere Ports aus.

## Wie die Route gefunden wird

- **Vorhandenes ist fest und kostenlos:** dokumentierte Kabel und die Durchschleifung vorn ↔ hinten an Patchfeldern und Dosen (*Stationen*). Ein Weg darf bis zu **3 Stationen** enthalten
  (z. B. Patchfeld → Dose → Patchfeld) und höchstens **3 neue Patchkabel**.
- **Neu geplant werden nur Patchkabel,** und zwar von der Quelle zu einem freien Patchfeld-Port, von einem freien Patchfeld-Port zum Zielport und – nur wenn nötig – zwischen zwei Patchfeld-Ports.
  Hängt der Zielport schon an der Strecke, entfällt das letzte Patchkabel.
- **Nähe:** Ein neues Patchkabel verbindet nur Ports **im selben Raum** (nächster Raum über der Location, sonst die übergeordnete Location). Im selben Rack ist es günstiger als zwischen Racks.
  Ein **direktes** Kabel von der Quelle zum Ziel gibt es nur, wenn beide im selben Rack stehen; zwischen Racks wird über Patchfelder gerangiert.
- **Frei** heißt: kein Kabel, nicht reserviert, nicht von einem offenen Auftrag verplant, Gerät nicht außer Betrieb. Ein Patchfeld-Port muss außerdem eine dokumentierte Gegenseite haben.
- **Medium:** Kupfer (RJ45) und Glasfaser (LWL/SFP …) werden nicht gemischt.
- **Auswahl:** Gesucht wird nach wenigsten neuen Patchkabeln, dann nach wenigsten Kabeln zwischen Racks, dann nach wenigsten Stationen. Alternativen unterscheiden sich in den neuen Patchkabeln.

## Wenn keine Route gefunden wird

Die Meldung nennt den Grund, z. B.:

| Meldung | Maßnahme |
|---|---|
| Im Raum des Quellgeräts gibt es keinen freien Patchfeld-Port (mit dokumentierter Gegenseite) | Patchfeld ergänzen oder Ports freigeben/Gegenseite dokumentieren |
| Im Raum des Zielgeräts gibt es keinen freien Patchfeld-Port | dito |
| Keine durchgängige dokumentierte Verbindung zwischen den beiden Räumen | Trunks zwischen den Patchfeldern dokumentieren (Strecken-Editor) |
| Weg länger als 3 Stationen bzw. 3 neue Patchkabel | Strecke vereinfachen oder von Hand planen |
| Quelle und Ziel liegen an verschiedenen Standorten | Autorouting plant nur innerhalb eines Standorts |

## API

```bash
# Vorschau (dry_run ist der Standard): vorhandener Quellport
curl -X POST -H "X-Auth-Token: $TOKEN" -H 'Content-Type: application/json' \
     -d '{"source_port_id": 4711, "target_port_id": 5120}' https://opp.example.test/api/routing/plan

# neues Gerät als geplant anlegen und Auftrag erzeugen
curl -X POST -H "X-Auth-Token: $TOKEN" -H 'Content-Type: application/json' \
     -d '{"dry_run": false, "route_index": 0, "workorder_title": "Server srv-db-07 anbinden",
          "new_device": {"hostname": "srv-db-07", "type": "server", "location_id": 42, "nic_count": 2},
          "source_port_name": "NIC1", "target_port_id": 5120}' https://opp.example.test/api/routing/plan
```

Die Antwort enthält `routes` (je Weg `cords` = neue Patchkabel, `steps` = alle Teilstücke, `summary`) und beim Anlegen `workorder` und `device_id`. Fehlercodes: `400` – Eingabe unpassend (z. B. Ziel an Patchfeld, verschiedene Standorte),
`403` – Rolle *Planer* fehlt, `409` – keine Route, Hostname vergeben oder Ports belegt/reserviert.
