# Releases und Changelog

Unter **Verwaltung → Releases** zeigt Portwerk die installierte Version und die Änderungen je Version (neueste zuerst, die aktuelle ist markiert).
Der Tab ist für globale Administratoren sichtbar.

## Wo die Einträge herkommen

Aus der Datei [`backend/app/CHANGELOG.md`](../../backend/app/CHANGELOG.md). Sie wird mit dem Image ausgeliefert; die **Version** der Anwendung
(`/health`, API-Dokumentation) ist der oberste Eintrag. Es gibt keine zweite Stelle, an der man die Version pflegen müsste.

## Format

```markdown
## 0.5.0 – 2026-12-01
- Titel der Änderung: Beschreibung in ein bis zwei Sätzen.
- Noch eine Änderung: Was ändert sich für die Anwender?

## 0.4.1 – 2026-11-24
- …
```

- Überschrift: `## <Version> – <Datum als JJJJ-MM-TT>`.
- Je Änderung eine Zeile `- Titel: Beschreibung`. Alles vor dem ersten `: ` ist der Titel (fett dargestellt), der Rest die Beschreibung. Ohne `: ` erscheint die ganze Zeile als Beschreibung.
- Neueste Version **zuerst**. Zeilen, die nicht mit `- ` beginnen, werden ignoriert.

## Workflow: Release vorbereiten

1. Änderungen entwickeln und testen.
2. In `CHANGELOG.md` oben einen neuen Block anlegen (Version hochzählen) und die Änderungen aus Sicht der Anwender beschreiben, nicht als Commit-Liste.
3. Beispiel – ein neues Feature:

   ```markdown
   ## 0.5.0 – 2026-12-01
   - Kabelliste: Neue Liste aller Kabel mit Filter „vorläufig“, um unvollständig dokumentierte Strecken zu finden.
   ```
4. Image bauen und ausrollen. Nach dem Neustart steht die neue Version im Tab *Releases* und in `/health`:

   ```bash
   curl https://opp.example.test/health
   # {"status": "ok", "version": "0.5.0"}
   ```

## Versionsnummern

Es gilt grob: **Patch** (`0.4.1`) für kleine Verbesserungen und Korrekturen, **Minor** (`0.5.0`) für neue Funktionen, **Major** erst bei einer inkompatiblen Änderung
(z. B. verändertes Datenmodell mit manueller Migration). Datenbankmigrationen (`backend/migrations`) laufen beim Start automatisch.

## API

```bash
curl -H "X-Auth-Token: $TOKEN" https://opp.example.test/api/releases
# → {"version": "0.4.1", "releases": [{"version": "0.4.1", "date": "2026-11-24", "items": [{"title": "…", "text": "…"}]}, …]}
```
