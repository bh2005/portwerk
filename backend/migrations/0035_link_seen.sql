-- „Nicht gesehen seit …“: je lokalem Port einer dokumentierten Verbindung, wann LLDP/CDP sie zuletzt bestätigt hat (last_ok)
-- und seit wann sie fehlt (missing_since). Wird bei jedem Import der Nachbardaten fortgeschrieben (compare.track).
CREATE TABLE IF NOT EXISTS link_seen (
    port_id       INTEGER PRIMARY KEY REFERENCES ports(id) ON DELETE CASCADE,
    peer_port_id  INTEGER REFERENCES ports(id) ON DELETE SET NULL,     -- dokumentiertes Gegenüber (Ende der Strecke)
    last_ok       REAL,                                                -- zuletzt von LLDP/CDP bestätigt
    missing_since REAL                                                 -- seit dem ersten Import, in dem sie fehlte (NULL = gesehen)
);
