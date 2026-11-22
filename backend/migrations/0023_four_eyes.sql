-- Vier-Augen-Prinzip: wer hat eingereicht, freigegeben, ausgeführt, bestätigt (Prüfung in routers/workorders.py)
ALTER TABLE workorders ADD COLUMN submitted_by TEXT NOT NULL DEFAULT '';
ALTER TABLE workorders ADD COLUMN approved_by  TEXT NOT NULL DEFAULT '';
ALTER TABLE workorders ADD COLUMN finished_by  TEXT NOT NULL DEFAULT '';
ALTER TABLE workorders ADD COLUMN confirmed_by TEXT NOT NULL DEFAULT '';
-- Admin-Ausnahmen (Begründungen, eine je Zeile: „approve: <Name>: <Grund>“)
ALTER TABLE workorders ADD COLUMN four_eyes_override TEXT NOT NULL DEFAULT '';

-- Bestand: aus dem Audit-Log übernehmen (jeweils der letzte Eintrag)
UPDATE workorders SET
  submitted_by = COALESCE((SELECT actor FROM audit_log a WHERE a.entity = 'workorder' AND a.entity_id = CAST(workorders.id AS TEXT)
                           AND a.action = 'workorder.submit' ORDER BY a.ts DESC LIMIT 1), ''),
  approved_by  = COALESCE((SELECT actor FROM audit_log a WHERE a.entity = 'workorder' AND a.entity_id = CAST(workorders.id AS TEXT)
                           AND a.action = 'workorder.approve' ORDER BY a.ts DESC LIMIT 1), ''),
  finished_by  = COALESCE((SELECT actor FROM audit_log a WHERE a.entity = 'workorder' AND a.entity_id = CAST(workorders.id AS TEXT)
                           AND a.action = 'workorder.finish' ORDER BY a.ts DESC LIMIT 1), ''),
  confirmed_by = COALESCE((SELECT actor FROM audit_log a WHERE a.entity = 'workorder' AND a.entity_id = CAST(workorders.id AS TEXT)
                           AND a.action = 'workorder.confirm' ORDER BY a.ts DESC LIMIT 1), '');
