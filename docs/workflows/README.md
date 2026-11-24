# Workflows

Beschreibungen der wichtigsten Abläufe in Portwerk, jeweils mit Beispielen. Die Beispiele verwenden frei erfundene Namen
(`sw-a1`, `ap-lager-01`, `LOC026`, `example.test`).

| Dokument | Worum es geht |
|---|---|
| [Soll/Ist-Abgleich](soll-ist-abgleich.md) | Verbindungen und Geräte aus LLDP/CDP übernehmen, vorläufige Kabel vervollständigen, Hosts in Checkmk anlegen |
| [Checkmk-Anbindung](checkmk-anbindung.md) | Automation-User und Rolle in Checkmk einrichten, Portwerk verbinden, Fehlerbilder |
| [Strecken-Editor](strecken-editor.md) | Die ganze Strecke ansehen und bearbeiten: Kabel, Zwischenstationen einfügen und entfernen, LLDP/CDP-Abgleich der Enden |
| [Sicherung auf externe Ziele](sicherung-extern.md) | Sicherungen zusätzlich auf NAS (NFS/SMB), S3 oder WebDAV ablegen, optional verschlüsselt; Wiederherstellung von dort |
| [Verbindungs-Historie](verbindungs-historie.md) | Frühere Verbindungen eines Ports oder Geräts in der Seitenleiste |
| [Releases](releases.md) | Änderungen je Version in der Verwaltung, Changelog pflegen |

Weitere Dokumente: [Konzept](../konzept.md), [Import aus Checkmk](../checkmk-import.md), [Anbindung an OpenPlan](../openplan.md).

## Grundsätze, die in allen Workflows gelten

- **Nichts passiert ohne Rückfrage.** Jede Übernahme zeigt vorher, was angelegt wird.
- **Vorläufig statt falsch.** Was aus dem Ist (LLDP/CDP) übernommen wird, ist als *vorläufig* markiert, bis jemand die Strecke vollständig dokumentiert hat.
- **Portwerk aktiviert nie in Checkmk.** Hosts werden als ausstehende Änderung angelegt, die Aktivierung bleibt bei den Checkmk-Administratoren.
- **Detailansichten kommen als Seitenleiste von rechts** (Esc oder Klick daneben schließt). Das gilt für die Historie, WAN-Details und den Übernehmen-Dialog.
