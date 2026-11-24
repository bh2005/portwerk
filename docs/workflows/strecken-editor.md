# Strecken-Editor

Eine **Strecke** ist die Folge von Kabeln und Stationen zwischen zwei aktiven Geräten, z. B.
`sw-a1:Gi0/3 → Patchfeld PP1:12 ⇄ 12-hinten → Dose B-04 → sw-a2:Gi0/7`. Der Strecken-Editor zeigt sie als Ganzes und lässt jedes Kabel und jede Zwischenstation
direkt bearbeiten.

## Öffnen

- **Gerätedetail:** in der Port-Tabelle **Verbindung** am Port. (**Pfad** daneben zeigt weiterhin nur die Grafik, auch zu einem früheren Zeitpunkt.)
- **Soll/Ist-Abgleich:** in der Zeile **Strecke**.

Die Leiste öffnet sich von rechts (Esc oder Klick daneben schließt).

## Aufbau

```
Strecke ab sw-a1:Gi0/3
┌ ANFANG ─────────────────────────────────────────────┐
│ sw-a1 : Gi0/3                                        │
│ ✓ LLDP/CDP: sw-a1 sieht sw-a2:Gi0/7                  │
└──────────────────────────────────────────────────────┘
   │ K-017  Cat6 · 2 m · blau          [bearbeiten] [+ Zwischenstation] [lösen]
┌ ZWISCHENSTATION ─────────────────────── [entfernen] ┐
│ PP1 : 12 ⇄ 12-hinten                                 │
└──────────────────────────────────────────────────────┘
   │ K-018  Cat6a · 40 m               [bearbeiten] [+ Zwischenstation] [lösen]
┌ ENDE ────────────────────────────────────────────────┐
│ sw-a2 : Gi0/7                                        │
│ ✓ LLDP/CDP: sw-a2 sieht sw-a1:Gi0/3                  │
└──────────────────────────────────────────────────────┘
                                   [Strecke vollständig]
```

- **Anfang und Ende** stehen immer oben und unten. Sind beide Enden aktive Geräte mit LLDP/CDP-Daten, steht dort das **Ist** (✓ stimmt, ✗ weicht ab mit Angabe, was gesehen wird, ○ keine Daten).
- **Kabel** zeigen Nummer, Typ, Länge und Farbe; ein ✓/✗ steht für das Messergebnis. **Gestrichelt und „vorläufig“** sind aus dem Soll/Ist-Abgleich übernommene Kabel.
- **Stationen** zeigen Gerät, Ort, beide Ports (vorn ⇄ hinten) sowie Planungen, Reservierungen und das VLAN/Portprofil.
- **Grafik** klappt die bekannte Pfadgrafik darunter auf.

## Workflows

### Kabel bearbeiten

**bearbeiten** am Kabel klappt die Felder auf: Nummer/Label, Typ, Fasern/Adern, Länge, Farbe, Verlegt am, Messprotokoll, Messergebnis, Notiz und das Kennzeichen *vorläufig*. **Speichern** übernimmt die Änderung.
Beispiel: Zu `K-018` die gemessene Länge `41,5` und das Protokoll `FLUKE-2026-114` mit Ergebnis ✓ eintragen.

### Zwischenstation einfügen

Typischer Fall: Die Verbindung wurde aus dem Abgleich als Direktkabel übernommen, später stellt sich heraus, dass sie über ein Patchfeld läuft.

1. Am Kabel **+ Zwischenstation** wählen.
2. Patchfeld oder Dose suchen und den **Port** wählen. Die Gegenseite (hinten) ergibt sich aus der Durchschleifung. Gewählt werden können nur Ports, deren beide Seiten frei sind.
3. Die Vorschau zeigt die Reihenfolge, z. B. `sw-a1:Gi0/3 → PP1:12 ⇄ 12-hinten → sw-a2:Gi0/7`. Stimmt die Richtung nicht, **Seiten tauschen** anhaken.
4. **Einfügen.** Das alte Kabel wird beendet (die Historie bleibt), es entstehen `sw-a1:Gi0/3 → PP1:12` und `PP1:12-hinten → sw-a2:Gi0/7`.

Das erste Teilkabel behält Nummer, Länge und Einbaudatum des alten Kabels; beide behalten Kabelart, Farbe und das Kennzeichen *vorläufig*. Das Messprotokoll gehört zum alten Kabel und wird nicht übernommen.
Mehrere Stationen hintereinander (Patchfeld → Dose) fügt man nacheinander ein: bei jedem weiteren Mal am passenden Kabel **+ Zwischenstation**.

### Zwischenstation entfernen

**entfernen** an der Station: Die beiden Kabel werden zu **einem vorläufigen Direktkabel** (Daten des ersten Kabels, Notiz „Zwischenstation entfernt“). Nur möglich, wenn die Station auf **beiden** Seiten verbunden ist; sonst stattdessen das Kabel lösen.

### Umstecken (Ziel ändern)

**umstecken** am Kabel: Sie wählen das **Ende**, das an einen anderen Port soll, suchen das neue Gerät und den freien Port. Die Vorschau zeigt das Ergebnis, z. B. statt
`sw-a1:Gi0/3 → sw-a2:Gi0/7` jetzt `sw-a1:Gi0/3 → sw-a3:Gi0/9`. Das Kabel behält **alle Angaben** (Nummer, Typ, Länge, Messprotokoll, Kennzeichen *vorläufig*);
in der Historie endet die alte Verbindung, die neue beginnt. Der neue Port muss frei sein; ist er reserviert oder verplant, fragt Portwerk nach.

### Kabel lösen und neu verbinden

**lösen** trennt ein Kabel (mit Rückfrage). An einem **offenen Ende** (Station ohne Anschluss) oder an einem unverbundenen Port erscheint **+ Verbindung herstellen**:
Zielgerät suchen, Port wählen, Kabeldaten eintragen, **Verbinden**. Ist der Zielport reserviert, fragt Portwerk nach.

### Strecke vollständig melden

Sind noch Kabel als *vorläufig* markiert, setzt **Strecke vollständig** im Fuß der Leiste das Kennzeichen an allen Kabeln der Strecke zurück.

## Hinweise

- Alle Änderungen laufen in einer Transaktion (alles oder nichts) und stehen in der [Verbindungs-Historie](verbindungs-historie.md) und im Audit-Log (`cable.insert_station`, `cable.remove_station`).
- Schreibrecht braucht man an den Standorten **aller** beteiligten Enden.
- Die Strecken-Ansicht folgt Durchschleifungen nur über Patchfelder und Dosen; sie endet am ersten aktiven Gerät (Switch, Router, Firewall, Server …).

## API

```bash
# Strecke ab einem Port (Stationen, Kabel samt Details, LLDP-Abgleich der Enden)
curl -H "X-Auth-Token: $TOKEN" https://opp.example.test/api/ports/4711/path

# Patchfeld in ein Kabel einfügen: port_id = Port der Station, der zu side_port_id zeigt
curl -X POST -H "X-Auth-Token: $TOKEN" -H 'Content-Type: application/json' \
     -d '{"port_id": 5120, "side_port_id": 4711}' https://opp.example.test/api/cables/88/insert-station

# Kabelende umstecken (Kabel behält seine Angaben)
curl -X POST -H "X-Auth-Token: $TOKEN" -H 'Content-Type: application/json' \
     -d '{"end_port_id": 4711, "new_port_id": 4802}' https://opp.example.test/api/cables/88/move-end

# Station entfernen (einer ihrer beiden Ports genügt)
curl -X POST -H "X-Auth-Token: $TOKEN" -H 'Content-Type: application/json' \
     -d '{"port_id": 5120}' https://opp.example.test/api/stations/remove
```

Fehlercodes: `400` – kein Patchfeld/keine Dose, Gegenseite fehlt oder ungültiger Port, `409` – Station bzw. neuer Port schon verbunden, bzw. Station nur einseitig verbunden, `404` – Kabel/Port nicht gefunden.
