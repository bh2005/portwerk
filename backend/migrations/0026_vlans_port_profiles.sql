-- VLANs und Portprofile (nur Dokumentation – Portwerk konfiguriert keine Switches)
CREATE TABLE IF NOT EXISTS vlans (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id INTEGER REFERENCES sites(id) ON DELETE CASCADE,        -- NULL = gilt für alle Standorte
    vid     INTEGER NOT NULL CHECK (vid BETWEEN 1 AND 4094),
    name    TEXT    NOT NULL,
    note    TEXT    NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_vlans_site_vid ON vlans(COALESCE(site_id, 0), vid);

CREATE TABLE IF NOT EXISTS port_profiles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    port_mode    TEXT    NOT NULL DEFAULT 'access',                -- access | trunk
    access_vid   INTEGER,
    voice_vid    INTEGER,
    native_vid   INTEGER,
    allowed_vids TEXT    NOT NULL DEFAULT '',                      -- Trunk: „10,20,40-45“, leer = alle
    note         TEXT    NOT NULL DEFAULT ''
);

-- Dokumentierte Konfiguration je Port (leerer Modus = nicht dokumentiert); profile_id = zuletzt angewendetes Profil
ALTER TABLE ports ADD COLUMN port_mode    TEXT NOT NULL DEFAULT '';
ALTER TABLE ports ADD COLUMN access_vid   INTEGER;
ALTER TABLE ports ADD COLUMN voice_vid    INTEGER;
ALTER TABLE ports ADD COLUMN native_vid   INTEGER;
ALTER TABLE ports ADD COLUMN allowed_vids TEXT NOT NULL DEFAULT '';
ALTER TABLE ports ADD COLUMN profile_id   INTEGER REFERENCES port_profiles(id) ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS port_config_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    port_id      INTEGER REFERENCES ports(id) ON DELETE SET NULL,
    host         TEXT NOT NULL DEFAULT '',
    port_name    TEXT NOT NULL DEFAULT '',
    before       TEXT NOT NULL DEFAULT '',                         -- JSON
    after        TEXT NOT NULL DEFAULT '',                         -- JSON
    changed_by   TEXT NOT NULL DEFAULT '',
    workorder_id INTEGER REFERENCES workorders(id) ON DELETE SET NULL,
    reason       TEXT NOT NULL DEFAULT '',                         -- manual | workorder
    changed_at   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_port_config_history_port ON port_config_history(port_id);

-- Auftragsposition: Ziel-Konfiguration (JSON) für einen Port der Position (bei „configure“ = Port A)
ALTER TABLE workitems ADD COLUMN cfg         TEXT NOT NULL DEFAULT '';
ALTER TABLE workitems ADD COLUMN cfg_port_id INTEGER REFERENCES ports(id) ON DELETE SET NULL;
