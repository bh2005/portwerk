-- Abwesenheit und Vertretung: im Zeitraum gehen Benachrichtigungen an die Vertretung; „Meine Aufgaben“ zeigt ihr die Aufträge mit
CREATE TABLE IF NOT EXISTS user_absences (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    start_date TEXT    NOT NULL,                                   -- JJJJ-MM-TT (einschließlich)
    end_date   TEXT    NOT NULL,                                   -- JJJJ-MM-TT (einschließlich)
    deputy_id  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    note       TEXT    NOT NULL DEFAULT '',
    created_by TEXT    NOT NULL DEFAULT '',
    created_at REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_user_absences_user ON user_absences(user_id, start_date, end_date);
CREATE INDEX IF NOT EXISTS idx_user_absences_deputy ON user_absences(deputy_id, start_date, end_date);
