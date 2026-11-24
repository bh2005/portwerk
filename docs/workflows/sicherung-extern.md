# Sicherung auf externe Ziele

Portwerk legt Sicherungen nicht nur im Datenverzeichnis des Servers ab (`backups/`), sondern auf Wunsch zusätzlich auf **externen Zielen**: einem eingehängten NAS-Verzeichnis (NFS/SMB),
einem S3-Speicher oder einem WebDAV-Server. So überlebt die Sicherung den Ausfall des Servers.

Einrichten unter **Verwaltung → Sicherung → Externe Sicherungsziele**.

## Ziel-Typen

| Typ | Für | Hinweis |
|---|---|---|
| **Verzeichnis** | NAS-Freigabe per NFS oder SMB, USB-Platte, beliebiger Mount | Das Verzeichnis liegt **im Container**. Die Freigabe wird auf dem Docker-Host als Volume eingebunden (Beispiel unten). |
| **S3 / S3-kompatibel** | Amazon S3, MinIO, Ceph RGW, viele Objektspeicher | Signatur Version 4; ohne Endpunkt gilt Amazon S3 (`bucket.s3.<region>.amazonaws.com`), mit Endpunkt Pfad-Stil (`host/bucket`) oder Host-Stil. |
| **WebDAV** | Nextcloud, ownCloud, viele NAS | Benutzer und Passwort; der Ordner wird bei Bedarf angelegt. |

SFTP gibt es (noch) nicht.

## Workflow 1: NAS per NFS einbinden und als Ziel eintragen

1. In der `docker-compose.yml` auf dem Host das NFS-Share als Volume definieren und in den Container einhängen:

   ```yaml
   services:
     portwerk:
       volumes:
         - opp-data:/data
         - nas-backup:/backup-extern
   volumes:
     opp-data:
     nas-backup:
       driver: local
       driver_opts:
         type: nfs
         o: "addr=nas.example.test,rw,nfsvers=4"
         device: ":/export/portwerk"
   ```

   Für **SMB** nimmt man `type: cifs`, `o: "addr=nas.example.test,username=...,password=...,vers=3.0"` und `device: "//nas.example.test/portwerk"`.
2. `docker compose up -d`.
3. In Portwerk **+ Ziel hinzufügen**: Typ *Verzeichnis*, Name `NAS Rechenzentrum`, Verzeichnis `/backup-extern`, aufbewahren z. B. `30`. **Speichern**.
4. **Testen**: Portwerk schreibt eine Testdatei und löscht sie wieder („Verzeichnis /backup-extern ist beschreibbar“).

## Workflow 2: S3 oder MinIO

1. Bucket und einen Zugang mit Schreib-, Lese- und Löschrecht auf den Bucket (bzw. den Ordner) anlegen.
2. **+ Ziel hinzufügen**: Typ *S3*, Name `Archiv`. Beispiele:

   | Feld | MinIO | Amazon S3 |
   |---|---|---|
   | Endpunkt | `https://minio.example.test:9000` | leer |
   | Bucket | `sicherungen` | `mein-bucket` |
   | Region | `us-east-1` | `eu-central-1` |
   | Ordner im Bucket | `portwerk/prod` | `portwerk/prod` |
   | Pfad-Stil | ☑ | – |

   Zugangsschlüssel und Secret eintragen; bei eigener CA das CA-Zertifikat als PEM einfügen.
3. **Testen** legt ein Testobjekt an und löscht es.

## Workflow 3: WebDAV (Nextcloud)

**+ Ziel hinzufügen**: Typ *WebDAV*, Adresse `https://cloud.example.test/remote.php/dav/files/benutzer`, Benutzer und (App-)Passwort, Ordner `Sicherungen/portwerk`. **Testen**.

## Was übertragen wird

- **Automatisch:** Nach jeder täglichen Sicherung werden alle aktiven Ziele bedient.
- **Manuell:** Nach **Jetzt sichern** läuft die Übertragung im Hintergrund; der Status steht am Ziel. In der Liste der Sicherungen überträgt **Extern ablegen** eine vorhandene Sicherung (erneut) auf alle aktiven Ziele.
- **Nicht übertragen** werden die Sicherungen „vor Wiederherstellung“.
- **Aufbewahrung je Ziel:** Es bleiben die letzten *N* **automatischen** Sicherungen; manuelle werden nie gelöscht.
- **Fehler** an einem Ziel stören weder die Sicherung noch die anderen Ziele. Die Spalte *Letzte Übertragung* zeigt ✓ oder ✗ mit der Meldung, das Audit-Log den Eintrag `backup.target.error`.
  Ein Ziel lässt sich mit **Ziel aktiv** abschalten, ohne es zu löschen.

## Verschlüsselung (optional)

Mit **Vor der Übertragung verschlüsseln** und einer Passphrase wird jede Sicherung vor dem Hochladen mit **AES-256-GCM** verschlüsselt (Schlüssel per scrypt aus der Passphrase,
Blockweise mit Authentifizierung gegen Verändern und Abschneiden). Die Datei auf dem Ziel heißt dann `portwerk-…zip.enc`.

> **Wichtig:** Ohne die Passphrase sind die Sicherungen auf dem Ziel nicht lesbar. Sie steht in der Portwerk-Datenbank, die selbst in der Sicherung steckt. Bei einem Totalausfall des Servers hilft das nicht:
> bewahren Sie die Passphrase **zusätzlich getrennt** auf (Passwortmanager). Die Sicherung enthält Passwort-Hashes, Zugangsdaten und das Server-Zertifikat. Ohne Verschlüsselung muss das Ziel entsprechend geschützt sein.

## Workflow 4: Aus einem externen Ziel wiederherstellen

1. Verwaltung → Sicherung → am Ziel **Sicherungen**: die Seitenleiste listet, was dort liegt (Name, automatisch/manuell, Größe, verschlüsselt).
2. Bei der gewünschten Sicherung **Wiederherstellen** und die Rückfrage bestätigen.
3. Portwerk lädt die Datei, entschlüsselt sie bei Bedarf (mit der Passphrase des Ziels), prüft sie und ersetzt den Bestand. Vorher entsteht automatisch eine Sicherung des jetzigen Stands; danach melden sich alle neu an.

**Auf einem neuen Server:** Portwerk neu starten, das Ziel (mit derselben Passphrase) einrichten und wie oben wiederherstellen. Alternativ die Datei vom Ziel manuell holen, mit einem eigenen Skript entschlüsseln
(Format: `PWENC1` + Salz + Präfix, dann Blöcke aus 4 Byte Länge und AES-GCM-Daten) und unter *Aus Datei wiederherstellen* hochladen.

## Fehlerbilder

| Meldung | Ursache | Abhilfe |
|---|---|---|
| Test fehlgeschlagen: … Permission denied | Verzeichnis nicht beschreibbar (Container-Benutzer 10001) | Rechte/Export-Optionen des NAS prüfen (`no_root_squash` ist hier nicht nötig, der Benutzer muss schreiben dürfen) |
| S3 Upload: HTTP 403 | Zugang ohne Schreibrecht, falsche Region oder Zeitabweichung | Rechte, Region und Serverzeit prüfen (Signatur ist zeitabhängig) |
| S3 …: HTTP 301/404 | Falscher Endpunkt oder Stil | bei MinIO *Pfad-Stil* anhaken, Bucket-Namen prüfen |
| WebDAV Upload: HTTP 401/403 | Benutzer/Passwort falsch | bei Nextcloud ein App-Passwort verwenden |
| Entschlüsselung fehlgeschlagen | Falsche Passphrase oder beschädigte Datei | Passphrase am Ziel prüfen |
| Test fehlgeschlagen: … CERTIFICATE_VERIFY_FAILED | eigene CA unbekannt | CA-Zertifikat im Ziel eintragen |

## API

```bash
# Ziele ansehen (Secrets und Passphrase werden nie ausgeliefert; *_set zeigt, ob sie gesetzt sind)
curl -H "X-Auth-Token: $TOKEN" https://opp.example.test/api/admin/backups/targets

# Ziel anlegen (S3)
curl -X POST -H "X-Auth-Token: $TOKEN" -H 'Content-Type: application/json' \
     -d '{"type":"s3","name":"Archiv","endpoint":"https://minio.example.test:9000","bucket":"sicherungen","prefix":"portwerk/prod",
          "access_key":"AK…","secret_key":"…","path_style":true,"keep":30,"encrypt":true,"passphrase":"…"}' \
     https://opp.example.test/api/admin/backups/targets

# Testen, Inhalt auflisten, Sicherung extern ablegen, wiederherstellen
curl -X POST -H "X-Auth-Token: $TOKEN" https://opp.example.test/api/admin/backups/targets/ab12cd34/test
curl -H "X-Auth-Token: $TOKEN" https://opp.example.test/api/admin/backups/targets/ab12cd34/items
curl -X POST -H "X-Auth-Token: $TOKEN" https://opp.example.test/api/admin/backups/portwerk-manual-20261124-121053.zip/push
curl -X POST -H "X-Auth-Token: $TOKEN" -H 'Content-Type: application/json' \
     -d '{"name":"portwerk-manual-20261124-121053.zip.enc","confirm":true}' https://opp.example.test/api/admin/backups/targets/ab12cd34/restore
```
