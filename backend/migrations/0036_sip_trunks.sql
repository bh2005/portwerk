-- SIP-Trunks (Telefonie): Anschlüsse beim Provider, die am SBC ankommen; Einrichtung/Änderung/Kündigung per Patchauftrag
CREATE TABLE IF NOT EXISTS sip_trunks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'planned',      -- planned|ordered|active|suspended|terminated
    mode            TEXT    NOT NULL DEFAULT 'registration', -- registration (Anmeldung mit Zugangsdaten) | static (IP-Peering)
    site_id         INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    sbc_device_id   INTEGER REFERENCES devices(id) ON DELETE SET NULL,   -- wo der Trunk ankommt (SBC, Sprach-Gateway, Router)
    pbx_device_id   INTEGER REFERENCES devices(id) ON DELETE SET NULL,   -- TK-Anlage dahinter
    wan_link_id     INTEGER REFERENCES wan_links(id) ON DELETE SET NULL, -- Leitung, über die der Trunk läuft
    provider        TEXT    NOT NULL DEFAULT '',
    trunk_ident     TEXT    NOT NULL DEFAULT '',             -- Anschluss-/Trunk-Kennung beim Provider
    registrar       TEXT    NOT NULL DEFAULT '',             -- Registrar/Proxy (Host oder Domain)
    channels        INTEGER,                                 -- gleichzeitige Gespräche
    numbers         TEXT    NOT NULL DEFAULT '',             -- Rufnummernblöcke (Freitext, je Zeile einer)
    contract_number TEXT    NOT NULL DEFAULT '',
    contract_start  TEXT,
    contract_end    TEXT,
    notice_days     INTEGER,
    monthly_cost    REAL,
    contact         TEXT    NOT NULL DEFAULT '',
    note            TEXT    NOT NULL DEFAULT '',
    activated_at    REAL,
    terminated_at   REAL,
    created_by      TEXT    NOT NULL DEFAULT '',
    created_at      REAL    NOT NULL DEFAULT 0,
    updated_at      REAL    NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sip_trunks_site ON sip_trunks(site_id);
CREATE INDEX IF NOT EXISTS idx_sip_trunks_wan ON sip_trunks(wan_link_id);

ALTER TABLE workitems ADD COLUMN sip_trunk_id INTEGER REFERENCES sip_trunks(id) ON DELETE SET NULL;
-- Änderungswerte bei trunk_change stehen (wie bei wan_change) als JSON in workitems.wan_patch
