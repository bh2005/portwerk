-- „Vorläufig dokumentiert“: Verbindung wurde aus dem Soll/Ist-Abgleich übernommen (direkt Gerät↔Gerät); Dosen und Patchfelder fehlen noch.
-- Das Kennzeichen erlaubt eine Liste „noch nachzudokumentieren“; es fällt weg, sobald die Strecke vollständig erfasst ist.
ALTER TABLE cables ADD COLUMN provisional INTEGER NOT NULL DEFAULT 0;
