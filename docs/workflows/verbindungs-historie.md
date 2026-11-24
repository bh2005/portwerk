# Verbindungs-Historie

Portwerk hält jede Verbindung (Kabel) mit **Gültigkeitszeitraum** fest: wann sie gesteckt wurde, von wem oder welchem Patchauftrag, und wann und warum sie getrennt wurde.
Geräte- und Portnamen von damals bleiben erhalten, auch wenn der Port inzwischen umbenannt oder gelöscht wurde.

## Historie öffnen

Die Historie erscheint als **Seitenleiste von rechts**. Schließen: Esc, Klick neben die Leiste oder das ×.

- **Für einen Port:** im Gerätedetail in der Port-Tabelle **Historie** neben dem Port.
- **Für ein ganzes Gerät:** im Gerätedetail die Zeile *Verbindungs-Historie* → **alle Ports anzeigen**. Aus der Port-Ansicht wechselt **alle Ports des Geräts** dorthin.
- **Aus dem Soll/Ist-Abgleich:** in der Zeile **Historie** – praktisch, um vor einer Korrektur zu sehen, was an dem Port früher gesteckt hat.

## Was die Leiste zeigt

Beispiel für `sw-a1:Gi0/3`:

```
sw-a1:Gi0/3 ↔ PP1:12                                            steckt
24.11.2026 09:12 · Cat6
hergestellt: PA-0042

sw-a1:Gi0/3 ↔ sw-a2:Gi0/7
12.03.2026 14:05 – 24.11.2026 09:11
hergestellt: anna · getrennt: PA-0042
```

- **grüner Rahmen / „steckt“** – aktuelle Verbindung, alle anderen sind beendet.
- **Zeitraum** – von/bis in Ortszeit.
- **hergestellt / getrennt** – Patchauftrag (anklickbar) oder Benutzer; bei beendeten Verbindungen zusätzlich der Grund, z. B. *(Assistent)*, *(direkt)*, *(Rückbau)* oder *(Port/Gerät gelöscht)*.
- **Gegenstelle** – anklickbar, springt zum Gerät (sofern es noch existiert).

## Stand zu einem Zeitpunkt

Im Feld **Stand am** einen Zeitpunkt wählen: Die Leiste zeigt dann nur die Verbindungen, die **zu diesem Zeitpunkt** steckten. **alle Zeitpunkte** hebt den Filter auf.
Für den Vergleich ganzer Standorte oder Räume gibt es die **Zeitreise** (Menü *Zeitreise*): Stand zu einem Datum und Unterschiede zwischen zwei Zeitpunkten.

## Beispiel: „Wer hat das umgesteckt?“

1. Der Abgleich meldet `sw-a1:Gi0/3` als *anderes Gerät*.
2. In der Zeile **Historie** öffnen.
3. Der oberste beendete Eintrag zeigt, dass die Verbindung zu `sw-a2:Gi0/7` am 24.11. durch Auftrag PA-0042 getrennt wurde – die Dokumentation wurde also nach dem Umstecken nicht nachgezogen.
4. Auftrag PA-0042 aus der Leiste öffnen und prüfen, ob die neue Verbindung dort erfasst ist.

## API

```bash
# Verbindungen eines Ports (neueste zuerst); optional Zeitpunkt
curl -H "X-Auth-Token: $TOKEN" 'https://opp.example.test/api/cable-history?port_id=4711'
curl -H "X-Auth-Token: $TOKEN" 'https://opp.example.test/api/cable-history?device_id=17&at=2026-06-01'
```

Die Historie wird durch Datenbank-Trigger gepflegt und ist deshalb auch dann vollständig, wenn Verbindungen indirekt verschwinden (z. B. Port oder Gerät gelöscht).
