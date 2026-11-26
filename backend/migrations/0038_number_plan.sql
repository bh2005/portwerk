-- Rufnummernplan: Blöcke (Präfix + Durchwahlbereich) und vergebene/reservierte Durchwahlen; freie Nummern ergeben sich aus dem Bereich
CREATE TABLE IF NOT EXISTS number_blocks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id      INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    sip_trunk_id INTEGER REFERENCES sip_trunks(id) ON DELETE SET NULL,
    name         TEXT    NOT NULL DEFAULT '',
    prefix       TEXT    NOT NULL,                       -- z. B. +49 6181 1234
    range_from   INTEGER NOT NULL,                       -- erste Durchwahl
    range_to     INTEGER NOT NULL,                       -- letzte Durchwahl
    width        INTEGER NOT NULL DEFAULT 0,             -- feste Stellenzahl der Durchwahl (0 = ohne führende Nullen)
    note         TEXT    NOT NULL DEFAULT '',
    created_by   TEXT    NOT NULL DEFAULT '',
    created_at   REAL    NOT NULL DEFAULT 0,
    updated_at   REAL    NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_number_blocks_site ON number_blocks(site_id);
CREATE INDEX IF NOT EXISTS idx_number_blocks_trunk ON number_blocks(sip_trunk_id);

CREATE TABLE IF NOT EXISTS number_assignments (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    block_id       INTEGER NOT NULL REFERENCES number_blocks(id) ON DELETE CASCADE,
    extension      INTEGER NOT NULL,
    status         TEXT    NOT NULL DEFAULT 'assigned',   -- assigned | reserved
    kind           TEXT    NOT NULL DEFAULT 'person',     -- person | function | group | fax | special | other
    holder         TEXT    NOT NULL DEFAULT '',           -- Person oder Funktion (z. B. Zentrale, Aufzug Halle 2)
    device_id      INTEGER REFERENCES devices(id) ON DELETE SET NULL,   -- Endgerät (Telefon, DECT, Fax …)
    reserved_until TEXT,                                  -- YYYY-MM-DD, nur bei reserved
    note           TEXT    NOT NULL DEFAULT '',
    updated_by     TEXT    NOT NULL DEFAULT '',
    created_at     REAL    NOT NULL DEFAULT 0,
    updated_at     REAL    NOT NULL DEFAULT 0,
    UNIQUE (block_id, extension)
);
CREATE INDEX IF NOT EXISTS idx_number_assignments_device ON number_assignments(device_id);
