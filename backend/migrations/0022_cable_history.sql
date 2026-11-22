-- Verbindungs-Historie: jede Verbindung (Kabel) mit Gültigkeitszeitraum. valid_to IS NULL = steckt aktuell.
-- Trigger auf ``cables`` halten die Historie vollständig – auch beim Löschen über Fremdschlüssel (Port/Gerät gelöscht).
-- Wer/welcher Auftrag eine Verbindung beendet hat, trägt ``app/cablelog.py`` vor dem Löschen ein (ended_*).
-- Gerätename und Portname werden beim Stecken festgehalten, damit die Historie Umbenennungen und Löschungen übersteht.
CREATE TABLE IF NOT EXISTS cable_history (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    cable_id           INTEGER NOT NULL,                     -- cables.id (ohne Fremdschlüssel, das Kabel wird gelöscht)
    port_a_id          INTEGER REFERENCES ports(id) ON DELETE SET NULL,
    port_b_id          INTEGER REFERENCES ports(id) ON DELETE SET NULL,
    host_a             TEXT NOT NULL DEFAULT '',
    port_a_name        TEXT NOT NULL DEFAULT '',
    host_b             TEXT NOT NULL DEFAULT '',
    port_b_name        TEXT NOT NULL DEFAULT '',
    cable_label        TEXT NOT NULL DEFAULT '',
    cable_type         TEXT NOT NULL DEFAULT '',
    length_m           REAL,
    color              TEXT NOT NULL DEFAULT '',
    note               TEXT NOT NULL DEFAULT '',
    created_by         TEXT NOT NULL DEFAULT '',
    workorder_id       INTEGER REFERENCES workorders(id) ON DELETE SET NULL,   -- Auftrag, der die Verbindung hergestellt hat
    valid_from         REAL NOT NULL,
    valid_to           REAL,
    ended_by           TEXT NOT NULL DEFAULT '',
    ended_workorder_id INTEGER REFERENCES workorders(id) ON DELETE SET NULL,   -- Auftrag, der sie getrennt hat
    end_reason         TEXT NOT NULL DEFAULT ''              -- manual | workorder | wizard | retire | (leer = Port/Gerät gelöscht)
);
CREATE INDEX IF NOT EXISTS idx_cable_history_a ON cable_history(port_a_id);
CREATE INDEX IF NOT EXISTS idx_cable_history_b ON cable_history(port_b_id);
CREATE INDEX IF NOT EXISTS idx_cable_history_cable ON cable_history(cable_id);
CREATE INDEX IF NOT EXISTS idx_cable_history_time ON cable_history(valid_from, valid_to);

-- Bestand übernehmen (Beginn = Anlagezeitpunkt des Kabels)
INSERT INTO cable_history(cable_id, port_a_id, port_b_id, host_a, port_a_name, host_b, port_b_name,
                          cable_label, cable_type, length_m, color, note, created_by, workorder_id, valid_from)
SELECT c.id, c.port_a_id, c.port_b_id, da.hostname, pa.name, db_.hostname, pb.name,
       c.cable_label, c.cable_type, c.length_m, c.color, c.note, c.created_by, c.workorder_id,
       CASE WHEN c.created_at > 0 THEN c.created_at ELSE (julianday('now') - 2440587.5) * 86400.0 END
FROM cables c
JOIN ports pa ON pa.id = c.port_a_id JOIN devices da ON da.id = pa.device_id
JOIN ports pb ON pb.id = c.port_b_id JOIN devices db_ ON db_.id = pb.device_id;

CREATE TRIGGER IF NOT EXISTS trg_cables_history_insert AFTER INSERT ON cables
BEGIN
    INSERT INTO cable_history(cable_id, port_a_id, port_b_id, host_a, port_a_name, host_b, port_b_name,
                              cable_label, cable_type, length_m, color, note, created_by, workorder_id, valid_from)
    VALUES (NEW.id, NEW.port_a_id, NEW.port_b_id,
            COALESCE((SELECT d.hostname FROM ports p JOIN devices d ON d.id = p.device_id WHERE p.id = NEW.port_a_id), ''),
            COALESCE((SELECT name FROM ports WHERE id = NEW.port_a_id), ''),
            COALESCE((SELECT d.hostname FROM ports p JOIN devices d ON d.id = p.device_id WHERE p.id = NEW.port_b_id), ''),
            COALESCE((SELECT name FROM ports WHERE id = NEW.port_b_id), ''),
            NEW.cable_label, NEW.cable_type, NEW.length_m, NEW.color, NEW.note, NEW.created_by, NEW.workorder_id,
            CASE WHEN NEW.created_at > 0 THEN NEW.created_at ELSE (julianday('now') - 2440587.5) * 86400.0 END);
END;

CREATE TRIGGER IF NOT EXISTS trg_cables_history_update AFTER UPDATE ON cables
BEGIN
    UPDATE cable_history SET cable_label = NEW.cable_label, cable_type = NEW.cable_type, length_m = NEW.length_m,
                             color = NEW.color, note = NEW.note
    WHERE cable_id = OLD.id AND valid_to IS NULL;
END;

CREATE TRIGGER IF NOT EXISTS trg_cables_history_delete AFTER DELETE ON cables
BEGIN
    UPDATE cable_history SET valid_to = MAX(valid_from, (julianday('now') - 2440587.5) * 86400.0)
    WHERE cable_id = OLD.id AND valid_to IS NULL;
END;
