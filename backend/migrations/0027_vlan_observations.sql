-- VLAN-Soll/Ist: von Checkmk gemeldete VLANs je Port (Cisco, CISCO-VLAN-MEMBERSHIP-MIB: nur Access-VLANs, keine Trunks/Voice)
CREATE TABLE IF NOT EXISTS vlan_observations (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    port_id   INTEGER REFERENCES ports(id) ON DELETE SET NULL,
    port_name TEXT NOT NULL DEFAULT '',
    vlans     TEXT NOT NULL DEFAULT '',        -- „20“ bzw. bei multi-VLAN „1-3, 9-10, 17“ (Format von Checkmk)
    vlantype  TEXT NOT NULL DEFAULT '',        -- static | dynamic | multi-VLAN
    seen_at   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_vlan_obs_device ON vlan_observations(device_id);
CREATE INDEX IF NOT EXISTS idx_vlan_obs_port ON vlan_observations(port_id);

-- Zeitpunkt der letzten VLAN-Meldung (leer = für dieses Gerät liegen keine VLAN-Daten vor)
ALTER TABLE devices ADD COLUMN vlans_at REAL;
