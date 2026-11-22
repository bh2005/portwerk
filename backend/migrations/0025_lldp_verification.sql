-- LLDP-Prüfung ausgeführter Aufträge: Ergebnis der letzten Prüfung (nach jedem Checkmk-Import und auf Anforderung)
ALTER TABLE workorders ADD COLUMN lldp_status TEXT NOT NULL DEFAULT '';      -- '' | ok | problem | pending | none
ALTER TABLE workorders ADD COLUMN lldp_checked_at REAL;
ALTER TABLE workorders ADD COLUMN lldp_detail TEXT NOT NULL DEFAULT '';      -- JSON: Ergebnis je Position
