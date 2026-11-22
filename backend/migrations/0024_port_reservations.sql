-- Port-Reservierungen: Ports für einen Zweck/ein Projekt freihalten, damit sie nicht doppelt verplant werden.
-- Höchstens eine Reservierung je Port. Abgelaufene (until < heute) gelten als frei, bleiben aber sichtbar, bis sie freigegeben werden.
CREATE TABLE IF NOT EXISTS port_reservations (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    port_id      INTEGER NOT NULL UNIQUE REFERENCES ports(id) ON DELETE CASCADE,
    purpose      TEXT    NOT NULL,                                        -- wofür (Projekt, Zweck)
    reserved_by  TEXT    NOT NULL DEFAULT '',
    workorder_id INTEGER REFERENCES workorders(id) ON DELETE SET NULL,  -- optional: für diesen Auftrag (dort ohne Rückfrage nutzbar)
    until        TEXT,                                                    -- JJJJ-MM-TT (einschließlich), leer = unbefristet
    created_at   REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_port_reservations_wo ON port_reservations(workorder_id);
